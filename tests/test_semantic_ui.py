from pathlib import Path

import pytest
from conftest import server
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from semantic_support import stack


@pytest.mark.neo4j
@pytest.mark.ui
async def test_semantic_comparison_ui_runs_two_isolated_columns_and_restores_history(tmp_path):
    load_dotenv()
    with stack(tmp_path) as (sources, semantic):
        env = {
            "PLATFORM_VNEXT_DB": str(tmp_path / "platform.db"),
            "PYTHONPATH": str(Path(__file__).parent.resolve()),
            "SEMANTIC_BASE_URL": semantic["url"],
            "SEMANTIC_MCP_URL": semantic["mcpUrl"],
            "SEMANTIC_READ_TOKEN": "",
            "SEMANTIC_MCP_TOKEN": "",
            "BUILDER_BASE_URL": semantic["builderUrl"],
            "BUILDER_ADMIN_TOKEN": "test-admin",
        }
        for system, config in sources.items():
            env.update(
                {
                    f"{system.upper()}_BASE_URL": config["url"],
                    f"{system.upper()}_MCP_URL": config["mcpUrl"],
                    f"{system.upper()}_READ_TOKEN": "",
                    f"{system.upper()}_MCP_TOKEN": "",
                }
            )
        with server(
            "import uvicorn; from semantic_support import platform_app; uvicorn.run(platform_app(),host='127.0.0.1',port=PORT,log_level='error')",
            env,
        ) as url:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 1000})
                try:
                    await page.goto(url)
                    await page.get_by_role("heading", name="통합 상황판", exact=True).wait_for(
                        timeout=5000
                    )
                    await page.get_by_label("분석 질의").fill("모의 1사단의 가용한 탱크를 보여줘.")
                    await page.get_by_role("button", name="동일 기준으로 비교", exact=True).click()
                    dialog = page.get_by_role("dialog", name="Semantic ON/OFF 비교")
                    await dialog.get_by_text("완전 비교", exact=True).wait_for(timeout=30000)
                    for mode in ("off", "on"):
                        await (
                            dialog.get_by_test_id("comparison-" + mode)
                            .get_by_text("모의 1사단의 가용 탱크는 2대입니다.", exact=True)
                            .wait_for()
                        )
                    await (
                        dialog.get_by_test_id("comparison-off")
                        .get_by_text("관계·원천 근거", exact=True)
                        .click()
                    )
                    await (
                        dialog.get_by_test_id("comparison-off")
                        .get_by_text("원천 필드값 집계 (의미 해석 없음)", exact=False)
                        .wait_for()
                    )
                    await (
                        dialog.get_by_test_id("comparison-on")
                        .get_by_text("관계·원천 근거", exact=True)
                        .click()
                    )
                    assert (
                        await dialog.get_by_test_id("comparison-on")
                        .get_by_text("semantic__resolve_unit_scope", exact=False)
                        .count()
                        > 0
                    )
                    await (
                        dialog.get_by_test_id("comparison-on")
                        .get_by_role("button", name="관계 근거 1 원문", exact=True)
                        .first.click()
                    )
                    await (
                        dialog.get_by_test_id("comparison-on")
                        .get_by_text("Graph 근거 원문 · 규칙·원천 snapshot", exact=True)
                        .wait_for()
                    )
                    Path("artifacts").mkdir(exist_ok=True)
                    await page.screenshot(path="artifacts/semantic-comparison.png", full_page=True)
                    await page.set_viewport_size({"width": 640, "height": 900})
                    await page.get_by_role("button", name="ON 비교 보기", exact=True).click()
                    assert await dialog.get_by_test_id("comparison-on").is_visible()
                    assert not await dialog.get_by_test_id("comparison-off").is_visible()
                    await page.keyboard.press("Escape")
                    await page.reload()
                    await page.get_by_role(
                        "button", name="비교 이력 열기", exact=True
                    ).first.click()
                    await (
                        page.get_by_role("dialog", name="Semantic ON/OFF 비교")
                        .get_by_text("완전 비교", exact=True)
                        .wait_for()
                    )
                finally:
                    await browser.close()
