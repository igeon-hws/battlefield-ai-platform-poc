import os
from typing import Annotated, Literal

import httpx
import uvicorn
from c4i_contracts import EntityFilter
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.responses import JSONResponse

from c4i_mcp.tool_instructions import C4I_TOOL_DESCRIPTIONS


class TokenMiddleware:
    def __init__(self, app, token: str):
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
    base_url = os.getenv("C4I_BASE_URL", "http://127.0.0.1:4100")
    read_token = os.getenv("C4I_READ_TOKEN", "")
    headers = {"Authorization": f"Bearer {read_token}"} if read_token else {}
    server = FastMCP("Mock C4I read tools", stateless_http=True, json_response=True)

    async def get(path, params=None):
        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10) as client:
            response = await client.get("/api/v1" + path, params=params)
            response.raise_for_status()
            return response.json()

    def filter_params(filters):
        data = EntityFilter.model_validate(filters or {}).model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        if "bbox" in data:
            data["bbox"] = ",".join(map(str, data["bbox"]))
        return data

    @server.tool(description=C4I_TOOL_DESCRIPTIONS["c4i_get_snapshot"])
    async def c4i_get_snapshot(snapshotId: str | None = None) -> dict:
        """Get a stable snapshot reference before C4I queries; returns metadata, not every entity."""
        data = await get(f"/snapshots/{snapshotId}" if snapshotId else "/snapshot")
        return {k: v for k, v in data.items() if k != "entities"} | {
            "entityCount": len(data["entities"])
        }

    @server.tool(description=C4I_TOOL_DESCRIPTIONS["c4i_list_entities"])
    async def c4i_list_entities(
        snapshotId: str,
        filter: EntityFilter | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
        cursor: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        """List registered equipment with kind, affiliation, availability, status or bbox filters. matchedCount counts all pages."""
        return await get(
            "/entities",
            {"atSnapshot": snapshotId, "limit": limit, "cursor": cursor, **filter_params(filter)},
        )

    @server.tool(description=C4I_TOOL_DESCRIPTIONS["c4i_summarize_entities"])
    async def c4i_summarize_entities(
        snapshotId: str,
        filter: EntityFilter | None = None,
        groupBy: list[
            Literal[
                "kind",
                "affiliation",
                "availability",
                "status",
                "maintenanceStatus",
                "unitId",
                "zoneId",
            ]
        ]
        | None = None,
    ) -> dict:
        """Count all matching registered entities at a fixed snapshot; grouping fields: kind, affiliation, availability, status."""
        return await get(
            "/entities/summary",
            {"atSnapshot": snapshotId, "groupBy": ",".join(groupBy or []), **filter_params(filter)},
        )

    @server.tool(description=C4I_TOOL_DESCRIPTIONS["c4i_get_entity"])
    async def c4i_get_entity(snapshotId: str, entityId: str) -> dict:
        """Read one equipment entity at the pinned snapshot."""
        from urllib.parse import quote

        return await get(f"/entities/{quote(entityId, safe='')}", {"atSnapshot": snapshotId})

    @server.tool(description=C4I_TOOL_DESCRIPTIONS["c4i_get_changes"])
    async def c4i_get_changes(fromSnapshotId: str, toSnapshotId: str) -> dict:
        """Read changes between two immutable snapshots in the same epoch."""
        return await get("/changes", {"fromSnapshot": fromSnapshotId, "toSnapshot": toSnapshotId})

    @server.tool(description=C4I_TOOL_DESCRIPTIONS["c4i_list_events"])
    async def c4i_list_events(
        epochId: str,
        after: Annotated[int, Field(ge=0)],
        throughSequence: Annotated[int, Field(ge=0)],
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
    ) -> dict:
        """Read bounded source events, never unbounded future state."""
        data = await get(
            "/events",
            {
                "epochId": epochId,
                "after": after,
                "throughSequence": throughSequence,
                "limit": limit,
            },
        )
        for item in data["items"]:
            item.pop("snapshot", None)
        return data

    @server.tool(description=C4I_TOOL_DESCRIPTIONS["c4i_list_entity_history"])
    async def c4i_list_entity_history(
        entityId: str,
        epochId: str,
        after: Annotated[int, Field(ge=0)],
        throughSequence: Annotated[int, Field(ge=0)],
        limit: Annotated[int, Field(ge=1, le=100)] = 100,
    ) -> dict:
        from urllib.parse import quote

        return await get(
            f"/entities/{quote(entityId, safe='')}/history",
            {
                "epochId": epochId,
                "after": after,
                "throughSequence": throughSequence,
                "limit": limit,
            },
        )

    app = server.streamable_http_app()
    app.state.tool_server = server
    app.add_middleware(TokenMiddleware, token=os.getenv("MCP_TOKEN", ""))

    async def health(request):
        return JSONResponse({"status": "ok", "service": "c4i-mcp"})

    app.add_route("/health", health)
    return app


def main():
    load_dotenv()
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("MCP_PORT", "4200")))
