import json
from contextlib import AsyncExitStack

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class MCPClient:
    def __init__(self, url: str, token=""):
        self.url, self.token = url, token

    async def __aenter__(self):
        self.stack = AsyncExitStack()
        await self.stack.__aenter__()
        try:
            http = await self.stack.enter_async_context(
                httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {self.token}"} if self.token else {},
                    timeout=20,
                )
            )
            read, write, _ = await self.stack.enter_async_context(
                streamable_http_client(self.url, http_client=http)
            )
            self.session = await self.stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        await self.stack.aclose()

    async def list_tools(self):
        definitions: list[dict] = []
        cursor = None
        seen = set()
        while True:
            page = await self.session.list_tools(cursor=cursor)
            definitions.extend(
                tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                for tool in page.tools
            )
            cursor = page.nextCursor
            if cursor is None:
                return definitions
            if cursor in seen:
                raise ValueError("repeated MCP tools/list cursor")
            seen.add(cursor)

    async def call(self, name: str, args: dict):
        result = await self.session.call_tool(name, args)
        if result.isError:
            raise ValueError("mcp_tool_error: " + str(result.content))
        if result.structuredContent is not None:
            return result.structuredContent
        return json.loads(next(item.text for item in result.content if item.type == "text"))
