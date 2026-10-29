from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect
from test_workspace_ui import mock_api, ui_server


@pytest.mark.ui
async def test_c_detail_leads_with_business_information_and_hides_diagnostics():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await mock_api(page)
            await page.route(
                "**/api/v1/config", lambda r: r.fulfill(json={"sourceToolContractVersion": "5"})
            )
            await page.route(
                "**/api/v1/demo-sessions", lambda r: r.fulfill(json={"sessionId": "test"})
            )
            await page.route(
                "**/api/v1/objects/detail",
                lambda r: r.fulfill(
                    json={
                        "identityStatus": "resolved",
                        "graphVersion": "test-sensitive-graph",
                        "records": [],
                        "links": [],
                        "coverage": {"atcis": "complete"},
                        "metadata": {"available": True},
                        "business": {
                            "asset": {
                                "name": "전차",
                                "status": "운용 제한",
                                "unit": "모의 해안중대",
                                "limitation": "정기 점검 필요",
                            },
                            "maintenance": [
                                {
                                    "id": "M-17",
                                    "status": "부품 대기",
                                    "durationHours": 4,
                                    "durationUnit": "h",
                                    "requirements": [
                                        {"partId": "P-08", "quantity": 2, "unit": "EA"}
                                    ],
                                    "otherFaults": "추가 고장 없음",
                                }
                            ],
                            "inventory": [],
                            "transport": [],
                            "sourceTimes": [
                                {
                                    "source": "atcis",
                                    "sourceTime": "2026-10-20T09:10:00Z",
                                    "lastReceivedAt": "2026-10-28T00:00:00Z",
                                }
                            ],
                            "queriedAt": "2026-10-28T00:00:01Z",
                        },
                    }
                ),
            )
            try:
                await page.goto(url + "/demo/c", wait_until="domcontentloaded")
                await page.get_by_role("button", name="객체 목록", exact=True).click()
                await page.locator(".bf-object-rows button").filter(has_text="L-T01").click()
                panel = page.get_by_label("구조화 객체 상세", exact=True)
                await expect(panel.get_by_text("운용 제한", exact=True)).to_be_visible()
                await expect(panel.get_by_text("부품 대기", exact=True)).to_be_visible()
                await expect(panel.get_by_text("test-sensitive-graph", exact=False)).to_be_hidden()
                await expect(panel.get_by_text("이번 조회 완료", exact=False)).to_be_visible()
                Path("artifacts/business-ui").mkdir(parents=True, exist_ok=True)
                for width, height in [
                    (1440, 900),
                    (1280, 800),
                    (1024, 768),
                    (640, 900),
                    (390, 844),
                    (1024, 500),
                ]:
                    await page.set_viewport_size({"width": width, "height": height})
                    await expect(panel.get_by_role("button", name="통합 상세 닫기")).to_be_visible()
                    bounds = await panel.bounding_box()
                    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
                    await page.screenshot(path=f"artifacts/business-ui/c-{width}-{height}.png")
            finally:
                await browser.close()


@pytest.mark.ui
@pytest.mark.parametrize("mode", ["a", "b", "c"])
async def test_semantic_scene_is_explicit_and_c_only(mode):
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await mock_api(page)
            await page.route(
                "**/api/v1/config", lambda r: r.fulfill(json={"sourceToolContractVersion": "5"})
            )
            await page.route(
                "**/api/v1/demo-sessions", lambda r: r.fulfill(json={"sessionId": "test"})
            )
            calls = []

            async def scene(route):
                calls.append(route.request.post_data_json)
                await route.fulfill(
                    json={
                        "graphVersion": "g1",
                        "counts": {
                            "observations": 10,
                            "canonicalAssets": 6,
                            "unresolvedObservations": 2,
                        },
                        "observations": [],
                        "groups": [],
                        "stale": False,
                    }
                )

            await page.route("**/api/v1/semantic-map", scene)
            try:
                await page.goto(url + "/demo/" + mode, wait_until="domcontentloaded")
                toggle = page.get_by_role("button", name="의미 객체 보기", exact=True)
                if mode == "c":
                    await toggle.click()
                    await expect(page.get_by_label("검증된 관측 연결")).to_contain_text(
                        "고유 자산 6"
                    )
                    assert len(calls) == 1
                    await page.get_by_role("button", name="원천 관측 보기", exact=True).click()
                    await expect(page.get_by_label("검증된 관측 연결")).to_have_count(0)
                else:
                    await expect(toggle).to_have_count(0)
                    assert not calls
            finally:
                await browser.close()
