"""V5 actual public HTTP/MCP/Neo4j integration; deterministic test provider."""

import asyncio
import json

import httpx
import pytest
from test_knowledge_integration import CapabilityProvider, v4_stack, wait_run


class LogisticsProvider(CapabilityProvider):
    async def respond(self, inputs, **kwargs):
        outputs = [
            json.loads(i["output"]) for i in inputs if i.get("type") == "function_call_output"
        ]
        seen = {o.get("tool") for o in outputs}
        for name, args in [("logistics__list_inventory", {}), ("knccs__list_transports", {})]:
            if name not in seen:
                return {
                    "status": "completed",
                    "output": [
                        {
                            "type": "function_call",
                            "name": name,
                            "call_id": "log-" + str(len(outputs)),
                            "arguments": json.dumps(args),
                        }
                    ],
                }
        if (
            "semantic__resolve_entity" in {t["name"] for t in kwargs["tools"]}
            and "semantic__resolve_entity" not in seen
        ):
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "name": "semantic__resolve_entity",
                        "call_id": "identity",
                        "arguments": json.dumps({"systemId": "logistics", "nativeId": "EQ-781"}),
                    }
                ],
            }
        return await super().respond(inputs, **kwargs)


@pytest.mark.neo4j
async def test_v5_transport_reference_and_dependency_are_available_over_mcp(tmp_path):
    from platform_api.mcp.client import MCPClient

    with v4_stack(tmp_path, graph=True, version="5") as (url, env):
        async with httpx.AsyncClient(base_url=url, timeout=60) as c:
            session = (await c.post("/api/v1/demo-sessions", json={"mode": "structured"})).json()
            detail = await c.post(
                "/api/v1/objects/detail",
                headers={"x-demo-session": session["sessionId"]},
                json={"systemId": "atcis", "recordType": "equipment", "nativeId": "L-T02"},
            )
            assert detail.status_code == 200, detail.text
            version = detail.json()["graphVersion"]
        async with MCPClient(env["SEMANTIC_MCP_URL"]) as mcp:
            resolved = await mcp.call(
                "resolve_entity", {"graphVersion": version, "systemId": "knccs", "nativeId": "N-21"}
            )
            assert resolved["canonicalId"] == "knccs:transport:N-21"
            related = await mcp.call(
                "query_relations",
                {
                    "graphVersion": version,
                    "subject": resolved["canonicalId"],
                    "relationTypes": ["CARRIED_BY", "FULFILLED_BY"],
                    "depth": 2,
                },
            )
            assert any(e["kind"] == "CARRIED_BY" for e in related["items"])


@pytest.mark.parametrize("mode", ["native", "documents"])
async def test_v5_a_b_without_semantic_services(tmp_path, mode):
    with v4_stack(
        tmp_path,
        version="5",
        knowledge=mode != "native",
        provider_module="test_logistics_integration",
        provider_class="LogisticsProvider",
    ) as (url, _env):
        async with httpx.AsyncClient(base_url=url, timeout=60) as c:
            session = (await c.post("/api/v1/demo-sessions", json={"mode": mode})).json()
            c.headers["x-demo-session"] = session["sessionId"]
            r = await c.post(
                "/api/v1/analyses", json={"question": "test source access", "knowledgeMode": mode}
            )
            assert r.status_code == 202, r.text
            run = await wait_run(c, r.json()["runId"])
            assert run["status"] == "completed", run.get("error")
            assert set(run["sourceSnapshotSet"]) == {"atcis", "knccs", "logistics"}
            assert not any(n.startswith("semantic__") for n in run["registryBindings"])
            if mode == "native":
                assert not any(n.startswith("knowledge__") for n in run["registryBindings"])


@pytest.mark.neo4j
@pytest.mark.ui
async def test_v5_actual_three_sources_detail_and_comparison(tmp_path):
    with v4_stack(
        tmp_path,
        graph=True,
        version="5",
        provider_module="test_logistics_integration",
        provider_class="LogisticsProvider",
    ) as (url, env):
        async with httpx.AsyncClient(base_url=url, timeout=60) as c:
            sessions = {
                m: (await c.post("/api/v1/demo-sessions", json={"mode": m})).json()["sessionId"]
                for m in ("native", "documents", "structured", "compare")
            }
            headers = lambda m: {"x-demo-session": sessions[m]}
            for m in ("native", "documents"):
                r = await c.post(
                    "/api/v1/analyses",
                    json={"question": "test v5 sources", "knowledgeMode": m},
                    headers=headers(m),
                )
                assert r.status_code == 202, r.text
                c.headers.update(headers(m))
                run = await wait_run(c, r.json()["runId"])
                assert run["status"] == "completed", run.get("error")
                assert run["sourceSnapshotSet"].keys() == {"atcis", "knccs", "logistics"}
                assert "logistics__list_inventory" in run["registryBindings"]
                assert not any(n.startswith("semantic__") for n in run["registryBindings"])
                assert (
                    not any(n.startswith("knowledge__") for n in run["registryBindings"])
                    if m == "native"
                    else True
                )
            detail = await c.post(
                "/api/v1/objects/detail",
                json={"systemId": "atcis", "recordType": "equipment", "nativeId": "L-T02"},
                headers=headers("structured"),
            )
            assert detail.status_code == 200, detail.text
            d = detail.json()
            assert d["identityStatus"] == "resolved"
            assert any(r["record"].get("transportId") == "N-21" for r in d["records"])
            assert all(r["sourceTime"] and r["lastReceivedAt"] for r in d["records"])
            comp = await c.post(
                "/api/v1/comparisons",
                json={"question": "test v5 comparison"},
                headers=headers("compare"),
            )
            assert comp.status_code == 202, comp.text
            for _ in range(1800):
                comparison = (
                    await c.get(
                        "/api/v1/comparisons/" + comp.json()["comparisonId"],
                        headers=headers("compare"),
                    )
                ).json()
                if comparison["status"] in ("completed", "incomplete", "failed"):
                    break
                await asyncio.sleep(0.1)
            assert comparison["status"] == "completed", comparison
            runs = [
                (await c.get("/api/v1/analyses/" + r, headers=headers("compare"))).json()
                for r in comparison["runIds"].values()
            ]
            assert all(r["sourceSnapshotSet"] == runs[0]["sourceSnapshotSet"] for r in runs)
            assert (
                runs[1]["knowledgeSetHash"] == runs[2]["knowledgeSetHash"] == d["knowledgeSetHash"]
            )
            from pathlib import Path

            from playwright.async_api import async_playwright, expect

            Path("artifacts").mkdir(exist_ok=True)
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                try:
                    await page.goto(url + "/demo/c", wait_until="domcontentloaded")
                    await page.get_by_role("button", name="객체 목록", exact=True).click()
                    await page.locator(".bf-object-rows button").filter(has_text="L-T02").click()
                    panel = page.get_by_label("구조화 객체 상세", exact=True)
                    await expect(panel).to_contain_text("M-17", timeout=60000)
                    await expect(panel).to_contain_text("N-21")
                    await page.screenshot(path="artifacts/logistics-v5-c-desktop.png")
                    await panel.get_by_text("연결 규칙·근거·버전", exact=False).click()
                    await panel.get_by_role(
                        "button", name="근거 문서 logistics:LOG-01", exact=True
                    ).first.click()
                    await expect(page.get_by_label("Fabric 문서", exact=True)).to_contain_text(
                        "LOG-LINK-01"
                    )
                    await page.set_viewport_size({"width": 390, "height": 844})
                    await page.screenshot(path="artifacts/logistics-v5-c-mobile.png")
                    await page.goto(url + "/demo/compare", wait_until="domcontentloaded")
                    await page.get_by_role("button", name="대화 이력 열기", exact=True).click()
                    await page.get_by_role(
                        "button", name="completed · test v5 comparison", exact=True
                    ).click()
                    await expect(
                        page.get_by_role(
                            "heading", name="A/B/C 동일 기준 비교 · completed", exact=True
                        )
                    ).to_be_visible()
                    await page.get_by_role("button", name="비교 확대", exact=True).click()
                    await expect(
                        page.get_by_role("dialog", name="A/B/C 비교 확대", exact=True)
                    ).to_be_visible()
                    await page.screenshot(path="artifacts/logistics-v5-comparison-mobile.png")
                    await page.goto(url + "/demo/a", wait_until="domcontentloaded")
                    await expect(page.get_by_label("구조화 객체 상세", exact=True)).to_have_count(0)
                    await expect(
                        page.get_by_role("button", name="지식 문서 열기", exact=True)
                    ).to_have_count(0)
                    await page.get_by_role("button", name="원천 기록 탐색", exact=True).click()
                    await page.get_by_role("button", name="원천 조회", exact=True).click()
                    await expect(
                        page.get_by_role("complementary", name="원천 기록 탐색", exact=True)
                    ).to_contain_text("EQ-781")
                    await page.screenshot(path="artifacts/logistics-v5-a-mobile.png")
                    await page.goto(env["LOGISTICS_BASE_URL"], wait_until="domcontentloaded")
                    await expect(
                        page.get_by_role("heading", name="Mock LOGISTICS", exact=True)
                    ).to_be_visible()
                    await page.get_by_role("button", name="work-orders", exact=True).click()
                    await page.get_by_role("button", name="M-17", exact=True).click()
                    await expect(
                        page.get_by_role("heading", name="원천 레코드", exact=True)
                    ).to_be_visible()
                finally:
                    await browser.close()
