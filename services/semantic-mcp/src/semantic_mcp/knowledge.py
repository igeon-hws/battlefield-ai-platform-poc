"""Fabric Knowledge MCP: read-only HTTP adapters, independent of Semantic MCP/Graph."""

import os
from typing import Annotated
from urllib.parse import quote

import httpx
import uvicorn
from battlefield_source_runtime.mcp import TokenMiddleware
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.responses import JSONResponse


def create_app(url=None, read_token=None, token=None):
    load_dotenv()
    url = url or os.getenv("SEMANTIC_BASE_URL", "http://127.0.0.1:4400")
    read_token = os.getenv("SEMANTIC_READ_TOKEN", "") if read_token is None else read_token
    token = os.getenv("KNOWLEDGE_MCP_TOKEN", "") if token is None else token
    server = FastMCP("Fabric Knowledge", stateless_http=True, json_response=True)

    async def get(path, params):
        async with httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": "Bearer " + read_token} if read_token else {},
            timeout=10,
        ) as client:
            response = await client.get("/v1/knowledge/" + path, params=params)
            response.raise_for_status()
            return response.json()

    @server.tool(
        description="List reviewed document metadata in the pinned knowledge set. Follow nextCursor. No semantic/graph interpretation."
    )
    async def list_knowledge_documents(
        knowledgeSetVersion: str, cursor: str = "", limit: Annotated[int, Field(ge=1, le=50)] = 20
    ) -> dict:
        return await get(
            "documents",
            {"knowledgeSetVersion": knowledgeSetVersion, "cursor": cursor, "limit": limit},
        )

    @server.tool(
        description="Search literal text of reviewed Fabric documents. Returns metadata; get full text by documentKey. No inferred summaries or graph access."
    )
    async def search_knowledge_documents(
        knowledgeSetVersion: str,
        q: str,
        cursor: str = "",
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        return await get(
            "search",
            {"knowledgeSetVersion": knowledgeSetVersion, "q": q, "cursor": cursor, "limit": limit},
        )

    @server.tool(
        description="Read complete reviewed document text, version/hash and provenance in the pinned set. Interpret the text yourself; no rule evaluation helper."
    )
    async def get_knowledge_document(knowledgeSetVersion: str, documentKey: str) -> dict:
        return await get(
            "documents/" + quote(documentKey, safe=""), {"knowledgeSetVersion": knowledgeSetVersion}
        )

    app = server.streamable_http_app()
    app.add_middleware(TokenMiddleware, token=token)

    async def health(request):
        return JSONResponse({"status": "ok", "service": "knowledge-mcp"})

    app.add_route("/health", health)
    return app


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("KNOWLEDGE_MCP_PORT", "4430")))
