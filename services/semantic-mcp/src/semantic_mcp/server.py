import os
from typing import Annotated
from urllib.parse import quote

import httpx
import uvicorn
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.responses import JSONResponse


class TokenMiddleware:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["path"] != "/health"
            and self.token
            and dict(scope["headers"]).get(b"authorization") != f"Bearer {self.token}".encode()
        ):
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_app():
    load_dotenv()
    server = FastMCP("Synthetic Semantic Layer read tools", stateless_http=True, json_response=True)
    url = os.getenv("SEMANTIC_BASE_URL", "http://127.0.0.1:4400")
    read_token = os.getenv("SEMANTIC_READ_TOKEN", "")

    async def request(path, params, post=False):
        async with httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {read_token}"} if read_token else {},
            timeout=10,
        ) as client:
            response = (
                await client.post(path, json=params)
                if post
                else await client.get(path, params=params)
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        description="Interpret a reviewed concept at pinned graphVersion. Known terms include availability, available, 가용, 가용성, tank, 탱크, 함정, 무인기, 전력. Unresolved responses return supportedTerms; use a supported term instead of guessing synonyms repeatedly. Returns versioned sourceMappings (native type/state fields and explicit code interpretation) and rule provenance. For common availability aggregation pass its evidenceId as conceptEvidenceIds, with Semantic identity/reference evidence. Mappings are interpretation rules, not live observations; read state from source MCP."
    )
    async def interpret_concept(graphVersion: str, term: str) -> dict:
        return await request("/v1/concepts", {"graphVersion": graphVersion, "term": term})

    @server.tool(
        description="Resolve a unit name or ID and traverse explicit subordinate relationships, returning scope unitIds and evidence paths. Ambiguous names return candidates, not an arbitrary choice. Pinned graphVersion is required; bounded depth may return partial coverage."
    )
    async def resolve_unit_scope(
        graphVersion: str, term: str, maxDepth: Annotated[int, Field(ge=0, le=8)] = 8
    ) -> dict:
        return await request(
            "/v1/unit-scopes", {"graphVersion": graphVersion, "term": term, "maxDepth": maxDepth}
        )

    @server.tool(
        description="Find equipment references directly assigned to explicit scope unitIds (from resolve_unit_scope). Returns canonical/source IDs, assignment and identity evidence; NO live availability/position. Query source MCP at pinned snapshots for current state. Follow nextCursor for completeness; conflicting assignments remain explicit."
    )
    async def find_equipment_refs(
        graphVersion: str,
        unitIds: list[str],
        kind: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        cursor: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        return await request(
            "/v1/equipment-refs/query",
            {
                "graphVersion": graphVersion,
                "unitIds": unitIds,
                "kind": kind,
                "limit": limit,
                "cursor": cursor,
            },
            post=True,
        )

    @server.tool(
        description="Resolve source systemId/nativeId to explicit canonical identity at graphVersion. Only verified exercise identifiers establish identity; unresolved/conflict are not proofs. Returns all source refs and rule evidence, not an explanation of live status disagreement."
    )
    async def resolve_entity(graphVersion: str, systemId: str, nativeId: str) -> dict:
        return await request(
            "/v1/entities/resolve",
            {"graphVersion": graphVersion, "systemId": systemId, "nativeId": nativeId},
        )

    @server.tool(
        description="Read immutable graph assertion provenance by graphVersion/evidenceId: source refs, stable input payload, applied rule and versions. This proves organization/identity, not current availability. Evidence from another build is rejected."
    )
    async def get_semantic_evidence(graphVersion: str, evidenceId: str) -> dict:
        return await request(
            "/v1/evidence/" + quote(evidenceId, safe=""), {"graphVersion": graphVersion}
        )

    if os.getenv("C4I_CONTRACT_VERSION") == "3":

        @server.tool(
            description="Explore verified organization/report/incident/activity relations at graphVersion. subject is a canonical key returned by Semantic tools. relationTypes allowed: SUBORDINATE_TO,ASSIGNED_TO,REFERS_TO,DERIVED_FROM,SUPERSEDES. Bounded traversal returns source/document/rule proofs and partial coverage when truncated. No live state inference."
        )
        async def query_relations(
            graphVersion: str,
            subject: str,
            relationTypes: list[str],
            depth: Annotated[int, Field(ge=0, le=8)] = 2,
            limit: Annotated[int, Field(ge=1, le=100)] = 100,
        ) -> dict:
            return await request(
                "/v1/relations",
                {
                    "graphVersion": graphVersion,
                    "subject": subject,
                    "relationTypes": ",".join(relationTypes),
                    "depth": depth,
                    "limit": limit,
                },
            )

        @server.tool(
            description="Read versioned synthetic procedure definitions and native evidence selectors at graphVersion. Read required source activities/reports before evaluating completion. Does not fetch live values or treat receipt as completion."
        )
        async def get_procedure_definition(graphVersion: str, documentId: str = "SOP-01") -> dict:
            return await request(
                "/v1/procedures", {"graphVersion": graphVersion, "documentId": documentId}
            )

    app = server.streamable_http_app()
    app.state.tool_server = server
    app.add_middleware(TokenMiddleware, token=os.getenv("SEMANTIC_MCP_TOKEN", ""))

    async def health(request):
        return JSONResponse({"status": "ok", "service": "semantic-mcp"})

    app.add_route("/health", health)
    return app


def main():
    load_dotenv()
    os.environ.setdefault("C4I_CONTRACT_VERSION", "3")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("SEMANTIC_MCP_PORT", "4410")))
