import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from platform_api.multi_repository import ConversationNotFound, MultiRepository
from platform_api.multi_runtime import MultiRuntime
from platform_api.providers.openai import OpenAIProvider


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=12000)
    semanticMode: Literal["off", "on"] = "off"
    knowledgeMode: Literal["native", "documents", "structured"] | None = None
    conversationId: str | None = None
    baselineReportRef: Literal["atcis:report:R0"] | None = None


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    courseId: str


class ComparisonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=12000)
    firstMode: Literal["off", "on"] = "off"
    firstKnowledgeMode: Literal["native", "documents", "structured"] = "native"
    baselineReportRef: Literal["atcis:report:R0"] | None = None


def create_multi_app(path=None, provider=None, sources=None, semantic=None):
    sources = sources or {
        s: {
            "url": os.getenv(
                f"{s.upper()}_BASE_URL", f"http://127.0.0.1:{4100 if s == 'atcis' else 4110}"
            ),
            "mcpUrl": os.getenv(
                f"{s.upper()}_MCP_URL", f"http://127.0.0.1:{4200 if s == 'atcis' else 4210}/mcp"
            ),
            "token": os.getenv(f"{s.upper()}_READ_TOKEN", ""),
            "mcpToken": os.getenv(f"{s.upper()}_MCP_TOKEN", ""),
        }
        for s in ("atcis", "knccs")
    }
    semantic = semantic or {
        "url": os.getenv("SEMANTIC_BASE_URL", "http://127.0.0.1:4400"),
        "token": os.getenv("SEMANTIC_READ_TOKEN", ""),
        "mcpUrl": os.getenv("SEMANTIC_MCP_URL", "http://127.0.0.1:4410/mcp"),
        "mcpToken": os.getenv("SEMANTIC_MCP_TOKEN", ""),
        "builderUrl": os.getenv("BUILDER_BASE_URL", "http://127.0.0.1:4420"),
        "adminToken": os.getenv("BUILDER_ADMIN_TOKEN", ""),
    }
    v4 = os.getenv("C4I_CONTRACT_VERSION") == "4"
    domain = os.getenv("C4I_CONTRACT_VERSION") in ("3", "4")
    repository_type = MultiRepository
    if v4:
        from platform_api.knowledge_runtime import KnowledgeRepository

        repository_type = KnowledgeRepository
    repo = repository_type(
        Path(
            path
            or os.getenv(
                "PLATFORM_VNEXT_DB",
                "var/platform-v4.db"
                if v4
                else "var/platform-v3.db"
                if domain
                else "var/platform-vnext-v2.db",
            )
        ),
        os.getenv("AUTO_SEMANTIC_MODE", "off"),
        "4-knowledge-abc" if v4 else "3-domain-native-off" if domain else "2-native-off",
        "4" if v4 else "3" if domain else "2",
    )
    runtime_type = MultiRuntime
    if domain:
        from platform_api.domain_runtime import DomainRuntime

        runtime_type = DomainRuntime
    if v4:
        from platform_api.knowledge_runtime import KnowledgeRuntime

        runtime_type = KnowledgeRuntime
    runtime = runtime_type(repo, provider or OpenAIProvider(), sources, semantic)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        await repo.open()
        tasks = [
            *(asyncio.create_task(runtime.ingest(s)) for s in sources),
            asyncio.create_task(runtime.worker()),
        ]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await repo.close()

    app = FastAPI(title="Heterogeneous Battlefield Analytical Platform", lifespan=lifespan)
    app.state.repository, app.state.runtime = repo, runtime

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": "not_found"}, status_code=404)

    @app.get("/health")
    async def health():
        return {"status": "ok", "profile": "heterogeneous"}

    @app.get("/api/v1/config")
    async def config():
        return {
            "profile": "heterogeneous",
            **(
                {
                    "defaultKnowledgeMode": "native",
                    "knowledgeModes": ["native", "documents", "structured"],
                    "fabricUrl": semantic["url"],
                }
                if v4
                else {"defaultSemanticMode": "off"}
            ),
            "sourceToolContractVersion": repo.source_contract,
            "semanticPolicyVersion": repo.policy_version,
        }

    @app.get("/ready")
    @app.get("/api/v1/sources")
    async def ready():
        return {"sources": runtime.source_status, "mcp": runtime.mcp_status}

    @app.get("/api/v1/situation")
    async def situation():
        return await repo.situation() | {"connections": runtime.source_status}

    @app.post("/api/v1/analyses", status_code=202)
    async def create(body: Question):
        try:
            if v4 and (body.knowledgeMode is None or "semanticMode" in body.model_fields_set):
                raise HTTPException(
                    422, "v4 requires knowledgeMode; semanticMode is a legacy contract"
                )
            return await repo.enqueue(
                body.question,
                ("on" if body.knowledgeMode == "structured" else "off")
                if v4
                else body.semanticMode,
                body.conversationId,
                baseline_report_ref=body.baselineReportRef,
                knowledge_mode=body.knowledgeMode if v4 else None,
            )
        except ConversationNotFound:
            return JSONResponse({"error": "conversation_not_found"}, status_code=404)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/v1/analyses")
    async def runs():
        return {"items": await repo.runs()}

    @app.post("/api/v1/comparisons", status_code=202)
    async def compare(body: ComparisonInput):
        if v4 and "firstMode" in body.model_fields_set:
            raise HTTPException(422, "v4 requires firstKnowledgeMode")
        return await repo.create_comparison(
            body.question, body.firstKnowledgeMode if v4 else body.firstMode, body.baselineReportRef
        )

    @app.get("/api/v1/comparisons")
    async def comparisons():
        return {"items": await repo.comparisons()}

    @app.get("/api/v1/comparisons/{comparison_id}")
    async def comparison(comparison_id: str):
        return await repo.comparison(comparison_id)

    @app.get("/api/v1/semantic/status")
    async def semantic_status():
        import httpx

        try:
            async with httpx.AsyncClient(timeout=2) as client:
                result = await client.get(
                    semantic["url"] + "/v1/builds/active",
                    headers={"Authorization": f"Bearer {semantic['token']}"}
                    if semantic.get("token")
                    else {},
                )
                result.raise_for_status()
                return result.json()
        except httpx.HTTPError:
            return JSONResponse({"status": "unavailable"}, status_code=503)

    @app.get("/api/v1/analyses/{run_id}")
    async def run(run_id: str):
        return await repo.get_run(run_id)

    @app.get("/api/v1/analyses/{run_id}/semantic-evidence/{evidence_id}")
    async def semantic_evidence(run_id: str, evidence_id: str):
        from urllib.parse import quote

        import httpx

        item = await repo.get_run(run_id)
        if item["semanticMode"] != "on" or not item.get("graphInfo"):
            raise KeyError(evidence_id)

        def ids(value):
            if isinstance(value, dict):
                found = set(value.get("evidenceRefs", []))
                for nested in value.values():
                    found.update(ids(nested))
                return found
            if isinstance(value, list):
                return {ref for nested in value for ref in ids(nested)}
            return set()

        allowed = {
            ref
            for e in item["evidence"]
            if e.get("systemId") == "semantic"
            for ref in ids(e["data"])
        }
        if evidence_id not in allowed:
            raise KeyError(evidence_id)
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                response = await client.get(
                    semantic["url"] + "/v1/evidence/" + quote(evidence_id, safe=""),
                    params={"graphVersion": item["graphInfo"]["graphVersion"]},
                    headers={"Authorization": f"Bearer {semantic['token']}"}
                    if semantic.get("token")
                    else {},
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                raise HTTPException(503, "Semantic evidence temporarily unavailable") from exc

    @app.get("/api/v1/conversations/{conversation_id}")
    async def conversation(conversation_id: str):
        items = await repo.conversation(conversation_id)
        if not items:
            raise KeyError(conversation_id)
        return {"items": items}

    @app.put("/api/v1/analyses/{run_id}/selection")
    async def select(run_id: str, body: Selection):
        try:
            return await repo.select(run_id, body.courseId)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/stream")
    async def stream(request: Request, after: int = 0):
        try:
            cursor = int(request.headers.get("last-event-id", after))
            if cursor < 0:
                raise ValueError("negative cursor")
        except ValueError as exc:
            raise HTTPException(422, "invalid cursor") from exc

        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                for seq, event in await repo.events(cursor):
                    cursor = seq
                    yield f"id: {seq}\nevent: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    static = Path(__file__).parent / "web_static"
    if (static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/")
    async def index():
        if (static / "index.html").exists():
            return FileResponse(static / "index.html")
        raise HTTPException(503, "Build UI before packaging")

    return app
