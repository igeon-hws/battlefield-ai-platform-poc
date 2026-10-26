"""Explorer contracts against an actual, isolated Neo4j build."""

from uuid import uuid4

import httpx
import pytest
from semantic_api.app import create_app
from test_domain_semantics import exports
from test_neo4j import graph  # noqa: F401

pytestmark = pytest.mark.neo4j


async def test_explorer_version_search_neighborhood_and_evidence(graph, monkeypatch):  # noqa: F811
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "3")
    version = "test-explorer-" + uuid4().hex
    graph.build(exports(), graph_version=version)
    app = create_app(repository=graph, token="read")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            assert (await c.get("/v1/graph-builds")).status_code == 401
            c.headers["Authorization"] = "Bearer read"
            builds = (await c.get("/v1/graph-builds", params={"q": version})).json()
            assert builds["items"][0]["graphVersion"] == version
            assert builds["items"][0]["inputSnapshotSet"]
            summary = (await c.get("/v1/graph-summary", params={"graphVersion": version})).json()
            assert summary["nodeCounts"]["Unit"] == 5
            nodes = (
                await c.get(
                    "/v1/graph-nodes", params={"graphVersion": version, "type": "Unit", "limit": 2}
                )
            ).json()
            assert len(nodes["items"]) == 2 and nodes["nextCursor"]
            assert (
                await c.get(
                    "/v1/graph-nodes",
                    params={"graphVersion": version, "q": "changed", "cursor": nodes["nextCursor"]},
                )
            ).status_code == 422
            second = (
                await c.get(
                    "/v1/graph-nodes",
                    params={
                        "graphVersion": version,
                        "type": "Unit",
                        "limit": 2,
                        "cursor": nodes["nextCursor"],
                    },
                )
            ).json()
            assert not {n["key"] for n in nodes["items"]} & {n["key"] for n in second["items"]}
            detail = (
                await c.get(
                    "/v1/graph-node", params={"graphVersion": version, "nodeKey": "atcis:report:R2"}
                )
            ).json()
            assert detail["item"]["key"] == "atcis:report:R2"
            params = {
                "graphVersion": version,
                "subject": "atcis:report:R2",
                "relationTypes": "DERIVED_FROM",
                "depth": 1,
            }
            neighborhood = (await c.get("/v1/graph-neighborhood", params=params)).json()
            keys = {n["key"] for n in neighborhood["nodes"]}
            assert "atcis:report:R1" in keys
            assert all(e["start"] in keys and e["end"] in keys for e in neighborhood["edges"])
            assert neighborhood["edges"][0]["evidenceId"]
            small = (await c.get("/v1/graph-neighborhood", params=params | {"nodeLimit": 1})).json()
            assert small["completeness"] == "partial" and not small["edges"]
            assert (
                await c.get("/v1/graph-neighborhood", params=params | {"depth": 3})
            ).status_code == 422
            assert (
                await c.get("/v1/graph-neighborhood", params=params | {"relationTypes": "INJECT"})
            ).status_code == 422
            assert (
                await c.get("/v1/graph-summary", params={"graphVersion": "missing"})
            ).status_code == 404
    finally:
        graph.remove_test_build(version)


@pytest.mark.ui
async def test_explorer_ui_search_select_and_follow_provenance(graph):  # noqa: F811
    import os
    from pathlib import Path

    from conftest import server
    from playwright.async_api import async_playwright

    version = "test-explorer-ui-" + uuid4().hex
    graph.build(exports(), graph_version=version)
    try:
        with server(
            "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
            {
                "C4I_CONTRACT_VERSION": "3",
                "NEO4J_URI": os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687"),
                "SEMANTIC_READ_TOKEN": "",
            },
        ) as url:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 960})
                page.set_default_timeout(5000)
                try:
                    await page.goto(url)
                    await page.get_by_role("button", name="Graph 탐색", exact=True).click()
                    await page.get_by_label("조회할 Graph 버전", exact=True).select_option(version)
                    await page.get_by_label("객체 검색", exact=True).fill("atcis:report:R2")
                    await page.get_by_role("button", name="객체 찾기", exact=True).click()
                    await page.get_by_role(
                        "button", name="객체 atcis:report:R2", exact=True
                    ).click()
                    await page.get_by_role("img", name="Graph 관계 시각화", exact=True).wait_for()
                    await page.get_by_text("관계 목록 · 키보드로 선택", exact=True).click()
                    await page.get_by_role("button", name="관계 상세").first.click()
                    await page.get_by_role("button", name="근거 조회", exact=True).click()
                    await page.get_by_text("근거 응답", exact=True).wait_for()
                    Path("artifacts").mkdir(exist_ok=True)
                    await page.screenshot(
                        path="artifacts/fabric-explorer-desktop.png", full_page=True
                    )
                    await page.set_viewport_size({"width": 640, "height": 900})
                    await page.screenshot(
                        path="artifacts/fabric-explorer-mobile.png", full_page=True
                    )
                    assert (
                        await page.get_by_label("조회할 Graph 버전", exact=True).input_value()
                        == version
                    )
                    await page.get_by_role(
                        "button", name="규칙 REPORT-LINEAGE-01 보기", exact=True
                    ).click()
                    await page.get_by_role("heading", name="도메인 규칙", exact=True).wait_for()
                    await page.get_by_role("button", name="조회", exact=True).click()
                    await page.locator("section > pre").filter(has_text=version).wait_for()
                    await page.get_by_role("button", name="Graph 탐색", exact=True).click()
                    await page.get_by_role(
                        "button", name="원천 문서 atcis · SOP-01 보기", exact=True
                    ).click()
                    await page.get_by_text("객체 ID · atcis:document:SOP-01", exact=True).wait_for()
                finally:
                    await browser.close()
    finally:
        graph.remove_test_build(version)


async def test_explorer_bounds_versions_and_build_paging(graph, monkeypatch):  # noqa: F811
    import json
    from time import perf_counter

    from semantic_core.explorer import GraphExplorer

    monkeypatch.setenv("C4I_CONTRACT_VERSION", "3")
    versions = ["test-explorer-paging-" + uuid4().hex for _ in range(2)]
    try:
        for v in versions:
            graph.build(exports(), graph_version=v)
        explorer = GraphExplorer(graph)
        # Explorer must not call the historical whole-model path.
        monkeypatch.setattr(
            "semantic_core.domain.DomainService.model", lambda *_: pytest.fail("whole graph loaded")
        )
        first = explorer.builds(q="test-explorer-paging-", limit=1)
        versions.append("test-explorer-paging-" + uuid4().hex)
        graph.build(exports(), graph_version=versions[-1])
        second = explorer.builds(q="test-explorer-paging-", limit=1, cursor=first["nextCursor"])
        assert first["items"][0]["graphVersion"] != second["items"][0]["graphVersion"]
        assert len(explorer.nodes(versions[0], kind="Unit")["items"]) == 5
        cursor = explorer.nodes(versions[0], limit=1)["nextCursor"]
        with pytest.raises(ValueError):
            explorer.nodes(versions[1], limit=1, cursor=cursor)
        assert explorer.nodes(versions[1], q="no-such-native-record")["items"] == []
        # Add a star and isolated/self/parallel relations only to this disposable build.
        v = versions[0]
        fixture_nodes = [
            {"key": f"test:{i}", "label": "Unit", "payload": {"name": f"fixture {i}"}}
            for i in range(210)
        ]
        graph.query(
            "UNWIND $items AS item CREATE (n:SemanticNode:Unit {graphVersion:$v,nodeKey:item.key,domainJson:item.body})",
            v=v,
            items=[{"key": n["key"], "body": json.dumps(n)} for n in fixture_nodes],
        )
        fixture_edges = [
            {
                "start": "test:0",
                "end": f"test:{i}",
                "kind": "REFERS_TO",
                "evidenceId": f"test-proof-{i}",
            }
            for i in range(209)
        ]
        fixture_edges.append(
            {
                "start": "test:0",
                "end": "test:1",
                "kind": "REFERS_TO",
                "evidenceId": "parallel-proof",
            }
        )
        graph.query(
            "UNWIND $items AS item MATCH (a:SemanticNode {graphVersion:$v,nodeKey:item.start}), (b:SemanticNode {graphVersion:$v,nodeKey:item.end}) CREATE (a)-[:REFERS_TO {domainJson:item.body,assertionId:item.id}]->(b)",
            v=v,
            items=[
                {"start": e["start"], "end": e["end"], "id": e["evidenceId"], "body": json.dumps(e)}
                for e in fixture_edges
            ],
        )
        started = perf_counter()
        small = explorer.neighborhood(v, "test:0", "REFERS_TO", 1, 200, 300)
        print(
            f"synthetic neighborhood: {perf_counter() - started:.3f}s, {len(json.dumps(small).encode())} bytes, {len(small['nodes'])} nodes/{len(small['edges'])} edges"
        )
        assert len(small["nodes"]) == 200 and small["completeness"] == "partial"
        assert "nodeLimit" in small["omittedReasons"]
        keys = {n["key"] for n in small["nodes"]}
        assert all(e["start"] in keys and e["end"] in keys for e in small["edges"])
        assert any(e["start"] == e["end"] for e in small["edges"])
        assert len([e for e in small["edges"] if e["end"] == "test:1"]) == 2
        isolated = explorer.neighborhood(v, "test:209", "REFERS_TO")
        assert (
            len(isolated["nodes"]) == 1
            and not isolated["edges"]
            and isolated["completeness"] == "complete"
        )
        assert len(explorer.neighborhood(v, "test:0", "REFERS_TO", edge_limit=2)["edges"]) == 2
        graph.query("MATCH (b:GraphBuild {graphVersion:$v}) SET b.status='BUILDING'", v=v)
        with pytest.raises(ValueError):
            explorer.summary(v)
    finally:
        for v in versions:
            graph.remove_test_build(v)
