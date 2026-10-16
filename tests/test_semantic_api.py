import os
from uuid import uuid4

import httpx
import pytest
from conftest import server
from dotenv import load_dotenv
from platform_api.mcp.client import MCPClient
from semantic_api.app import create_app
from semantic_core.graph import GraphRepository
from test_neo4j import fixture_sources

pytestmark = pytest.mark.neo4j


async def test_semantic_api_and_mcp_share_real_graph_results():
    load_dotenv()
    uri = os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687")
    repo = GraphRepository(uri, "neo4j", os.environ["NEO4J_PASSWORD"])
    version = "test-" + uuid4().hex
    repo.ensure_schema()
    repo.build(fixture_sources(), graph_version=version)
    app = create_app(repository=repo, token="read")
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            assert (
                await client.get(
                    "/v1/unit-scopes", params={"graphVersion": version, "term": "모의 1사단"}
                )
            ).status_code == 401
            headers = {"Authorization": "Bearer read"}
            scope = (
                await client.get(
                    "/v1/unit-scopes",
                    params={"graphVersion": version, "term": "모의 1사단"},
                    headers=headers,
                )
            ).json()
            assert len(scope["unitIds"]) == 3
            assert scope["graphVersion"] == version and scope["completeness"] == "complete"
            equipment = (
                await client.post(
                    "/v1/equipment-refs/query",
                    json={"graphVersion": version, "unitIds": scope["unitIds"], "kind": "tank"},
                    headers=headers,
                )
            ).json()
            assert len(equipment["items"]) == 4
            assert "availability" not in str(equipment)
            assert (
                await client.get(
                    "/v1/unit-scopes",
                    params={"graphVersion": "nonexistent", "term": "x"},
                    headers=headers,
                )
            ).status_code == 404
            assert (
                await client.get(
                    "/v1/unit-scopes",
                    params={"graphVersion": version, "term": "모의 1사단", "maxDepth": 9},
                    headers=headers,
                )
            ).status_code == 422
        with (
            server(
                "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                {"NEO4J_URI": uri, "SEMANTIC_READ_TOKEN": "read"},
            ) as api_url,
            server(
                "import uvicorn; from semantic_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                {
                    "SEMANTIC_BASE_URL": api_url,
                    "SEMANTIC_READ_TOKEN": "read",
                    "SEMANTIC_MCP_TOKEN": "mcp",
                },
            ) as mcp_url,
        ):
            async with MCPClient(mcp_url + "/mcp", "mcp") as mcp:
                assert {t["name"] for t in await mcp.list_tools()} == {
                    "interpret_concept",
                    "resolve_unit_scope",
                    "find_equipment_refs",
                    "resolve_entity",
                    "get_semantic_evidence",
                }
                result = await mcp.call(
                    "resolve_unit_scope", {"graphVersion": version, "term": "모의 1사단"}
                )
                assert result["unitIds"] == scope["unitIds"]
                resolved = await mcp.call(
                    "resolve_entity",
                    {"graphVersion": version, "systemId": "atcis", "nativeId": "U-A01"},
                )
                assert resolved["canonicalId"] == "EX-U01" and len(resolved["sourceRefs"]) == 2
                evidence = await mcp.call(
                    "get_semantic_evidence",
                    {"graphVersion": version, "evidenceId": resolved["evidenceRefs"][0]},
                )
                assert evidence["item"]["ruleId"] == "ER-EXERCISE-ID"
    finally:
        repo.remove_test_build(version)
        repo.close()
