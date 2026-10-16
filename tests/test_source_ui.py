import pytest
from conftest import server
from playwright.async_api import async_playwright


@pytest.mark.ui
@pytest.mark.parametrize("system,entity", [("atcis", "T-A01"), ("knccs", "V-K01")])
async def test_source_ui_standalone_map_and_controls(tmp_path, system, entity):
    with server(
        f"import uvicorn; from mock_{system}.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
        {
            f"{system.upper()}_DB": str(tmp_path / "source.db"),
            f"{system.upper()}_READ_TOKEN": "",
            f"{system.upper()}_CONTROL_TOKEN": "",
        },
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            try:
                await page.goto(url)
                await page.get_by_role(
                    "heading", name=f"Mock {system.upper()}", exact=True
                ).wait_for(timeout=5000)
                await page.wait_for_function(
                    "Number(document.querySelector('.map-wrap')?.dataset.renderedEntities || 0) > 0"
                )
                await page.get_by_role("button", name=entity, exact=True).click()
                await page.get_by_label("가용 상태 변경").select_option("unavailable")
                await page.get_by_role("button", name="변경 적용", exact=True).click()
                await page.get_by_text("변경 저장됨", exact=True).wait_for()
                await page.get_by_role("button", name="이동 시작", exact=True).click()
                await page.get_by_text("시뮬레이션 실행 중", exact=True).wait_for()
                await page.get_by_role("button", name="일시 정지", exact=True).click()
            finally:
                await browser.close()
