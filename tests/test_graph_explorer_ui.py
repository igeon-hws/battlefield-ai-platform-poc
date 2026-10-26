"""Browser-only edge cases using explicitly mocked API responses."""

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import server
from playwright.async_api import async_playwright, expect


@pytest.mark.ui
async def test_explorer_distinct_version_labels_and_stale_responses():
    versions = ["domain-11111111same0000", "domain-22222222same0000"]
    builds = [
        {
            "graphVersion": v,
            "builtAt": "2026-10-26T03:00:00Z",
            "status": "READY",
            "ontologyVersion": "3.0.0",
            "inputSnapshotSet": {"atcis": {"datasetId": "c2-domain-demo-v3"}},
        }
        for v in versions
    ]
    builds.append(
        {"graphVersion": "domain-missing-meta", "status": "READY", "ontologyVersion": "3.0.0"}
    )
    waiting = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()

    with server(
        "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
        {"C4I_CONTRACT_VERSION": "3", "NEO4J_PASSWORD": "", "SEMANTIC_READ_TOKEN": ""},
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(permissions=["clipboard-read", "clipboard-write"])
            page = await context.new_page()
            page.set_default_timeout(5000)

            async def route_api(route):
                parsed = urlparse(route.request.url)
                params = parse_qs(parsed.query)
                version = params.get("graphVersion", [versions[0]])[0]
                path = parsed.path
                if path.endswith("/catalog"):
                    body = {"datasetId": "c2-domain-demo-v3"}
                elif path.endswith("/graph-builds"):
                    body = {
                        "items": [] if params.get("q") else builds,
                        "activeGraphVersion": versions[0],
                        "nextCursor": None,
                    }
                elif "/builds/" in path:
                    body = next(b for b in builds if b["graphVersion"] == path.rsplit("/", 1)[-1])
                elif path.endswith("/graph-summary"):
                    body = {
                        "build": next(b for b in builds if b["graphVersion"] == version),
                        "nodeCounts": {"Unit": 1},
                        "edgeCounts": {},
                    }
                elif path.endswith("/graph-nodes"):
                    body = {
                        "graphVersion": version,
                        "items": [{"key": "test:unit:A", "name": "테스트 객체", "label": "Unit"}],
                        "nextCursor": None,
                    }
                elif path.endswith("/graph-node"):
                    waiting.set()
                    await release.wait()
                    body = {
                        "graphVersion": version,
                        "item": {"key": "stale-old-node", "label": "Unit", "payload": {}},
                    }
                    await route.fulfill(json=body)
                    completed.set()
                    return
                elif path.endswith("/graph-neighborhood"):
                    body = {
                        "graphVersion": version,
                        "nodes": [{"key": "test:unit:A", "label": "Unit", "name": "old"}],
                        "edges": [],
                        "completeness": "complete",
                        "omittedReasons": [],
                    }
                else:
                    body = {}
                await route.fulfill(json=body)

            await page.route("**/v1/**", route_api)
            try:
                await page.goto(url)
                select = page.get_by_label("조회할 Graph 버전", exact=True)
                await expect(select).to_have_value(versions[0])
                options = await select.locator("option").all_text_contents()
                assert len(set(options)) == 4
                assert (
                    "1111same0000"
                    in await select.locator(f'option[value="{versions[0]}"]').inner_text()
                )
                assert (
                    "2222same0000"
                    in await select.locator(f'option[value="{versions[1]}"]').inner_text()
                )
                assert (
                    "정보 없음"
                    in await select.locator('option[value="domain-missing-meta"]').inner_text()
                )
                assert any(
                    "12:00:00 KST" in text and "c2-domain-demo-v3" in text for text in options
                )
                await page.get_by_role("button", name="객체 test:unit:A", exact=True).click()
                await asyncio.wait_for(waiting.wait(), 5)
                await select.select_option(versions[1])
                release.set()
                await asyncio.wait_for(completed.wait(), 5)
                await expect(select).to_have_value(versions[1])
                await expect(
                    page.get_by_text("활성 버전과 다른 버전 조회 중", exact=True)
                ).to_be_visible()
                await expect(
                    page.get_by_text("객체나 관계를 선택하세요.", exact=True)
                ).to_be_visible()
                assert await page.get_by_text("stale-old-node", exact=False).count() == 0
                assert await page.get_by_role("img", name="Graph 관계 시각화").count() == 0
                await page.get_by_label("버전 검색", exact=True).fill("not-in-this-page")
                await page.get_by_role("button", name="버전 찾기·새로고침", exact=True).click()
                await expect(select.locator("option")).to_have_count(3)
                await expect(select).to_have_value(versions[1])
                await page.get_by_role("button", name="전체 버전 ID 복사", exact=True).click()
                assert await page.evaluate("navigator.clipboard.readText()") == versions[1]
                # Graph failure must leave source/catalog navigation usable.
                await page.get_by_role("button", name="Catalog", exact=True).click()
                await page.get_by_role("button", name="조회", exact=True).click()
                await expect(page.locator("section > pre")).to_contain_text("c2-domain-demo-v3")
            finally:
                release.set()
                await browser.close()


@pytest.mark.ui
@pytest.mark.parametrize("graph_status", [200, 401, 503])
async def test_explorer_empty_or_unavailable_keeps_catalog_usable(graph_status):
    with server(
        "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
        {"C4I_CONTRACT_VERSION": "3", "NEO4J_PASSWORD": "", "SEMANTIC_READ_TOKEN": ""},
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 640, "height": 900})
            page.set_default_timeout(5000)

            async def route_api(route):
                if "/catalog" in route.request.url:
                    await route.fulfill(json={"datasetId": "c2-domain-demo-v3"})
                else:
                    await route.fulfill(
                        status=graph_status,
                        json={"items": [], "activeGraphVersion": None, "nextCursor": None},
                    )

            await page.route("**/v1/**", route_api)
            try:
                await page.goto(url)
                if graph_status == 200:
                    await expect(
                        page.get_by_text("생성된 READY Graph 없음.", exact=False)
                    ).to_be_visible()
                else:
                    await expect(page.get_by_role("alert")).to_contain_text(str(graph_status))
                await page.get_by_role("button", name="Catalog", exact=True).click()
                await page.get_by_role("button", name="조회", exact=True).click()
                await expect(page.locator("section > pre")).to_contain_text("c2-domain-demo-v3")
                assert await page.get_by_label("조회할 Graph 버전", exact=True).input_value() == ""
            finally:
                await browser.close()
