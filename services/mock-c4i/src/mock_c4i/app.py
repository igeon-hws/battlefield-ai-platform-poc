import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from c4i_contracts import EntityFilter, EntityPatch
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from mock_c4i.scenario import border_entities, get_scenario, initial_entities
from mock_c4i.store import C4IStore, CursorExpired


def mount_ui(app: FastAPI, directory: Path):
    if (directory / "assets").exists():
        app.mount("/assets", StaticFiles(directory=directory / "assets"), name="assets")

    @app.get("/")
    async def index():
        if (directory / "index.html").exists():
            return FileResponse(directory / "index.html")
        return JSONResponse(
            {"message": "UI not built. Run frontend build and scripts/build_ui.py."},
            status_code=503,
        )


def create_app(
    path: Path | None = None, *, tick_enabled=True, token=None, control_token=None, scenario_id=None
):
    load_dotenv()
    scenario = get_scenario(scenario_id or os.getenv("C4I_SCENARIO", "border-demo"))
    store = C4IStore(path or Path(os.getenv("C4I_DB", "var/c4i.db")))
    read_token = token if token is not None else os.getenv("C4I_READ_TOKEN", "")
    write_token = control_token if control_token is not None else os.getenv("C4I_CONTROL_TOKEN", "")

    async def ticker():
        loop = asyncio.get_running_loop()
        next_tick = loop.time() + 1
        while True:
            await asyncio.sleep(max(0, next_tick - loop.time()))
            if store.state["running"]:
                await store.tick()
            next_tick += 1
            if loop.time() - next_tick > 5:
                next_tick = loop.time() + 1

    @asynccontextmanager
    async def lifespan(app):
        await store.open(
            border_entities() if scenario["scenarioId"] == "border-demo" else initial_entities(),
            scenario=scenario,
        )
        task = asyncio.create_task(ticker()) if tick_enabled else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await store.close()

    app = FastAPI(title="Mock C4I", lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)

    @app.exception_handler(CursorExpired)
    async def expired(request, exc):
        return JSONResponse({"error": "cursor_expired"}, status_code=409)

    def auth(request: Request, expected: str):
        if expected and request.headers.get("authorization") != f"Bearer {expected}":
            raise HTTPException(401, "invalid token")

    async def read(request: Request):
        auth(request, read_token)

    async def control(request: Request):
        auth(request, write_token)

    def parse_filters(request: Request):
        params = dict(request.query_params)
        filter_names = {field.alias or name for name, field in EntityFilter.model_fields.items()}
        allowed = filter_names | {"atSnapshot", "groupBy", "limit", "cursor"}
        if set(params) - allowed:
            raise HTTPException(422, "unknown query parameter")
        data: dict[str, Any] = {key: value for key, value in params.items() if key in filter_names}
        try:
            if "bbox" in data:
                data["bbox"] = [float(value) for value in str(data["bbox"]).split(",")]
            return EntityFilter.model_validate(data)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "mock-c4i"}

    @app.get("/api/v1/snapshot", dependencies=[Depends(read)])
    async def snapshot():
        return await store.snapshot()

    @app.get("/api/v1/snapshots/{snapshot_id}", dependencies=[Depends(read)])
    async def at(snapshot_id: str):
        return await store.snapshot(snapshot_id)

    @app.get("/api/v1/entities/summary", dependencies=[Depends(read)])
    async def summary(
        filters: Annotated[EntityFilter, Depends(parse_filters)],
        atSnapshot: str | None = None,
        groupBy: str = "kind",
    ):
        try:
            return await store.summary(atSnapshot, filters, [v for v in groupBy.split(",") if v])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/entities", dependencies=[Depends(read)])
    async def entities(
        filters: Annotated[EntityFilter, Depends(parse_filters)],
        atSnapshot: str | None = None,
        limit: int = Query(100, ge=1, le=100),
        cursor: int = Query(0, ge=0),
    ):
        return await store.entities(atSnapshot, filters, limit, cursor)

    @app.get("/api/v1/entities/{entity_id}", dependencies=[Depends(read)])
    async def entity(entity_id: str, atSnapshot: str | None = None):
        data = await store.snapshot(atSnapshot)
        found = next((e for e in data["entities"] if e["entityId"] == entity_id), None)
        if not found:
            raise KeyError(entity_id)
        return {"entity": found, "snapshotId": data["snapshotId"], "sourceTime": data["sourceTime"]}

    @app.get("/api/v1/entities/{entity_id}/history", dependencies=[Depends(read)])
    async def entity_history(
        entity_id: str,
        epochId: str,
        throughSequence: int = Query(ge=0),
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
    ):
        try:
            return await store.entity_history(entity_id, epochId, after, throughSequence, limit)
        except CursorExpired:
            raise
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.patch("/api/v1/entities/{entity_id}", dependencies=[Depends(control)])
    async def patch(entity_id: str, data: EntityPatch):
        return await store.patch(
            entity_id, data.model_dump(mode="json", by_alias=True, exclude_unset=True)
        )

    @app.get("/api/v1/changes", dependencies=[Depends(read)])
    async def changes(fromSnapshot: str, toSnapshot: str):
        try:
            return await store.changes(fromSnapshot, toSnapshot)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/events", dependencies=[Depends(read)])
    async def events(
        epochId: str,
        after: int = Query(0, ge=0),
        throughSequence: int | None = None,
        limit: int = Query(100, ge=1, le=100),
    ):
        return {"items": await store.events(epochId, after, throughSequence, limit)}

    @app.get("/api/v1/stream", dependencies=[Depends(read)])
    async def stream(request: Request, epochId: str, after: int = Query(0, ge=0)):
        last = request.headers.get("last-event-id")
        if last:
            try:
                epochId, sequence = last.rsplit(":", 1)
                after = int(sequence)
            except ValueError as exc:
                raise HTTPException(422, "invalid cursor") from exc
        await store.events(epochId, after, limit=1, across_epochs=True)

        async def generate():
            import json

            cursor = after
            while not await request.is_disconnected():
                events = await store.events(epochId, cursor, across_epochs=True)
                for event in events:
                    cursor = event["sequence"]
                    yield f"id: {event['epochId']}:{cursor}\nevent: update\ndata: {json.dumps(event)}\n\n"
                if not events:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/simulation/{action}", dependencies=[Depends(control)])
    async def simulation(action: str):
        if action == "reset":
            return await store.reset()
        if action in ("start", "pause"):
            return await store.running(action == "start")
        raise HTTPException(404, "unknown action")

    mount_ui(app, Path(__file__).parent / "web_static")
    return app


def main():
    load_dotenv()
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("C4I_PORT", "4100")), workers=1)
