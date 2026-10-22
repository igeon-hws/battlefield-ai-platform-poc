"""Native v3 HTTP read adapters. Descriptions belong to the MCP server."""

from typing import Annotated
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.responses import JSONResponse

from battlefield_source_runtime.mcp import TokenMiddleware


def create_native_mcp(system, url, read_token="", mcp_token=""):
    server = FastMCP(
        f"Synthetic {system.upper()} native v3", stateless_http=True, json_response=True
    )

    async def get(path, params=None):
        async with httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {read_token}"} if read_token else {},
            timeout=10,
        ) as client:
            response = await client.get(
                "/api/v1" + path, params={k: v for k, v in (params or {}).items() if v is not None}
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        description="Read immutable native snapshot metadata. Pin snapshotId for every following query. No object arrays or semantic interpretation."
    )
    async def get_snapshot(snapshotId: str | None = None) -> dict:
        result = await get(
            "/snapshots/" + quote(snapshotId, safe="") if snapshotId else "/snapshot"
        )
        return {k: v for k, v in result.items() if k != "records"}

    def land_tool(resource, description):
        async def listing(
            snapshotId: str,
            offset: Annotated[int, Field(ge=0)] = 0,
            limit: Annotated[int, Field(ge=1, le=100)] = 100,
        ) -> dict:
            return await get(
                "/" + resource, {"snapshotId": snapshotId, "offset": offset, "limit": limit}
            )

        server.add_tool(
            listing,
            name="list_" + resource.replace("-", "_"),
            description=description
            + " Native land page: items,total,nextOffset. Follow nextOffset at the same snapshot. No cross-source interpretation.",
        )

    def sea_tool(resource, description):
        async def listing(
            snapshotId: str,
            continuation: str | None = None,
            limit: Annotated[int, Field(ge=1, le=100)] = 100,
        ) -> dict:
            return await get(
                "/" + resource,
                {"snapshotId": snapshotId, "continuation": continuation, "limit": limit},
            )

        server.add_tool(
            listing,
            name="list_" + resource.replace("-", "_"),
            description=description
            + " Native maritime envelope: header.total/header.continuation,payload. Follow continuation with unchanged snapshot and limit. No cross-source interpretation.",
        )

    resources = {
        "atcis": {
            "units": "Read unitCode/name/parentCode and previousName records.",
            "equipment": "Read equipmentId/classCode/maintenanceCode/ownerCode/role and x/y position, east/north vector. Interpret definitions only after reading source documents.",
            "relations": "Read native explicit organizational relation records and validFrom/validTo.",
            "reports": "Read reportId/revision/incidentId/knownAt, source text, derivedFrom/supersedes.",
            "journal": "Read native journal entries.",
            "activities": "Read activityId/stepCode/state/evidenceReport/knownAt. No inferred completion.",
            "documents": "Read versioned native reference documents/codebooks including full text, hash, issuer and section.",
        },
        "knccs": {
            "formations": "Read formationRef/designation/superior.",
            "own-forces": "Read registered own pennant/hullClass/formationRef, engineering and mission fields, lat/lon, knots and course.",
            "contacts": "Read observations keyed by (originator,trackNo); leading zero and originator are part of identity. Not a registered own-force list.",
            "tracks": "Read timestamped track observations, not distinct asset counts.",
            "associations": "Read explicit native association records and their source document references; no inferred identity result.",
            "relations": "Read native COMPONENT_OF/SUPPORT relation records, since/until.",
            "messages": "Read serial/thread/sentAt/receivedAt, relayOf and original text.",
            "delivery-events": "Read message delivery/receipt records, separately from activity data.",
            "documents": "Read versioned native codebook/reference text with source hash and section.",
        },
    }
    for resource, description in resources[system].items():
        (land_tool if system == "atcis" else sea_tool)(resource, description)
    app = server.streamable_http_app()
    app.state.tool_server = server
    app.add_middleware(TokenMiddleware, token=mcp_token)

    async def health(request):
        return JSONResponse(
            {"status": "ok", "service": system + "-mcp", "sourceToolContractVersion": "3"}
        )

    app.add_route("/health", health)
    return app
