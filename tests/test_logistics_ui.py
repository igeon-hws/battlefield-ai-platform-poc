"""V5 entry and capability presentation over the built UI (mock HTTP)."""

import pytest
from conftest import server
from playwright.async_api import async_playwright, expect
from test_workspace_ui import mock_api, ui_server


@pytest.mark.ui
async def test_v5_entry_and_mode_fixed_pages():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            await mock_api(page)
            await page.route(
                "**/api/v1/config",
                lambda r: r.fulfill(
                    json={"sourceToolContractVersion": "5", "fabricUrl": "http://localhost:4400"}
                ),
            )
            await page.route(
                "**/api/v1/demo-sessions",
                lambda r: r.fulfill(
                    json={"sessionId": "test", "mode": r.request.post_data_json["mode"]}
                ),
            )
            try:
                await page.goto(url)
                await expect(
                    page.get_by_role("heading", name="지식 제공 조건을 선택하세요", exact=True)
                ).to_be_visible()
                await page.get_by_role("link", name="A · 원천 데이터로 진입", exact=True).click()
                await expect(
                    page.get_by_role("region", name="전장 상황판", exact=True)
                ).to_be_visible()
                await expect(page.get_by_label("지식 제공 방식", exact=True)).to_have_count(0)
                await expect(
                    page.get_by_role("button", name="원천 기록 탐색", exact=True)
                ).to_be_visible()
                await expect(
                    page.get_by_role("button", name="지식 문서 열기", exact=True)
                ).to_have_count(0)
                await page.get_by_role("link", name="조건 선택으로", exact=True).click()
                await page.get_by_role("link", name="B · 문서 지식으로 진입", exact=True).click()
                await expect(
                    page.get_by_role("button", name="지식 문서 열기", exact=True)
                ).to_be_visible()
            finally:
                await browser.close()


@pytest.mark.ui
async def test_standalone_logistics_control_refreshes_selected_record(tmp_path):
    with server(
        "import uvicorn; from mock_logistics.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
        {
            "LOGISTICS_DB": str(tmp_path / "ui.db"),
            "LOGISTICS_READ_TOKEN": "",
            "LOGISTICS_CONTROL_TOKEN": "",
        },
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.get_by_role("button", name="정비 작업", exact=True).click()
                await page.get_by_role("button", name="M-17", exact=True).click()
                await page.get_by_label("정비 상태 변경", exact=True).select_option("DONE")
                await expect(
                    page.locator("article dd").filter(has_text="정비 완료")
                ).to_be_visible()
                await page.get_by_text("전체 원본 기록·식별자", exact=True).click()
                await expect(page.locator(".fabric-grid article pre")).to_contain_text(
                    '"status": "DONE"'
                )
            finally:
                await browser.close()
