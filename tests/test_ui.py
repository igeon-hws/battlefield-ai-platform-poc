import os

import pytest
from conftest import server
from playwright.async_api import async_playwright


@pytest.mark.ui
async def test_c4i_controls_map_filters_and_platform_query(c4i_url, mcp_url, tmp_path):
    env = {
        "C4I_BASE_URL": c4i_url,
        "C4I_READ_TOKEN": "test-read",
        "MCP_SERVER_URL": mcp_url,
        "MCP_TOKEN": "test-mcp",
        "PLATFORM_DB": str(tmp_path / "ui-platform.db"),
        "PYTHONPATH": str(os.path.dirname(__file__)),
    }
    code = "import uvicorn; from ui_support import app; uvicorn.run(app(),host='127.0.0.1',port=PORT,log_level='error')"
    with server(code, env) as platform_url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            console = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: console.append(message.text))
            await page.add_init_script(
                "sessionStorage.setItem('c4i.readToken','test-read');sessionStorage.setItem('c4i.controlToken','test-control')"
            )
            await page.goto(c4i_url)
            try:
                await page.wait_for_function(
                    "Number(document.querySelector('.map-wrap')?.dataset.renderedEntities || 0) > 0",
                    timeout=15000,
                )
            except Exception:
                await page.screenshot(path="artifacts/map-failure.png")
                print("Browser map diagnostics:", console[-20:], errors)
                raise
            await page.get_by_role("button", name="BLU-T01", exact=False).click()
            await page.get_by_label("가용 상태 변경").select_option("unavailable")
            await page.get_by_role("button", name="변경 적용").click()
            await page.get_by_text("변경 저장됨", exact=True).wait_for()
            await page.get_by_label("유형 필터").select_option("tank")
            await page.get_by_label("소속 필터").select_option("hostile")
            await page.get_by_test_id("entity-count").filter(has_text="3").wait_for()
            await page.get_by_label("유형 필터").select_option("armored_vehicle")
            await page.get_by_label("소속 필터").select_option("friendly")
            await page.get_by_role("button", name="BLU-A01", exact=False).click()
            assert await page.get_by_label("정비 상태 변경").input_value() == "serviceable"
            await (
                page.locator(".object-detail")
                .get_by_text("synthetic-scenario", exact=False)
                .wait_for()
            )
            await page.goto(platform_url)
            await page.get_by_label("유형 필터").select_option("armored_vehicle")
            await page.get_by_test_id("entity-count").filter(has_text="1").wait_for()
            await page.get_by_role("button", name="BLU-A01", exact=False).click()
            await page.get_by_test_id("entity-attributes").filter(has_text="DEMO-BLUE").wait_for()
            await page.get_by_label("유형 필터").select_option("")
            await page.get_by_role("textbox", name="분석 질의").fill(
                "적 탱크는 몇 대야? 방책 세 가지도 비교해줘."
            )
            await page.get_by_role("button", name="질의 실행", exact=True).click()
            await page.get_by_text("등록된 적 탱크는 3대입니다.", exact=False).wait_for(
                timeout=20000
            )
            await page.get_by_role("button", name="방책 3개 비교").click()
            assert await page.get_by_test_id("course-column").count() == 3
            await page.get_by_role("button", name="방책 2 선택").click()
            await page.get_by_text("선택됨", exact=True).wait_for()
            await page.screenshot(path="artifacts/platform-comparison.png", full_page=True)
            await page.get_by_role("button", name="분석으로 돌아가기").click()
            await page.wait_for_function(
                "Number(document.querySelector('.map-wrap')?.dataset.renderedEntities || 0) > 0"
            )
            await page.locator("summary").filter(has_text="실행 상세").first.click()
            await page.get_by_text("c4i_summarize_entities", exact=False).first.wait_for()
            await page.wait_for_function(
                "Number(document.querySelector('.map-wrap')?.dataset.basemapFeatures || 0) > 0",
                timeout=20000,
            )
            await page.screenshot(path="artifacts/platform-dashboard.png", full_page=True)
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.screenshot(path="artifacts/platform-1280.png", full_page=True)
            await page.get_by_role("textbox", name="분석 질의").fill(
                "선택한 방책을 바탕으로 다시 비교해줘"
            )
            await page.get_by_role("button", name="질의 실행", exact=True).click()
            await page.wait_for_function(
                "document.querySelectorAll('[data-testid=chat-turn]').length === 2"
            )
            turns = page.get_by_test_id("chat-turn")
            await turns.nth(1).get_by_role("button", name="방책 3개 비교").wait_for()
            await turns.nth(1).get_by_role("button", name="방책 3개 비교").click()
            await page.get_by_role("button", name="방책 3 선택").click()
            await page.get_by_text("선택됨", exact=True).wait_for()
            await page.get_by_role("button", name="분석으로 돌아가기").click()
            await (
                turns.nth(0)
                .get_by_test_id("selected-course")
                .filter(has_text="검토 대안 2")
                .wait_for()
            )
            await (
                turns.nth(1)
                .get_by_test_id("selected-course")
                .filter(has_text="검토 대안 3")
                .wait_for()
            )
            await page.reload()
            await (
                page.get_by_test_id("chat-turn")
                .nth(1)
                .get_by_test_id("selected-course")
                .filter(has_text="검토 대안 3")
                .wait_for()
            )
            # An older turn must retain its own selection target after follow-up.
            await (
                page.get_by_test_id("chat-turn")
                .nth(0)
                .get_by_role("button", name="방책 3개 비교")
                .click()
            )
            await page.route(
                "**/selection",
                lambda route: route.fulfill(
                    status=422,
                    content_type="application/json",
                    body='{"detail":"test selection failure"}',
                ),
            )
            await page.get_by_role("button", name="방책 1 선택").click()
            await page.get_by_text("방책 선택 실패:", exact=False).first.wait_for()
            await page.unroute("**/selection")
            await page.get_by_role("button", name="방책 1 선택").click()
            await page.get_by_text("선택됨", exact=True).wait_for()
            await page.get_by_role("button", name="분석으로 돌아가기").click()
            await (
                page.get_by_test_id("chat-turn")
                .nth(0)
                .get_by_test_id("selected-course")
                .filter(has_text="검토 대안 1")
                .wait_for()
            )
            await (
                page.get_by_test_id("chat-turn")
                .nth(1)
                .get_by_test_id("selected-course")
                .filter(has_text="검토 대안 3")
                .wait_for()
            )
            conversation_id = await page.evaluate("sessionStorage.getItem('platform.conversation')")
            response = await page.request.get(
                platform_url + "/api/v1/conversations/" + conversation_id
            )
            turns_data = (await response.json())["items"]
            assert turns_data[0]["selectedCourseId"].endswith("course-1")
            assert turns_data[1]["selectedCourseId"].endswith("course-3")
            await page.screenshot(path="artifacts/platform-conversation.png", full_page=True)
            await page.get_by_role("textbox", name="분석 질의").fill(
                "최신 적 탱크 수도 다시 확인해줘"
            )
            await page.get_by_role("button", name="질의 실행", exact=True).click()
            await (
                page.get_by_test_id("chat-turn")
                .nth(2)
                .get_by_role("button", name="방책 3개 비교")
                .wait_for()
            )
            assert (
                await page.evaluate("sessionStorage.getItem('platform.conversation')")
                == conversation_id
            )
            await page.get_by_role("button", name="새 대화", exact=True).click()
            assert await page.get_by_test_id("chat-turn").count() == 0
            assert not errors
            await browser.close()


@pytest.mark.ui
async def test_border_overview_sector_navigation_and_tick_preserves_view(tmp_path):
    source_code = "import uvicorn; from mock_c4i.app import create_app; uvicorn.run(create_app(token='',control_token='',scenario_id='border-demo'),host='127.0.0.1',port=PORT,log_level='error')"
    platform_code = "import uvicorn; from ui_support import app; uvicorn.run(app(),host='127.0.0.1',port=PORT,log_level='error')"
    with server(source_code, {"C4I_DB": str(tmp_path / "border.db")}) as source_url:
        env = {
            "C4I_BASE_URL": source_url,
            "C4I_READ_TOKEN": "",
            "PLATFORM_DB": str(tmp_path / "border-platform.db"),
            "PYTHONPATH": str(os.path.dirname(__file__)),
        }
        with server(platform_code, env) as platform_url:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                await page.goto(source_url)
                await page.get_by_role("heading", name="남북 접경 전역 모의 상황").wait_for()
                await page.wait_for_function(
                    "Number(document.querySelector('.map-wrap')?.dataset.renderedEntities || 0) >= 100"
                )
                await page.get_by_label("시연 구역 이동").select_option("east-south")
                await page.wait_for_function(
                    "Number(document.querySelector('.map-wrap')?.dataset.mapLongitude)>128"
                )
                await page.get_by_role("button", name="이동 시작", exact=True).click()
                await page.wait_for_function(
                    "Number(document.querySelector('.simulation-meta code')?.textContent.replace('s',''))>=2"
                )
                assert (
                    float(await page.locator(".map-wrap").get_attribute("data-map-longitude")) > 128
                )
                await page.get_by_role("button", name="전체 보기", exact=True).click()
                await page.wait_for_function(
                    "Number(document.querySelector('.map-wrap')?.dataset.mapZoom)<9"
                )
                await page.wait_for_function(
                    "Number(document.querySelector('.map-wrap')?.dataset.basemapFeatures || 0)>0",
                    timeout=25000,
                )
                await page.screenshot(path="artifacts/border-c4i.png", full_page=True)
                await page.get_by_role("button", name="일시 정지", exact=True).click()
                # Background failure still leaves local objects available on platform.
                await page.route("**/styles/liberty", lambda route: route.abort())
                await page.goto(platform_url)
                await page.get_by_role("heading", name="남북 접경 전역 모의 상황").wait_for()
                await page.wait_for_function(
                    "Number(document.querySelector('.map-wrap')?.dataset.renderedEntities || 0) >= 100"
                )
                assert await page.locator(".small-count").inner_text() == "120"
                await page.get_by_label("시연 구역 이동").select_option("central-north")
                await page.get_by_role("button", name="전체 보기", exact=True).click()
                await page.screenshot(path="artifacts/border-platform.png", full_page=True)
                await browser.close()
