import asyncio
import contextlib
import os

import uvicorn
from battlefield_ontology import (
    MAPPING_VERSION,
    ONTOLOGY_VERSION,
    RESOLUTION_VERSION,
    SourceSnapshotSet,
    SourceSnapshotSetV5,
)
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from semantic_core.graph import GraphRepository

from graph_builder.worker import GraphBuilder


class BuildInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledgeSetVersion: str | None = None
    snapshots: SourceSnapshotSet | SourceSnapshotSetV5
    ontologyVersion: str = ONTOLOGY_VERSION
    mappingVersion: str = MAPPING_VERSION
    resolutionRuleVersion: str = RESOLUTION_VERSION


def create_app(repository=None, sources=None, admin_token=None):
    load_dotenv()
    repo = repository or GraphRepository(
        os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
        os.getenv("NEO4J_USER", "neo4j"),
        os.environ["NEO4J_PASSWORD"],
    )
    worker = GraphBuilder(
        repo,
        sources
        or {
            s: {
                "url": os.getenv(
                    f"{s.upper()}_BASE_URL",
                    f"http://127.0.0.1:{({'atcis': 4100, 'knccs': 4110, 'logistics': 4120})[s]}",
                ),
                "token": os.getenv(f"{s.upper()}_READ_TOKEN", ""),
            }
            for s in (
                ("atcis", "knccs", "logistics")
                if os.getenv("C4I_CONTRACT_VERSION") == "5"
                else ("atcis", "knccs")
            )
        },
    )
    token = os.getenv("BUILDER_ADMIN_TOKEN", "") if admin_token is None else admin_token

    @contextlib.asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(repo.verify)
        await asyncio.to_thread(repo.ensure_schema)
        await asyncio.to_thread(
            repo.query,
            "CREATE CONSTRAINT build_request_key IF NOT EXISTS FOR (r:BuildRequest) REQUIRE r.requestId IS UNIQUE",
        )
        tasks = [
            asyncio.create_task(worker.run_forever()),
            *(asyncio.create_task(worker.watch(s)) for s in worker.sources),
        ]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            repo.close()

    app = FastAPI(title="Graph Builder internal management", lifespan=lifespan)
    app.state.worker = worker

    async def admin(request: Request):
        if not token or request.headers.get("authorization") != f"Bearer {token}":
            raise HTTPException(401, "builder admin token required")

    @app.get("/health")
    async def health():
        return {"status": "ok", "graphVersion": worker.last_version, "error": worker.last_error}

    @app.post("/internal/build-requests", status_code=202, dependencies=[Depends(admin)])
    async def submit(body: BuildInput):
        try:
            return await worker.submit(
                body.snapshots.public(),
                {
                    k: getattr(body, k)
                    for k in ("ontologyVersion", "mappingVersion", "resolutionRuleVersion")
                },
                body.knowledgeSetVersion,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/internal/build-requests/{request_id}", dependencies=[Depends(admin)])
    async def info(request_id: str):
        try:
            return await worker.request_info(request_id)
        except KeyError as exc:
            raise HTTPException(404, "request not found") from exc

    return app


def main():
    load_dotenv()
    os.environ.setdefault("C4I_CONTRACT_VERSION", "4")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("BUILDER_PORT", "4420")))
