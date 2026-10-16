import asyncio
import contextlib
import json
import math
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite
from battlefield_geo import decorate, destination
from battlefield_ontology import normalize_equipment, stable_hash, stable_payload
from c4i_contracts import Entity, Position
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles


def stamp():
    return datetime.now(UTC).isoformat()


class SourceStore:
    def __init__(self, path: Path, system: str, seed: dict):
        self.path, self.system, self.seed = path, system, seed
        self.records_key = "tracks" if system == "atcis" else "contacts"
        self.units_key = "units" if system == "atcis" else "formations"
        self.id_key = "trackKey" if system == "atcis" else "contactNo"
        self.unit_key = "ownerUnitCode" if system == "atcis" else "orgRef"
        self.lock = asyncio.Lock()
        self.state: dict = {}

    async def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        await self.db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, epoch TEXT, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS current_state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
        """)
        async with self.db.execute("SELECT body FROM current_state WHERE id=1") as cursor:
            row = await cursor.fetchone()
        if row:
            self.state = json.loads(row[0])
            if self.state.get("systemId") != self.system:
                raise ValueError("source database belongs to another system")
        else:
            await self.reset()

    def export(self, snapshot: dict, *, live=False):
        units = []
        for raw in snapshot[self.units_key]:
            units.append(
                {
                    "unitId": raw["unitCode"] if self.system == "atcis" else raw["orgRef"],
                    "name": raw["name"],
                    "parentId": raw.get("parentCode")
                    if self.system == "atcis"
                    else raw.get("superiorRef"),
                }
            )
        data = {
            "systemId": self.system,
            "datasetId": snapshot["datasetId"],
            "epochId": snapshot["epochId"],
            "units": units,
            "equipment": [
                {
                    k: v
                    for k, v in normalize_equipment(self.system, raw).public().items()
                    if k != "assignmentRole"
                    or "assignmentRole" in raw
                    or snapshot["datasetId"] != "semantic-demo-v1"
                }
                for raw in snapshot[self.records_key]
            ],
        }
        if not live:
            data = stable_payload(data)
        return {
            **data,
            "snapshotId": snapshot["snapshotId"],
            "sequence": snapshot["sequence"],
            "sourceTime": snapshot["sourceTime"],
            "stableDataHash": stable_hash(data),
        }

    async def save(self, state: dict, kind: str, payload: dict):
        state = {**deepcopy(state), "snapshotId": uuid4().hex, "sourceTime": stamp()}
        time_field = "observedAt" if self.system == "atcis" else "reportTime"
        for raw in state[self.records_key]:
            raw.setdefault(time_field, state["sourceTime"])
        try:
            cursor = await self.db.execute(
                "INSERT INTO events(epoch,body) VALUES(?,?)", (state["epochId"], "{}")
            )
            state["sequence"] = cursor.lastrowid
            state["stableDataHash"] = self.export(state)["stableDataHash"]
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
                "UPDATE events SET body=? WHERE seq=?", (json.dumps(event), state["sequence"])
            )
            await self.db.execute(
                "INSERT INTO snapshots VALUES(?,?)", (state["snapshotId"], json.dumps(state))
            )
            await self.db.execute(
                "INSERT OR REPLACE INTO current_state VALUES(1,?)", (json.dumps(state),)
            )
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise
        self.state = state
        return deepcopy(state)

    async def reset(self):
        async with self.lock:
            return await self.save(
                {
                    **deepcopy(self.seed),
                    "systemId": self.system,
                    "epochId": uuid4().hex,
                    "running": False,
                    "simulationTime": 0,
                },
                "scenario.reset",
                {},
            )

    async def snapshot(self, snapshot_id=None):
        if not snapshot_id:
            return deepcopy(self.state)
        async with self.db.execute(
            "SELECT body FROM snapshots WHERE id=?", (snapshot_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise KeyError(snapshot_id)
        return json.loads(row[0])

    async def running(self, value):
        async with self.lock:
            return await self.save(
                {**self.state, "running": value}, "simulation.changed", {"running": value}
            )

    async def tick(self):
        async with self.lock:
            if not self.state["running"]:
                return deepcopy(self.state)
            state = deepcopy(self.state)
            for raw in state[self.records_key]:
                item = normalize_equipment(self.system, raw)
                if not item.position:
                    continue
                east, north = item.velocity["eastMps"], item.velocity["northMps"]
                bearing = math.degrees(math.atan2(east, north)) % 360
                pos = destination(
                    Position.model_validate(item.position), bearing, math.hypot(east, north)
                )
                if self.system == "atcis":
                    raw["pos"] = {"lon": pos.longitude, "lat": pos.latitude}
                    raw["observedAt"] = stamp()
                else:
                    raw["geo"] = pos.public()
                    raw["reportTime"] = stamp()
            state["simulationTime"] += 1
            return await self.save(state, "positions.updated", {})

    async def patch(self, native_id, patch):
        allowed = (
            {
                "ownerUnitCode",
                "classCode",
                "readyCode",
                "sideCode",
                "pos",
                "velocity",
                "exerciseAssetRef",
            }
            if self.system == "atcis"
            else {
                "orgRef",
                "platformCategory",
                "aircraftType",
                "serviceability",
                "identity",
                "geo",
                "motion",
                "exerciseAssetRef",
            }
        )
        allowed.add("assignmentRole")
        if not patch or set(patch) - allowed:
            raise ValueError("unknown or empty patch")
        async with self.lock:
            state = deepcopy(self.state)
            record = next((r for r in state[self.records_key] if r[self.id_key] == native_id), None)
            if record is None:
                raise KeyError(native_id)
            record.update(patch)
            record["observedAt" if self.system == "atcis" else "reportTime"] = stamp()
            normalize_equipment(self.system, record)
            kind = (
                "structure.changed"
                if set(patch)
                & {
                    self.unit_key,
                    "classCode",
                    "platformCategory",
                    "aircraftType",
                    "exerciseAssetRef",
                    "assignmentRole",
                }
                else "equipment.changed"
            )
            return await self.save(state, kind, {"nativeId": native_id, "patch": patch})

    async def events(self, epoch_id, after, through, limit):
        if epoch_id is None:
            epoch_id = self.state["epochId"]
        async with self.db.execute(
            "SELECT body FROM events WHERE epoch=? AND seq>? AND seq<=? ORDER BY seq LIMIT ?",
            (epoch_id, after, through, limit + 1),
        ) as cursor:
            rows = list(await cursor.fetchall())
        items = [json.loads(r[0]) for r in rows[:limit]]
        return {
            "items": items,
            "nextCursor": items[-1]["sequence"] if len(rows) > limit and items else None,
            "epochId": epoch_id,
            "throughSequence": through,
        }


def create_source_app(
    system: str,
    seed: dict,
    path: Path,
    static: Path,
    *,
    tick_enabled=True,
    token="",
    control_token="",
):
    store = SourceStore(path, system, seed)

    async def ticker():
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 1
        while True:
            await asyncio.sleep(max(0, deadline - loop.time()))
            await store.tick()
            deadline += 1
            if loop.time() - deadline > 5:
                deadline = loop.time() + 1

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

    app = FastAPI(title=f"Mock {system.upper()} · synthetic", lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "not_found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "invalid_request", "detail": str(exc)}, status_code=422)

    async def read(request: Request):
        if token and request.headers.get("authorization") != f"Bearer {token}":
            raise HTTPException(401, "invalid read token")

    async def control(request: Request):
        if control_token and request.headers.get("authorization") != f"Bearer {control_token}":
            raise HTTPException(401, "invalid control token")

    @app.get("/health")
    @app.get("/ready")
    async def health():
        return {"status": "ok", "systemId": system, "synthetic": True}

    @app.get("/api/v1/snapshot", dependencies=[Depends(read)])
    async def snapshot():
        return await store.snapshot()

    @app.get("/api/v1/snapshots/{snapshot_id}", dependencies=[Depends(read)])
    async def historical_snapshot(snapshot_id: str):
        return await store.snapshot(snapshot_id)

    @app.get("/api/v1/stable-export", dependencies=[Depends(read)])
    async def export(snapshotId: str):
        return store.export(await store.snapshot(snapshotId))

    @app.get("/api/v1/situation", dependencies=[Depends(read)])
    async def situation():
        snap = await store.snapshot()
        entities = []
        for raw in snap[store.records_key]:
            e = normalize_equipment(system, raw)
            if e.position is None:
                continue
            entity = Entity.model_validate(
                {
                    "entityId": e.native_id,
                    "label": e.native_id,
                    "kind": e.kind,
                    "unitId": e.unit_id,
                    "affiliation": e.affiliation,
                    "availability": e.availability,
                    "position": e.position,
                    "velocity": e.velocity,
                    "source": system,
                    "observedAt": e.observed_at,
                    "updatedAt": snap["sourceTime"],
                    "revision": snap["sequence"],
                }
            )
            entities.append(decorate(entity))
        return {k: v for k, v in snap.items() if k not in (store.records_key, store.units_key)} | {
            "entities": entities
        }

    def page(snapshot, items, limit, cursor):
        return {
            "systemId": system,
            "snapshotId": snapshot["snapshotId"],
            "epochId": snapshot["epochId"],
            "sequence": snapshot["sequence"],
            "items": items[cursor : cursor + limit],
            "matchedCount": len(items),
            "nextCursor": cursor + limit if cursor + limit < len(items) else None,
        }

    @app.get("/api/v1/equipment", dependencies=[Depends(read)])
    async def equipment(
        snapshotId: str,
        nativeIds: str | None = None,
        unitIds: str | None = None,
        typeCode: str | None = None,
        statusCode: str | None = None,
        limit: int = Query(100, ge=1, le=100),
        cursor: int = Query(0, ge=0),
    ):
        snap = await store.snapshot(snapshotId)
        items = []
        for raw in snap[store.records_key]:
            if nativeIds is not None and raw[store.id_key] not in nativeIds.split(","):
                continue
            if unitIds is not None and raw.get(store.unit_key) not in unitIds.split(","):
                continue
            if (
                typeCode
                and raw.get("classCode" if system == "atcis" else "platformCategory") != typeCode
            ) or (
                statusCode
                and raw.get("readyCode" if system == "atcis" else "serviceability") != statusCode
            ):
                continue
            items.append(raw)
        return page(snap, items, limit, cursor)

    @app.get("/api/v1/equipment/{native_id}", dependencies=[Depends(read)])
    async def equipment_detail(native_id: str, snapshotId: str):
        snap = await store.snapshot(snapshotId)
        item = next((r for r in snap[store.records_key] if r[store.id_key] == native_id), None)
        if item is None:
            raise KeyError(native_id)
        return {**page(snap, [item], 1, 0), "item": item}

    @app.get("/api/v1/units", dependencies=[Depends(read)])
    async def units(
        snapshotId: str, limit: int = Query(100, ge=1, le=100), cursor: int = Query(0, ge=0)
    ):
        snap = await store.snapshot(snapshotId)
        return page(snap, snap[store.units_key], limit, cursor)

    @app.get("/api/v1/unit-relations", dependencies=[Depends(read)])
    async def relations(
        snapshotId: str, limit: int = Query(100, ge=1, le=100), cursor: int = Query(0, ge=0)
    ):
        snap = await store.snapshot(snapshotId)
        parent_key = "parentCode" if system == "atcis" else "superiorRef"
        return page(snap, [r for r in snap[store.units_key] if r.get(parent_key)], limit, cursor)

    @app.get("/api/v1/assignments", dependencies=[Depends(read)])
    @app.get("/api/v1/identity-records", dependencies=[Depends(read)])
    async def assignments(
        snapshotId: str, limit: int = Query(100, ge=1, le=100), cursor: int = Query(0, ge=0)
    ):
        snap = await store.snapshot(snapshotId)
        items = [
            {
                k: r.get(k)
                for k in (store.id_key, store.unit_key, "exerciseAssetRef", "assignmentRole")
            }
            for r in snap[store.records_key]
        ]
        return page(snap, items, limit, cursor)

    @app.get("/api/v1/equipment-summary", dependencies=[Depends(read)])
    async def summary(snapshotId: str, typeCode: str | None = None, statusCode: str | None = None):
        snap = await store.snapshot(snapshotId)
        type_field = "classCode" if system == "atcis" else "platformCategory"
        status_field = "readyCode" if system == "atcis" else "serviceability"
        counts = Counter(
            e.get(type_field, "<missing>")
            for e in snap[store.records_key]
            if (not typeCode or e.get(type_field) == typeCode)
            and (not statusCode or e.get(status_field) == statusCode)
        )
        return {
            "systemId": system,
            "snapshotId": snapshotId,
            "counts": counts,
            "matchedCount": sum(counts.values()),
        }

    @app.get("/api/v1/events", dependencies=[Depends(read)])
    async def events(
        epochId: str,
        after: int = Query(0, ge=0),
        throughSequence: int = Query(..., ge=0),
        limit: int = Query(100, ge=1, le=100),
    ):
        return await store.events(epochId, after, throughSequence, limit)

    @app.get("/api/v1/changes", dependencies=[Depends(read)])
    async def changes(fromSnapshotId: str, toSnapshotId: str):
        before = await store.snapshot(fromSnapshotId)
        after = await store.snapshot(toSnapshotId)
        if before["epochId"] != after["epochId"] or before["sequence"] > after["sequence"]:
            raise ValueError("snapshots must be ordered within one epoch")
        old = {r[store.id_key]: r for r in before[store.records_key]}
        new = {r[store.id_key]: r for r in after[store.records_key]}
        return {
            "systemId": system,
            "epochId": after["epochId"],
            "fromSnapshotId": fromSnapshotId,
            "toSnapshotId": toSnapshotId,
            "items": [
                {"nativeId": k, "before": old.get(k), "after": new.get(k)}
                for k in sorted(old.keys() | new.keys())
                if old.get(k) != new.get(k)
            ],
        }

    @app.get("/api/v1/equipment/{native_id}/history", dependencies=[Depends(read)])
    async def history(
        native_id: str,
        epochId: str,
        throughSequence: int = Query(..., ge=0),
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
    ):
        data = await store.events(epochId, after, throughSequence, limit)
        data["items"] = [
            e
            for e in data["items"]
            if e["payload"].get("nativeId") == native_id
            or e["type"] in ("scenario.reset", "positions.updated")
        ]
        return data

    @app.get("/api/v1/stream", dependencies=[Depends(read)])
    async def stream(request: Request, after: int = Query(0, ge=0), epochId: str | None = None):
        if epochId and epochId != store.state["epochId"]:
            raise HTTPException(409, "source epoch changed; reload snapshot")

        async def generate():
            cursor = after
            while not await request.is_disconnected():
                if epochId and epochId != store.state["epochId"]:
                    return
                data = await store.events(epochId, cursor, store.state["sequence"], 100)
                for event in data["items"]:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if not data["items"]:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/api/v1/simulation/{action}", dependencies=[Depends(control)])
    async def simulation(action: str):
        if action not in ("start", "pause"):
            raise HTTPException(404, "unknown action")
        return await store.running(action == "start")

    @app.post("/api/v1/scenario/reset", dependencies=[Depends(control)])
    async def reset():
        return await store.reset()

    @app.patch("/api/v1/equipment/{native_id}", dependencies=[Depends(control)])
    async def patch(native_id: str, body: dict):
        return await store.patch(native_id, body)

    if (static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/")
    async def index():
        if (static / "index.html").exists():
            return FileResponse(static / "index.html")
        raise HTTPException(503, "Build source UI before packaging")

    return app
