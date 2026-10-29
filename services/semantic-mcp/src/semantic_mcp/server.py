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
        description="Interpret a reviewed concept at pinned graphVersion. Known terms include availability, available, 가용, 가용성, tank, 탱크, 함정, 무인기, 전력. Returns only matching reviewed rules and explicitly required dependencies; unresolved responses return supportedTerms. For common availability aggregation pass its evidenceId as conceptEvidenceIds with Semantic identity/reference evidence. Mappings are interpretation rules, not live observations; read state from source MCP."
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
        + (
            " V5 also resolves explicit work-order, part, inventory, cargo and transport record IDs to their graph keys; read current facts via the respective source MCP."
            if os.getenv("C4I_CONTRACT_VERSION") == "5"
            else ""
        )
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

    if os.getenv("C4I_CONTRACT_VERSION") in ("3", "4", "5"):

        @server.tool(
            description="Explore verified organization/report/incident/activity relations at graphVersion. subject is a graph key returned by Semantic tools. Traverse ONLY requested relationTypes; to reach logistics relations from an ATCIS equipment key, include SAME_AS and depth >= 2 or resolve the logistics asset first. relationTypes allowed: SUBORDINATE_TO,ASSIGNED_TO,REFERS_TO,DERIVED_FROM,SUPERSEDES. Bounded traversal preserves edge direction and returns proofs/partial coverage. No live state inference."
            + (
                " V5 also allows SAME_AS,MAINTAINS,REQUIRES,STOCK_OF,RESERVES,FOR_WORK,FULFILLED_BY,CARRIED_BY,CONTAINS_PART. Use resolve_entity to obtain a source record graph key, then traverse explicit dependencies."
                if os.getenv("C4I_CONTRACT_VERSION") == "5"
                else ""
            )
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
            description="Read the reviewed incident reporting/activity completion procedure SOP-01 only. This tool does not define equipment repair, parts allocation, transport delivery or restoration forecasts. Provide documentId explicitly; read source activities/reports before evaluating incident completion."
        )
        async def get_procedure_definition(graphVersion: str, documentId: str) -> dict:
            return await request(
                "/v1/procedures", {"graphVersion": graphVersion, "documentId": documentId}
            )

    if os.getenv("C4I_CONTRACT_VERSION") == "5":

        @server.tool(
            description="Read reviewed Korean displayName, description, aliases, native code labels and units at this pinned graphVersion. Same content is in Fabric document fabric:DISPLAY-01 available to B. Presentation metadata is not an executed availability/identity rule. Unknown values remain unknown. Use original native IDs in tools and concise meaningful Korean in the answer."
        )
        async def get_display_metadata(graphVersion: str) -> dict:
            return await request("/v1/semantic-metadata", {"graphVersion": graphVersion})

    app = server.streamable_http_app()
    app.state.tool_server = server
    app.add_middleware(TokenMiddleware, token=os.getenv("SEMANTIC_MCP_TOKEN", ""))

    async def health(request):
        return JSONResponse({"status": "ok", "service": "semantic-mcp"})

    app.add_route("/health", health)
    return app


def main():
    load_dotenv()
    os.environ.setdefault("C4I_CONTRACT_VERSION", "4")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("SEMANTIC_MCP_PORT", "4410")))
