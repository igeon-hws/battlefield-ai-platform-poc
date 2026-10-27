import asyncio
import contextlib
import os
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError, ServiceUnavailable
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


class UnavailableRepository:
    def __getattr__(self, name):
        raise ServiceUnavailable("Neo4j is not configured")


def create_app(repository=None, token=None):
    load_dotenv()
    owned = repository is None
    repo = repository or (
        GraphRepository(
            os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            os.getenv("NEO4J_USER", "neo4j"),
            os.environ["NEO4J_PASSWORD"],
        )
        if os.getenv("NEO4J_PASSWORD")
        else UnavailableRepository()
    )
    service: Any = SemanticService(repo)
    if os.getenv("C4I_CONTRACT_VERSION") in ("3", "4"):
        from semantic_core.domain import DomainService

        service = DomainService(repo)
    read_token = os.getenv("SEMANTIC_READ_TOKEN", "") if token is None else token

    @contextlib.asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owned and isinstance(repo, GraphRepository):
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

    from semantic_api.knowledge import install_knowledge

    install_knowledge(app, read)

    if os.getenv("C4I_CONTRACT_VERSION") in ("3", "4"):
        from semantic_api.explorer import install_explorer
        from semantic_api.fabric import install_fabric

        install_explorer(app, read, repo)

        async def ensure_graph(snapshots, knowledge_version=None):
            import httpx

            token = os.getenv("BUILDER_ADMIN_TOKEN", "")
            if not token:
                raise ValueError("Semantic preparation requires BUILDER_ADMIN_TOKEN")
            async with httpx.AsyncClient(
                base_url=os.getenv("BUILDER_BASE_URL", "http://127.0.0.1:4420"),
                headers={"Authorization": "Bearer " + token},
                timeout=10,
            ) as client:
                r = await client.post(
                    "/internal/build-requests",
                    json={
                        "snapshots": snapshots,
                        "ontologyVersion": "4.0.0" if knowledge_version else "3.0.0",
                        "mappingVersion": "4.0.0" if knowledge_version else "3.0.0",
                        "resolutionRuleVersion": "4.0.0" if knowledge_version else "3.0.0",
                        "knowledgeSetVersion": knowledge_version,
                    },
                )
                r.raise_for_status()
                request_id = r.json()["requestId"]
                async with asyncio.timeout(30):
                    while True:
                        r = await client.get("/internal/build-requests/" + request_id)
                        r.raise_for_status()
                        state = r.json()
                        if state["status"] == "FAILED":
                            raise ValueError(
                                "Semantic build failed: " + state.get("error", "unknown")
                            )
                        if state["status"] == "READY":
                            info = await asyncio.to_thread(
                                repo.require_ready, state["graphVersion"]
                            )
                            if info["inputStableHashes"] != {
                                s: r["stableDataHash"] for s, r in snapshots.items()
                            }:
                                raise ValueError("graph snapshot mismatch")
                            return info
                        await asyncio.sleep(0.2)

        install_fabric(app, read, ensure_graph)
        from battlefield_source_runtime.ledger import mount_ui

        mount_ui(app, Path(__file__).parent / "web_static")

        @app.get("/v1/relations", dependencies=[Depends(read)])
        async def relations(
            graphVersion: str,
            subject: str,
            relationTypes: str,
            depth: int = Query(2, ge=0, le=8),
            limit: int = Query(100, ge=1, le=100),
        ):
            return await asyncio.to_thread(
                service.query_relations,
                graphVersion,
                subject,
                relationTypes.split(","),
                depth,
                limit,
            )

        @app.get("/v1/procedures", dependencies=[Depends(read)])
        async def procedure(graphVersion: str, documentId: str):
            return await asyncio.to_thread(
                service.get_procedure_definition, graphVersion, documentId
            )

    return app


def main():
    load_dotenv()
    os.environ.setdefault("C4I_CONTRACT_VERSION", "4")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("SEMANTIC_PORT", "4400")))
