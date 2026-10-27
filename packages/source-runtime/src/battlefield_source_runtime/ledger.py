"""Snapshot/event persistence only. No ontology, source models or domain rules."""

import asyncio
import contextlib
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles


def content_hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class Ledger:
    def __init__(self, path, system, seed, stable, advance, baseline=None):
        self.path, self.system = Path(path), system
        self.seed, self.stable, self.advance = seed, stable, advance
        self.baseline = baseline
        self.lock = asyncio.Lock()
        self.state: dict = {}

    async def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        await self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS native_snapshots(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS native_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT, epoch TEXT, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS native_state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
        """)
        await self.setup_native()
        async with self.db.execute("SELECT body FROM native_state WHERE id=1") as cursor:
            row = await cursor.fetchone()
        if row:
            self.state = json.loads(row[0])
            if (
                self.state["systemId"] != self.system
                or self.state["datasetId"] != self.seed["datasetId"]
            ):
                raise ValueError("database source/dataset mismatch; choose a separate v3 path")
            await self.persist_native(self.state)
            await self.db.commit()
        else:
            await self.reset()

    def export(self, state):
        stable = self.stable(state)
        return {
            **stable,
            **{k: state[k] for k in ("snapshotId", "sequence", "sourceTime", "stableDataHash")},
        }

    async def save(self, state, kind, payload):
        state = deepcopy(state)
        state["snapshotId"] = uuid4().hex
        state["stableDataHash"] = content_hash(self.stable(state))
        try:
            cursor = await self.db.execute(
                "INSERT INTO native_events(epoch,body) VALUES(?,?)", (state["epochId"], "{}")
            )
            state["sequence"] = cursor.lastrowid
            event = {
                "eventId": uuid4().hex,
                "systemId": self.system,
                "epochId": state["epochId"],
                "sequence": state["sequence"],
                "snapshotId": state["snapshotId"],
                "occurredAt": state["sourceTime"],
                "type": kind,
                "payload": payload,
            }
            await self.db.execute(
                "UPDATE native_events SET body=? WHERE sequence=?",
                (json.dumps(event), state["sequence"]),
            )
            await self.db.execute(
                "INSERT INTO native_snapshots VALUES(?,?)", (state["snapshotId"], json.dumps(state))
            )
            await self.db.execute(
                "INSERT OR REPLACE INTO native_state VALUES(1,?)", (json.dumps(state),)
            )
            await self.persist_native(state)
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise
        self.state = state
        return deepcopy(state)

    async def setup_native(self):
        """Implemented by each source repository, never by semantic adapters."""

    async def persist_native(self, state):
        """Persist source-owned tables in the same snapshot/event transaction."""

    async def reset(self):
        async with self.lock:
            epoch = uuid4().hex
            meta = {
                "systemId": self.system,
                "epochId": epoch,
                "running": False,
                "simulationTime": 0,
            }
            baseline_id = None
            if self.baseline is not None:
                first = await self.save(
                    {**deepcopy(self.baseline), **meta}, "scenario.baseline", {}
                )
                baseline_id = first["snapshotId"]
            return await self.save(
                {**deepcopy(self.seed), **meta, "baselineSnapshotId": baseline_id},
                "scenario.reset",
                {},
            )

    async def snapshot(self, snapshot_id=None):
        if snapshot_id is None:
            return deepcopy(self.state)
        async with self.db.execute(
            "SELECT body FROM native_snapshots WHERE id=?", (snapshot_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return json.loads(row[0])

    async def tick(self, *, force=False):
        async with self.lock:
            if not self.state["running"] and not force:
                return deepcopy(self.state)
            state = deepcopy(self.state)
            self.advance(state)
            state["simulationTime"] += 1
            state["sourceTime"] = (
                datetime.fromisoformat(state["sourceTime"]) + timedelta(seconds=1)
            ).isoformat()
            return await self.save(state, "positions.updated", {})

    async def events(self, epoch, after, through, limit):
        async with self.db.execute(
            "SELECT body FROM native_events WHERE epoch=? AND sequence>? AND sequence<=? ORDER BY sequence LIMIT ?",
            (epoch, after, through, limit + 1),
        ) as cursor:
            rows = list(await cursor.fetchall())
        items = [json.loads(r[0]) for r in rows[:limit]]
        return {
            "items": items,
            "epochId": epoch,
            "throughSequence": through,
            "nextCursor": items[-1]["sequence"] if len(rows) > limit else None,
        }


def create_ledger_app(store, install_routes, *, tick_enabled, token, control_token):
    async def ticker():
        while True:
            await asyncio.sleep(1)
            await store.tick()

    @contextlib.asynccontextmanager
    async def lifespan(app):
        await store.open()
        task = asyncio.create_task(ticker()) if tick_enabled else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await store.db.close()

    app = FastAPI(title=f"Synthetic {store.system.upper()} native v3", lifespan=lifespan)
    app.state.store = store

    async def read(request: Request):
        if token and request.headers.get("authorization") != f"Bearer {token}":
            raise HTTPException(401, "invalid read token")

    async def control(request: Request):
        if control_token and request.headers.get("authorization") != f"Bearer {control_token}":
            raise HTTPException(401, "invalid control token")

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": "not_found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"error": "invalid_request", "detail": str(exc)}, status_code=422)

    @app.get("/health")
    @app.get("/ready")
    async def health():
        return {
            "status": "ok",
            "systemId": store.system,
            "synthetic": True,
            "sourceSchemaVersion": store.seed["sourceSchemaVersion"],
        }

    @app.get("/api/v1/snapshot", dependencies=[Depends(read)])
    async def snapshot():
        return await store.snapshot()

    @app.get("/api/v1/snapshots/{snapshot_id}", dependencies=[Depends(read)])
    async def historical(snapshot_id: str):
        return await store.snapshot(snapshot_id)

    @app.get("/api/v1/stable-export", dependencies=[Depends(read)])
    async def export(snapshotId: str):
        return store.export(await store.snapshot(snapshotId))

    @app.get("/api/v1/events", dependencies=[Depends(read)])
    async def events(epochId: str, throughSequence: int, after: int = 0, limit: int = 100):
        if not 1 <= limit <= 100 or after < 0 or throughSequence < after:
            raise ValueError("invalid event bounds")
        return await store.events(epochId, after, throughSequence, limit)

    @app.get("/api/v1/stream", dependencies=[Depends(read)])
    async def stream(request: Request, after: int = 0, epochId: str | None = None):
        epoch = epochId or store.state["epochId"]
        if epoch != store.state["epochId"]:
            raise HTTPException(409, "epoch changed")

        async def generate():
            cursor = after
            while not await request.is_disconnected():
                if epoch != store.state["epochId"]:
                    return
                page = await store.events(epoch, cursor, store.state["sequence"], 100)
                for event in page["items"]:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if not page["items"]:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/api/v1/simulation/{action}", dependencies=[Depends(control)])
    async def simulation(action: str):
        if action == "step":
            return await store.tick(force=True)
        if action not in ("start", "pause"):
            raise HTTPException(404, "unknown action")
        async with store.lock:
            return await store.save(
                {**store.state, "running": action == "start"}, "simulation.changed", {}
            )

    @app.post("/api/v1/scenario/reset", dependencies=[Depends(control)])
    async def reset():
        return await store.reset()

    install_routes(app, store, read, control)
    return app


def mount_ui(app, directory):
    if (directory / "assets").exists():
        app.mount("/assets", StaticFiles(directory=directory / "assets"), name="assets")

    @app.get("/")
    async def index():
        if (directory / "index.html").exists():
            return FileResponse(directory / "index.html")
        raise HTTPException(503, "Build native UI before packaging")

    return app
