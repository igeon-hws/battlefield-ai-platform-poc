"""Read-only HTTP adapter mechanics, imported only by standalone MCP products."""

from typing import Annotated
from urllib.parse import quote

import httpx
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


def create_mcp_app(system, base_url, read_token="", mcp_token=""):
    server = FastMCP(
        f"Synthetic {system.upper()} read tools", stateless_http=True, json_response=True
    )
    fields = (
        "trackKey/ownerUnitCode/classCode/readyCode(R,N,U), units.unitCode/parentCode"
        if system == "atcis"
        else "contactNo/orgRef/platformCategory/serviceability(READY,NOT_READY,UNCONFIRMED), formations.orgRef/superiorRef"
    )
    source_description = (
        f"Synthetic {system.upper()}; native fields: {fields}. No invented hierarchy or identity. "
    )

    async def get(path, params=None):
        headers = {"Authorization": f"Bearer {read_token}"} if read_token else {}
        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
            response = await client.get(
                "/api/v1" + path, params={k: v for k, v in (params or {}).items() if v is not None}
            )
            response.raise_for_status()
            return response.json()

    @server.tool(
        description=source_description
        + "Get immutable snapshot metadata before queries. Omits object arrays; returns snapshotId, epochId, sequence, datasetId, stableDataHash."
    )
    async def get_snapshot(snapshotId: str | None = None) -> dict:
        result = await get(
            "/snapshots/" + quote(snapshotId, safe="") if snapshotId else "/snapshot"
        )
        return {
            k: v
            for k, v in result.items()
            if k not in ("tracks", "contacts", "units", "formations")
        }

    @server.tool(
        description=source_description
        + "Read native equipment at snapshotId. unitIds filter direct source assignments only. typeCode/statusCode filter exact native classCode/readyCode (ATCIS) or platformCategory/serviceability (KNCCS), without common taxonomy or state translation. matchedCount covers all pages; follow nextCursor."
    )
    async def list_equipment(
        snapshotId: str,
        nativeIds: list[str] | None = None,
        unitIds: list[str] | None = None,
        typeCode: str | None = None,
        statusCode: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        cursor: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        return await get(
            "/equipment",
            {
                "snapshotId": snapshotId,
                "nativeIds": ",".join(nativeIds) if nativeIds is not None else None,
                "unitIds": ",".join(unitIds) if unitIds is not None else None,
                "typeCode": typeCode,
                "statusCode": statusCode,
                "limit": limit,
                "cursor": cursor,
            },
        )

    @server.tool(
        description=source_description
        + "Read one native equipment record, never latest when snapshotId is supplied."
    )
    async def get_equipment(snapshotId: str, nativeId: str) -> dict:
        return await get("/equipment/" + quote(nativeId, safe=""), {"snapshotId": snapshotId})

    @server.tool(
        description=source_description
        + "Count exact native type codes at a pinned snapshot. Optional typeCode/statusCode compare native values only. Returns source record counts, not unique cross-system assets."
    )
    async def summarize_equipment(
        snapshotId: str, typeCode: str | None = None, statusCode: str | None = None
    ) -> dict:
        return await get(
            "/equipment-summary",
            {"snapshotId": snapshotId, "typeCode": typeCode, "statusCode": statusCode},
        )

    @server.tool(
        description=source_description
        + "Read raw organization records, including explicit parent references. Resolve ambiguous names rather than guessing; follow pagination."
    )
    async def list_units(
        snapshotId: str,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        cursor: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        return await get("/units", {"snapshotId": snapshotId, "limit": limit, "cursor": cursor})

    @server.tool(
        description=source_description
        + "Read explicit immediate child/parent records; no recursive scope or hidden Graph data. Follow pagination."
    )
    async def list_unit_relations(
        snapshotId: str,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        cursor: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        return await get(
            "/unit-relations", {"snapshotId": snapshotId, "limit": limit, "cursor": cursor}
        )

    @server.tool(
        description=source_description
        + "Read direct native equipment-to-unit assignments, not inferred organization membership. Follow pagination."
    )
    async def list_assignments(
        snapshotId: str,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        cursor: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        return await get(
            "/assignments", {"snapshotId": snapshotId, "limit": limit, "cursor": cursor}
        )

    @server.tool(
        description=source_description
        + "Read raw exerciseAssetRef identifiers and native record/assignment fields. This endpoint returns source records without cross-system identity decisions. Follow pagination."
    )
    async def list_identity_records(
        snapshotId: str,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        cursor: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        return await get(
            "/identity-records", {"snapshotId": snapshotId, "limit": limit, "cursor": cursor}
        )

    @server.tool(
        description=source_description
        + "Compare two immutable snapshots from the same source epoch, returning native before/after records."
    )
    async def get_changes(fromSnapshotId: str, toSnapshotId: str) -> dict:
        return await get(
            "/changes", {"fromSnapshotId": fromSnapshotId, "toSnapshotId": toSnapshotId}
        )

    @server.tool(
        description=source_description
        + "Read events bounded by epochId and throughSequence. Do not use events newer than the run snapshot; follow nextCursor."
    )
    async def list_events(
        epochId: str,
        throughSequence: Annotated[int, Field(ge=0)],
        after: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
    ) -> dict:
        return await get(
            "/events",
            {
                "epochId": epochId,
                "throughSequence": throughSequence,
                "after": after,
                "limit": limit,
            },
        )

    @server.tool(
        description=source_description
        + "Read one native equipment history bounded by source epoch and run sequence. Follow nextCursor even if the filtered page is empty."
    )
    async def list_equipment_history(
        nativeId: str,
        epochId: str,
        throughSequence: Annotated[int, Field(ge=0)],
        after: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
    ) -> dict:
        return await get(
            "/equipment/" + quote(nativeId, safe="") + "/history",
            {
                "epochId": epochId,
                "throughSequence": throughSequence,
                "after": after,
                "limit": limit,
            },
        )

    app = server.streamable_http_app()
    app.state.tool_server = server
    app.add_middleware(TokenMiddleware, token=mcp_token)

    async def health(request):
        return JSONResponse({"status": "ok", "service": f"{system}-mcp"})

    app.add_route("/health", health)
    return app
