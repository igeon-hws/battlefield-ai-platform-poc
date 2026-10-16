import asyncio
import contextlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from c4i_contracts import Model
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from platform_api.providers.openai import OpenAIProvider
from platform_api.repository import Repository
from platform_api.runtime import Runtime


class Question(Model):
    question: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None


class Selection(Model):
    course_id: str


def create_app(
    path: Path | None = None,
    *,
    c4i_url=None,
    mcp_url=None,
    c4i_token=None,
    mcp_token=None,
    provider=None,
    profile=None,
    sources=None,
    semantic_config=None,
):
    load_dotenv()
    selected_profile = profile or os.getenv("PLATFORM_PROFILE", "legacy")
    if selected_profile == "heterogeneous":
        from platform_api.multi_app import create_multi_app

        return create_multi_app(path, provider, sources, semantic_config)
    if selected_profile != "legacy":
        raise ValueError("unknown platform profile")
    repo = Repository(path or Path(os.getenv("PLATFORM_DB", "var/platform.db")))
    runtime = Runtime(
        repo,
        provider or OpenAIProvider(),
        c4i_url or os.getenv("C4I_BASE_URL", "http://127.0.0.1:4100"),
        mcp_url or os.getenv("MCP_SERVER_URL", "http://127.0.0.1:4200/mcp"),
        os.getenv("C4I_READ_TOKEN", "") if c4i_token is None else c4i_token,
        os.getenv("MCP_TOKEN", "") if mcp_token is None else mcp_token,
    )

    @asynccontextmanager
    async def lifespan(app):
        await repo.open()
        tasks = [asyncio.create_task(runtime.ingest_loop()), asyncio.create_task(runtime.worker())]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await repo.close()

    app = FastAPI(title="Battlefield Intelligence Platform", lifespan=lifespan)
    app.state.repository, app.state.runtime = repo, runtime

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "platform-api"}

    @app.get("/ready")
    async def ready():
        return {
            "sourceConnected": runtime.source_connected,
            "mcpConnected": runtime.mcp_connected,
            "sourceError": runtime.source_error,
            "mcpError": runtime.mcp_error,
            "openaiConfigured": bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")),
        }

    @app.get("/api/v1/situation")
    async def situation():
        return await repo.situation() | {
            "connected": runtime.source_connected,
            "connectionError": runtime.source_error,
        }

    @app.post("/api/v1/analyses", status_code=202)
    async def create(question: Question):
        try:
            return await repo.create_run(question.question, question.conversation_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/v1/analyses")
    async def analyses():
        return {"items": await repo.runs()}

    @app.get("/api/v1/analyses/{run_id}")
    async def analysis(run_id: str):
        return await repo.get_run(run_id)

    @app.get("/api/v1/conversations/{conversation_id}")
    async def conversation(conversation_id: str):
        items = await repo.conversation(conversation_id)
        if not items:
            raise KeyError(conversation_id)
        return {"items": items}

    @app.put("/api/v1/analyses/{run_id}/selection")
    async def selection(run_id: str, data: Selection):
        try:
            return await repo.select(run_id, data.course_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/stream")
    async def stream(request: Request, after: int = 0):
        try:
            cursor = int(request.headers.get("last-event-id", after))
        except ValueError as exc:
            raise HTTPException(422, "invalid cursor") from exc

        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                events = await repo.events(cursor)
                for seq, event in events:
                    cursor = seq
                    yield f"id: {seq}\nevent: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                if not events:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    static = Path(__file__).parent / "web_static"
    if (static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/")
    async def index():
        if (static / "index.html").exists():
            return FileResponse(static / "index.html")
        return JSONResponse(
            {"message": "UI not built. Run frontend build and scripts/build_ui.py."},
            status_code=503,
        )

    return app


def main():
    load_dotenv()
    uvicorn.run(
        create_app(), host="127.0.0.1", port=int(os.getenv("PLATFORM_PORT", "4300")), workers=1
    )
