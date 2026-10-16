import asyncio
import contextlib
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError
from pydantic import BaseModel, ConfigDict, Field
from semantic_core.graph import GraphRepository
from semantic_core.service import SemanticService


class EquipmentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graphVersion: str
    unitIds: list[str] = Field(min_length=1, max_length=100)
    kind: str | None = None
    limit: int = Field(default=100, ge=1, le=100)
    cursor: int = Field(default=0, ge=0)


def create_app(repository=None, token=None):
    load_dotenv()
    owned = repository is None
    repo = repository or GraphRepository(
        os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
        os.getenv("NEO4J_USER", "neo4j"),
        os.environ["NEO4J_PASSWORD"],
    )
    service = SemanticService(repo)
    read_token = os.getenv("SEMANTIC_READ_TOKEN", "") if token is None else token

    @contextlib.asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owned:
                repo.close()

    app = FastAPI(title="Synthetic Semantic Layer API", lifespan=lifespan)

    async def read(request: Request):
        if read_token and request.headers.get("authorization") != f"Bearer {read_token}":
            raise HTTPException(401, "invalid semantic read token")

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(
            {"error": "not_found", "detail": "Graph version or evidence not found"}, status_code=404
        )

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"error": "invalid_request", "detail": str(exc)}, status_code=422)

    async def unavailable(request, exc):
        return JSONResponse({"error": "graph_unavailable"}, status_code=503)

    app.add_exception_handler(DriverError, unavailable)
    app.add_exception_handler(Neo4jError, unavailable)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "semantic-api"}

    @app.get("/ready")
    async def ready():
        await asyncio.to_thread(repo.verify)
        return {"status": "ok", "activeGraphVersion": await asyncio.to_thread(repo.active_version)}

    @app.get("/v1/concepts", dependencies=[Depends(read)])
    async def concept(graphVersion: str, term: str):
        return await asyncio.to_thread(service.interpret_concept, graphVersion, term)

    @app.get("/v1/unit-scopes", dependencies=[Depends(read)])
    async def scope(graphVersion: str, term: str, maxDepth: int = Query(8, ge=0, le=8)):
        return await asyncio.to_thread(service.resolve_unit_scope, graphVersion, term, maxDepth)

    @app.post("/v1/equipment-refs/query", dependencies=[Depends(read)])
    async def equipment(body: EquipmentQuery):
        return await asyncio.to_thread(
            service.find_equipment_refs,
            body.graphVersion,
            body.unitIds,
            body.kind,
            body.limit,
            body.cursor,
        )

    @app.get("/v1/entities/resolve", dependencies=[Depends(read)])
    async def resolve(graphVersion: str, systemId: str, nativeId: str):
        if systemId not in ("atcis", "knccs"):
            raise HTTPException(422, "unknown source")
        return await asyncio.to_thread(service.resolve_entity, graphVersion, systemId, nativeId)

    @app.get("/v1/evidence/{evidence_id}", dependencies=[Depends(read)])
    async def evidence(evidence_id: str, graphVersion: str):
        return await asyncio.to_thread(service.get_semantic_evidence, graphVersion, evidence_id)

    @app.get("/v1/builds/{version}", dependencies=[Depends(read)])
    async def build(version: str):
        if version == "active":
            version = await asyncio.to_thread(repo.active_version)
            if not version:
                raise KeyError("active")
        return await asyncio.to_thread(repo.build_info, version)

    return app


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("SEMANTIC_PORT", "4400")))
