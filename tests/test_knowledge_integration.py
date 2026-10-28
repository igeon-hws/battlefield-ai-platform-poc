"""Actual v4 HTTP/MCP/Neo4j stack; no real model calls."""

import asyncio
import json
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path

import httpx
import pytest
from conftest import server
from platform_api.mcp.client import MCPClient


class CapabilityProvider:
    async def respond(self, inputs, **kwargs):
        outputs = [
            json.loads(i["output"]) for i in inputs if i.get("type") == "function_call_output"
        ]
        names = {t["name"] for t in kwargs["tools"]}
        seen = {o.get("tool") for o in outputs}
        if "atcis__list_units" not in seen:
            tool, args = "atcis__list_units", {}
        elif (
            "knowledge__get_knowledge_document" in names
            and "knowledge__get_knowledge_document" not in seen
        ):
            tool, args = "knowledge__get_knowledge_document", {"documentKey": "atcis:EX-01"}
        else:
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "outcome": "answer",
                                        "answer": "Capability integration test; not a domain accuracy measurement.",
                                        "findings": [],
                                        "claims": [],
                                        "evidenceIds": [o["evidenceId"] for o in outputs],
                                        "limitations": ["test provider"],
                                        "courses": None,
                                    }
                                ),
                            }
                        ],
                    }
                ],
            }
        return {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": tool,
                    "call_id": "test-" + str(len(outputs)),
                    "arguments": json.dumps(args),
                }
            ],
        }


@contextmanager
def v4_stack(
    tmp_path,
    graph=False,
    version="4",
    provider_module="test_knowledge_integration",
    provider_class="CapabilityProvider",
    knowledge=True,
):
    from dotenv import load_dotenv

    load_dotenv()
    systems = ("atcis", "knccs", "logistics") if version == "5" else ("atcis", "knccs")
    with ExitStack() as stack:
        env = {
            "C4I_CONTRACT_VERSION": version,
            "BUILDER_GRAPH_PREFIX": "test-",
            "SEMANTIC_READ_TOKEN": "",
            "SEMANTIC_MCP_TOKEN": "",
            "KNOWLEDGE_MCP_TOKEN": "",
            "BUILDER_ADMIN_TOKEN": "test-admin",
            "PYTHONPATH": str(Path(__file__).parent.resolve()),
            "AGENT_LOG_ENABLED": "false",
        }
        for system in systems:
            env[system.upper() + "_READ_TOKEN"] = ""
            env[system.upper() + "_CONTROL_TOKEN"] = ""
            env[system.upper() + "_MCP_TOKEN"] = ""
            env[system.upper() + "_DB"] = str(tmp_path / (system + ".db"))
            env[system.upper() + "_BASE_URL"] = stack.enter_context(
                server(
                    f"import uvicorn; from mock_{system}.{'app' if system == 'logistics' else 'native'} import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
                    env,
                )
            )
            env[system.upper() + "_MCP_URL"] = (
                stack.enter_context(
                    server(
                        f"import uvicorn; from {'mock_logistics.mcp' if system == 'logistics' else system + '_mcp.server'} import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                        env,
                    )
                )
                + "/mcp"
            )
        if not graph:
            env["NEO4J_PASSWORD"] = ""
        else:
            env["NEO4J_URI"] = os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687")
        env["SEMANTIC_BASE_URL"] = stack.enter_context(
            server(
                "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                env | {"BUILDER_BASE_URL": "http://127.0.0.1:1"},
            )
        )
        if graph:
            # Builder reads knowledge from the first independent Fabric read API;
            # the second Fabric coordinates managed builds. Both pin identical sets.
            env["BUILDER_BASE_URL"] = stack.enter_context(
                server(
                    "import uvicorn; from graph_builder.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                    env,
                )
            )
            env["SEMANTIC_BASE_URL"] = stack.enter_context(
                server(
                    "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                    env,
                )
            )
        if knowledge:
            env["KNOWLEDGE_MCP_URL"] = (
                stack.enter_context(
                    server(
                        "import uvicorn; from semantic_mcp.knowledge import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                        env,
                    )
                )
                + "/mcp"
            )
        else:
            env["KNOWLEDGE_MCP_URL"] = "http://127.0.0.1:1/mcp"
        if version == "5" and not graph:
            env["SEMANTIC_MCP_URL"] = "http://127.0.0.1:1/mcp"
        else:
            env["SEMANTIC_MCP_URL"] = (
                stack.enter_context(
                    server(
                        "import uvicorn; from semantic_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                        env,
                    )
                )
                + "/mcp"
            )
        env["PLATFORM_VNEXT_DB"] = str(tmp_path / "platform.db")
        platform = stack.enter_context(
            server(
                f"import uvicorn; from platform_api.app import create_app; from {provider_module} import {provider_class}; uvicorn.run(create_app(profile='heterogeneous',provider={provider_class}()),host='127.0.0.1',port=PORT,log_level='error')",
                env,
            )
        )
        try:
            yield platform, env
        finally:
            stack.close()
            if graph:
                from battlefield_ontology import digest
                from semantic_core.graph import GraphRepository

                repo = GraphRepository(env["NEO4J_URI"], "neo4j", os.environ["NEO4J_PASSWORD"])
                scope = digest({s: env[s.upper() + "_BASE_URL"].rstrip("/") for s in systems})
                for row in repo.query(
                    "MATCH (r:BuildRequest {sourceScope:$scope}) WHERE r.graphVersion STARTS WITH 'test-' RETURN DISTINCT r.graphVersion AS v",
                    scope=scope,
                ):
                    repo.remove_test_build(row["v"])
                repo.query("MATCH (r:BuildRequest {sourceScope:$scope}) DELETE r", scope=scope)
                repo.query(
                    "MATCH (s:GraphState {id:$id}) DELETE s", id="source-checkpoints-" + scope
                )
                repo.close()


async def wait_run(client, rid):
    # Service preparation is outside the 120-second Agent loop budget.
    for _ in range(1800):
        run = (await client.get("/api/v1/analyses/" + rid)).json()
        if run["status"] not in ("queued", "running"):
            return run
        await asyncio.sleep(0.1)
    raise AssertionError("run did not finish")


async def test_v4_native_and_documents_actual_mcp_without_neo4j(tmp_path):
    with v4_stack(tmp_path) as (url, env):
        async with MCPClient(env["ATCIS_MCP_URL"]) as mcp:
            assert "list_documents" not in {d["name"] for d in await mcp.list_tools()}
        async with httpx.AsyncClient(base_url=url, timeout=15) as client:
            assert (
                await client.post(
                    "/api/v1/analyses", json={"question": "test", "semanticMode": "off"}
                )
            ).status_code == 422
            results = []
            for mode in ("native", "documents"):
                response = await client.post(
                    "/api/v1/analyses",
                    json={"question": "test capabilities", "knowledgeMode": mode},
                )
                assert response.status_code == 202, response.text
                results.append(await wait_run(client, response.json()["runId"]))
            a, b = results
            assert a["status"] == b["status"] == "completed", results
            assert not any(t["name"].startswith("knowledge__") for t in a["toolCalls"])
            assert any(t["name"] == "knowledge__get_knowledge_document" for t in b["toolCalls"])
            assert a["graphInfo"] is None and b["graphInfo"] is None
            assert "knowledgeSetVersion" not in a["sourceContext"]
            assert (
                await client.post(
                    "/api/v1/analyses",
                    json={
                        "question": "switch",
                        "knowledgeMode": "documents",
                        "conversationId": a["conversationId"],
                    },
                )
            ).status_code == 409


@pytest.mark.neo4j
@pytest.mark.ui
async def test_v4_abc_shared_context_and_graph_knowledge_provenance(tmp_path):
    with v4_stack(tmp_path, graph=True) as (url, env):
        async with httpx.AsyncClient(base_url=url, timeout=50) as client:
            comparison = (
                await client.post("/api/v1/comparisons", json={"question": "test same snapshots"})
            ).json()
            # Three sequential 120-second loops plus shared service preparation.
            for _ in range(4500):
                item = (
                    await client.get("/api/v1/comparisons/" + comparison["comparisonId"])
                ).json()
                if item["status"] not in ("preparing", "running"):
                    break
                await asyncio.sleep(0.1)
            assert item["status"] == "completed", item
            runs = [
                (await client.get("/api/v1/analyses/" + item["runIds"][m])).json()
                for m in ("native", "documents", "structured")
            ]
            assert len({r["conversationId"] for r in runs}) == 3
            assert all(
                r["sourceSnapshotSet"] == item["manifest"]["sourceSnapshotSet"] for r in runs
            )
            assert (
                runs[1]["knowledgeSetHash"]
                == runs[2]["knowledgeSetHash"]
                == runs[2]["graphInfo"]["knowledgeSetHash"]
            )
            assert any(n.startswith("semantic__") for n in runs[2]["registryBindings"])
            async with MCPClient(env["SEMANTIC_MCP_URL"]) as mcp:
                data = await mcp.call(
                    "interpret_concept",
                    {"graphVersion": runs[2]["graphInfo"]["graphVersion"], "term": "all"},
                )
                assert data["ontologyVersion"] == "4.0.0"
                assert "knowledgeSetVersion" in json.dumps(data)
            from playwright.async_api import async_playwright, expect

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 960})
                page.set_default_timeout(30000)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.get_by_role("button", name="대화 이력 열기", exact=True).click()
                    await page.get_by_role(
                        "button", name="completed · test same snapshots", exact=True
                    ).click()
                    await expect(
                        page.get_by_role(
                            "heading", name="A/B/C 동일 기준 비교 · completed", exact=True
                        )
                    ).to_be_visible()
                    assert await page.locator(".knowledge-columns .next-run").count() == 3
                    canvas = page.locator(".map-canvas canvas")
                    await canvas.evaluate("el => el.dataset.comparisonIdentity = 'persistent'")
                    await page.get_by_role("button", name="비교 확대", exact=True).click()
                    enlarged = page.get_by_role("dialog", name="A/B/C 비교 확대", exact=True)
                    await expect(enlarged).to_be_visible()
                    assert await enlarged.locator(".next-run").count() == 3
                    await page.screenshot(path="artifacts/knowledge-comparison-expanded-v4.png")
                    await page.get_by_role("button", name="비교 확대 닫기", exact=True).click()
                    assert await canvas.get_attribute("data-comparison-identity") == "persistent"
                    await page.screenshot(
                        path="artifacts/knowledge-comparison-v4.png", full_page=True
                    )
                    await page.set_viewport_size({"width": 640, "height": 900})
                    await page.get_by_role(
                        "button", name="C · 원천 + 구조화 지식", exact=True
                    ).click()
                    await expect(
                        page.locator(".knowledge-columns > .mobile-current")
                    ).to_contain_text("Capability integration test")
                    await page.goto(
                        env["SEMANTIC_BASE_URL"], wait_until="domcontentloaded", timeout=30000
                    )
                    await page.get_by_role("button", name="Graph 탐색", exact=True).click()
                    await page.get_by_label("조회할 Graph 버전", exact=True).select_option(
                        runs[2]["graphInfo"]["graphVersion"]
                    )
                    await page.get_by_label("객체 검색", exact=True).fill("atcis:report:R2")
                    await page.get_by_role("button", name="객체 찾기", exact=True).click()
                    await page.get_by_role(
                        "button", name="객체 atcis:report:R2", exact=True
                    ).click()
                    await page.get_by_text("관계 목록 · 키보드로 선택", exact=True).click()
                    await page.get_by_role("button", name="관계 상세").first.click()
                    await page.get_by_role(
                        "button", name="Fabric 지식 atcis:SOP-01 보기", exact=True
                    ).click()
                    await expect(
                        page.get_by_role("heading", name="atcis:SOP-01", exact=True)
                    ).to_be_visible()
                    assert (
                        await page.get_by_label("지식 집합 버전", exact=True).input_value()
                        == runs[2]["knowledgeSetVersion"]
                    )
                finally:
                    await browser.close()


@pytest.mark.ui
async def test_v4_platform_and_fabric_ui(tmp_path):
    from playwright.async_api import async_playwright, expect

    with v4_stack(tmp_path) as (url, env):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(30000)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.get_by_label("지식 제공 방식", exact=True).select_option("documents")
                await page.get_by_label("분석 질의", exact=True).fill("test knowledge capabilities")
                await page.get_by_role("button", name="분석 실행", exact=True).click()
                await expect(
                    page.get_by_text(
                        "Capability integration test; not a domain accuracy measurement.",
                        exact=True,
                    )
                ).to_be_visible(timeout=180000)
                Path("artifacts").mkdir(exist_ok=True)
                await page.screenshot(path="artifacts/knowledge-platform-v4.png", full_page=True)
                await page.goto(
                    env["SEMANTIC_BASE_URL"], wait_until="domcontentloaded", timeout=30000
                )
                await page.get_by_role("button", name="지식 문서", exact=True).click()
                await page.get_by_role("button", name="문서 atcis:EX-01", exact=True).click()
                await expect(
                    page.get_by_role("paragraph").filter(has_text="TK=전차")
                ).to_be_visible()
                await page.set_viewport_size({"width": 640, "height": 900})
                await page.screenshot(
                    path="artifacts/knowledge-fabric-v4-mobile.png", full_page=True
                )
            finally:
                await browser.close()
