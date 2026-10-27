from pathlib import Path

import pytest
from conftest import server
from playwright.async_api import async_playwright
from test_domain_integration import domain_stack  # noqa: F401 - real services fixture


@pytest.mark.ui
@pytest.mark.parametrize(
    "system,tab,record", [("atcis", "상황보고", "R4"), ("knccs", "전문함", "M3")]
)
async def test_native_workspaces_show_distinct_work_records_and_raw_schema(
    tmp_path, system, tab, record
):
    with server(
        f"import uvicorn; from mock_{system}.native import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
        {f"{system.upper()}_DB": str(tmp_path / "source.db")},
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 960})
            try:
                await page.goto(url)
                await page.get_by_role(
                    "heading", name=f"Mock {system.upper()}", exact=True
                ).wait_for(timeout=5000)
                await page.get_by_role("button", name=tab, exact=True).click()
                await page.get_by_role("button", name=record, exact=True).click()
                await page.get_by_text("원천 레코드", exact=True).wait_for()
                await page.get_by_role("button", name="1초 진행", exact=True).click()
                await page.get_by_role("status").filter(has_text="진행 완료").wait_for()
            finally:
                await browser.close()


@pytest.mark.ui
async def test_fabric_console_is_independent_and_shows_catalog():
    with server(
        "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
        # This case requires no Graph; do not inherit a developer's active Neo4j.
        {"C4I_CONTRACT_VERSION": "3", "SEMANTIC_READ_TOKEN": "", "NEO4J_PASSWORD": ""},
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url)
                await page.get_by_role("heading", name="Data Fabric", exact=True).wait_for(
                    timeout=5000
                )
                await page.get_by_text("c2-domain-demo-v3", exact=True).wait_for()
                await page.get_by_role("button", name="도메인 규칙", exact=True).click()
                await page.get_by_text(
                    "규칙을 조회할 Graph 버전이 필요합니다.", exact=True
                ).wait_for()
            finally:
                await browser.close()


@pytest.mark.ui
@pytest.mark.neo4j
async def test_domain_platform_comparison_displays_shared_context(domain_stack, tmp_path):  # noqa: F811
    env = {
        **domain_stack,
        "PLATFORM_VNEXT_DB": str(tmp_path / "ui-platform.db"),
        "PYTHONPATH": str(Path(__file__).parent.resolve()),
    }
    with server(
        "import uvicorn; from platform_api.app import create_app; from test_domain_platform import ProcedureProvider; uvicorn.run(create_app(profile='heterogeneous',provider=ProcedureProvider()),host='127.0.0.1',port=PORT,log_level='error')",
        env,
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            try:
                await page.goto(url)
                await page.get_by_label("기준보고").select_option("atcis:report:R0")
                await page.get_by_label("분석 질의").fill("INC-1 지금 어디까지 진행됐어?")
                await page.get_by_role("button", name="동일 기준으로 비교", exact=True).click()
                dialog = page.get_by_role("dialog", name="Semantic ON/OFF 비교")
                await dialog.get_by_text("완전 비교", exact=True).wait_for(timeout=120000)
                await dialog.get_by_text("공통 비교 조건·문서·기준보고", exact=True).click()
                await dialog.get_by_text(
                    '"baselineReportRef": "atcis:report:R0"', exact=False
                ).wait_for()
                Path("artifacts").mkdir(exist_ok=True)
                await page.screenshot(path="artifacts/domain-comparison.png", full_page=True)
                await page.set_viewport_size({"width": 640, "height": 900})
                await page.get_by_role("button", name="ON 비교 보기", exact=True).click()
                assert await dialog.get_by_test_id("comparison-on").is_visible()
                assert not await dialog.get_by_test_id("comparison-off").is_visible()
            finally:
                await browser.close()


@pytest.mark.ui
async def test_navy_reference_tab_switches_do_not_accumulate_document_buttons(tmp_path):
    with server(
        "import uvicorn; from mock_knccs.native import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
        {"KNCCS_DB": str(tmp_path / "navy.db")},
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url)
                aside = page.locator(".domain-source-grid > aside").first
                for _ in range(3):
                    await page.get_by_role("button", name="참조 기록", exact=True).click()
                    await aside.get_by_role("button", name="E1", exact=True).wait_for(timeout=5000)
                    assert await aside.get_by_role("button").count() == 2
                    await page.get_by_role("button", name="관측 이력", exact=True).click()
                    await aside.get_by_role("button", name="O1", exact=True).wait_for()
                    assert await aside.get_by_role("button").count() == 4
                    await page.get_by_role("button", name="자군 함정", exact=True).click()
                    await aside.get_by_role("button", name="N-S01", exact=True).wait_for()
                    assert await aside.get_by_role("button").count() == 2
            finally:
                await browser.close()
