"""Workspace UI contracts with explicitly mocked API data and real MapLibre canvas."""

import asyncio
from contextlib import contextmanager
from pathlib import Path

import pytest
from conftest import server
from playwright.async_api import async_playwright, expect


@contextmanager
def ui_server():
    code = "import uvicorn,platform_api; from pathlib import Path; from fastapi import FastAPI; from fastapi.staticfiles import StaticFiles; from fastapi.responses import FileResponse; app=FastAPI(); root=Path(platform_api.__file__).parent/'web_static'; app.get('/health')(lambda:{'status':'ok'}); app.get('/')(lambda:FileResponse(root/'index.html')); app.mount('/assets',StaticFiles(directory=root/'assets')); uvicorn.run(app,host='127.0.0.1',port=PORT,log_level='error')"
    with server(code) as url:
        yield url


def entity():
    return {
        "entityId": "atcis/L-T01",
        "nativeId": "L-T01",
        "label": "L-T01",
        "source": "atcis",
        "kind": "tank",
        "affiliation": "friendly",
        "availability": "unknown",
        "unitId": "B11",
        "position": {"longitude": 126.5, "latitude": 37.2},
        "velocity": {"eastMps": 0, "northMps": 0},
        "speedMps": 0,
        "bearingDegrees": None,
        "displayVector": None,
        "observedAt": "2026-10-20T09:10:00Z",
        "nativeStatus": "FMC",
    }


async def mock_api(page):
    state = {
        "runs": [],
        "posts": [],
        "comparisons": [],
        "gate": None,
        "fail": False,
        "situation_fail": False,
    }

    async def route_api(route):
        path = route.request.url.split("/api/v1/")[-1]
        if path == "config":
            data = {
                "profile": "heterogeneous",
                "sourceToolContractVersion": "4",
                "fabricUrl": "http://localhost:4400",
            }
        elif path == "analyses" and route.request.method == "POST":
            args = route.request.post_data_json
            state["posts"].append(args)
            if state["gate"]:
                await state["gate"].wait()
            if state["fail"]:
                await route.fulfill(status=503, json={"detail": "test service unavailable"})
                return
            i = len(state["runs"]) + 1
            data = {
                "runId": f"r{i}",
                "conversationId": args.get("conversationId") or f"c{i}",
                "knowledgeMode": args["knowledgeMode"],
                "semanticMode": "on" if args["knowledgeMode"] == "structured" else "off",
                "semanticPolicyVersion": "4-knowledge-abc",
                "status": "completed",
                "question": args["question"],
                "createdAt": f"2026-10-20T09:10:{i:02d}Z",
                "result": {
                    "answer": f"응답 {i}: " + args["question"],
                    "findings": [],
                    "claims": [],
                    "limitations": [],
                    "courses": None,
                },
                "toolCalls": [],
                "iterations": [],
                "evidence": [],
                "selectedCourseId": None,
            }
            state["runs"].insert(0, data)
        elif path == "analyses":
            data = {"items": state["runs"]}
        elif path.startswith("conversations/"):
            data = {
                "items": [r for r in state["runs"] if r["conversationId"] == path.split("/")[1]]
            }
        elif path == "comparisons":
            data = {"items": state["comparisons"]}
        elif path.startswith("comparisons/"):
            await route.fulfill(status=404, json={"detail": "comparison_not_found"})
            return
        elif path == "situation":
            if state["situation_fail"]:
                await route.fulfill(status=503, json={"detail": "test source unavailable"})
                return
            data = {
                "entities": [entity()],
                "sources": {"atcis": {"sourceTime": "2026-10-20T09:10:00Z"}},
            }
        elif path == "sources":
            data = {
                "sources": {"atcis": {"connected": True}, "knccs": {"connected": False}},
                "mcp": {},
            }
        else:
            data = {}
        await route.fulfill(json=data)

    await page.route("**/api/v1/**", route_api)
    await page.route("https://tiles.openfreemap.org/**", lambda r: r.abort())
    return state


@pytest.mark.ui
async def test_map_and_composer_are_visible_together_at_all_sizes():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await mock_api(page)
            try:
                await page.goto(url, wait_until="domcontentloaded")
                for width, height in [
                    (1440, 900),
                    (1280, 800),
                    (1024, 768),
                    (640, 900),
                    (390, 844),
                    (390, 430),
                ]:
                    await page.set_viewport_size({"width": width, "height": height})
                    await expect(
                        page.get_by_role("region", name="전장 상황판", exact=True)
                    ).to_be_visible()
                    await expect(page.get_by_label("분석 질의", exact=True)).to_be_visible()
                    for locator in [
                        page.get_by_role("region", name="전장 상황판", exact=True),
                        page.get_by_label("분석 질의", exact=True),
                        page.locator(".bf-composer"),
                    ]:
                        box = await locator.bounding_box()
                        assert box and box["width"] > 150 and box["height"] > 45
                        assert box["y"] >= 0 and box["y"] + box["height"] <= height + 1
                    assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                await browser.close()


@pytest.mark.ui
async def test_deleted_comparison_restores_to_chat_with_explanation():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await mock_api(page)
            await page.add_init_script(
                "sessionStorage.setItem('battlefield.v4.workspace',JSON.stringify({mode:'documents',comparison:'deleted'}))"
            )
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await expect(
                    page.get_by_text("저장된 비교가 없어 대화로 돌아왔습니다.", exact=True)
                ).to_be_visible()
                await expect(page.get_by_label("지식 제공 방식", exact=True)).to_have_value(
                    "documents"
                )
                await expect(
                    page.get_by_role("button", name="대화로 돌아가기", exact=True)
                ).to_have_count(0)
            finally:
                await browser.close()


@pytest.mark.ui
async def test_ime_duplicate_errors_and_late_response_keep_user_context():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            state = await mock_api(page)
            try:
                await page.goto(url, wait_until="domcontentloaded")
                editor = page.get_by_label("분석 질의", exact=True)
                await editor.fill("한글 조합")
                await editor.dispatch_event("compositionstart")
                await editor.dispatch_event(
                    "keydown", {"key": "Enter", "code": "Enter", "isComposing": True}
                )
                assert len(state["posts"]) == 0
                await editor.dispatch_event("compositionend")
                state["fail"] = True
                await editor.press("Enter")
                await expect(page.get_by_role("alert")).to_contain_text("503")
                await expect(editor).to_have_value("한글 조합")
                state["fail"] = False
                state["gate"] = asyncio.Event()
                await editor.press("Enter")
                await expect(
                    page.get_by_role("button", name="분석 실행", exact=True)
                ).to_be_disabled()
                await editor.press("Enter")
                await page.get_by_label("지식 제공 방식", exact=True).select_option("documents")
                await editor.fill("새 맥락의 초안")
                state["gate"].set()
                await expect(
                    page.get_by_role("button", name="분석 실행", exact=True)
                ).to_be_enabled()
                assert len(state["posts"]) == 2
                await expect(editor).to_have_value("새 맥락의 초안")
                await expect(page.get_by_label("지식 제공 방식", exact=True)).to_have_value(
                    "documents"
                )
                assert await page.locator('[data-message-role="user"]').count() == 0
                await page.get_by_role("button", name="대화 이력 열기", exact=True).click()
                await page.get_by_role(
                    "button", name="A · 원천 데이터 한글 조합", exact=True
                ).click()
                await expect(page.get_by_text("응답 1: 한글 조합", exact=True)).to_be_visible()
                state["situation_fail"] = True
                await expect(
                    page.get_by_text("원천 갱신 지연 · 마지막 객체 정보 유지", exact=True)
                ).to_be_visible()
                await expect(page.get_by_text("표시 객체 1", exact=True)).to_be_visible()
                await page.screenshot(path="artifacts/battlefield-chat-source-error.png")
            finally:
                if state["gate"]:
                    state["gate"].set()
                await browser.close()


@pytest.mark.ui
async def test_scroll_selection_and_camera_survive_history_and_reload():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            state = await mock_api(page)
            try:
                await page.goto(url, wait_until="domcontentloaded")
                editor = page.get_by_label("분석 질의", exact=True)
                await editor.fill("긴 답변 검증")
                await editor.press("Enter")
                await expect(page.get_by_text("응답 1: 긴 답변 검증", exact=True)).to_be_visible()
                state["runs"][0]["result"]["answer"] = "\n\n".join(
                    f"{i}번째 근거 설명입니다." for i in range(100)
                )
                timeline = page.get_by_label("대화 타임라인", exact=True)
                await expect(
                    page.get_by_text("99번째 근거 설명입니다.", exact=False)
                ).to_be_visible()
                await timeline.evaluate(
                    'el=>{el.scrollTop=100;el.dispatchEvent(new Event("scroll"))}'
                )
                state["runs"][0]["result"]["answer"] += "\n\n새로 갱신된 내용"
                await expect(
                    page.get_by_role("button", name="새 내용 보기", exact=True)
                ).to_be_visible()
                assert abs(await timeline.evaluate("el=>el.scrollTop") - 100) < 2
                await page.get_by_role("button", name="객체 목록", exact=True).click()
                await page.get_by_role("button", name="L-T01 ATCIS · B11", exact=True).click()
                await expect(page.get_by_label("선택 객체", exact=True)).to_be_visible()
                canvas = page.locator(".map-canvas canvas")
                await canvas.evaluate("el=>el.dataset.testIdentity='kept'")
                await canvas.hover()
                await page.mouse.wheel(0, -250)
                await page.wait_for_timeout(500)  # MapLibre's wheel zoom animation
                saved = await page.evaluate(
                    "JSON.parse(sessionStorage.getItem('battlefield.v4.workspace')).view"
                )
                await page.get_by_role("button", name="새 대화", exact=True).click()
                await page.get_by_role("button", name="대화 이력 열기", exact=True).click()
                await page.get_by_role(
                    "button", name="A · 원천 데이터 긴 답변 검증", exact=True
                ).click()
                await expect(page.get_by_label("선택 객체", exact=True)).to_be_visible()
                assert await canvas.get_attribute("data-test-identity") == "kept"
                await page.reload(wait_until="domcontentloaded")
                await expect(page.get_by_label("선택 객체", exact=True)).to_be_visible()
                await expect(
                    page.get_by_text("99번째 근거 설명입니다.", exact=False)
                ).to_be_visible()
                assert abs(await timeline.evaluate("el=>el.scrollTop") - 100) < 2
                restored = await page.evaluate(
                    "JSON.parse(sessionStorage.getItem('battlefield.v4.workspace')).view"
                )
                assert abs(saved["zoom"] - restored["zoom"]) < 0.01
                await page.screenshot(path="artifacts/battlefield-chat-long.png")
            finally:
                await browser.close()


@pytest.mark.ui
async def test_chat_turns_map_identity_and_reload_restore():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            state = await mock_api(page)
            try:
                await page.goto(url, wait_until="domcontentloaded")
                editor = page.get_by_label("분석 질의", exact=True)
                await page.locator(".map-canvas canvas").wait_for()
                await page.locator(".map-canvas canvas").evaluate(
                    "el=>el.dataset.testIdentity='persistent'"
                )
                for index, text in enumerate(["첫 번째 상황 질문", "후속 질문"], 1):
                    await editor.fill(text)
                    await editor.press("Enter")
                    await expect(
                        page.get_by_text(f"응답 {index}: " + text, exact=True)
                    ).to_be_visible()
                assert state["posts"][1]["conversationId"] == "c1"
                assert await page.locator('[data-message-role="user"]').count() == 2
                assert (
                    await page.locator(".map-canvas canvas").get_attribute("data-test-identity")
                    == "persistent"
                )
                await page.reload(wait_until="domcontentloaded")
                await expect(
                    page.get_by_text("응답 1: 첫 번째 상황 질문", exact=True)
                ).to_be_visible()
                await expect(page.get_by_text("응답 2: 후속 질문", exact=True)).to_be_visible()
                await page.get_by_label("지식 제공 방식", exact=True).select_option("documents")
                assert await page.locator('[data-message-role="user"]').count() == 0
                await editor.fill("새 방식 질문")
                await editor.press("Shift+Enter")
                assert len(state["posts"]) == 2
                await editor.press("Enter")
                await expect(page.get_by_text("응답 3: 새 방식 질문", exact=True)).to_be_visible()
                assert state["posts"][2]["conversationId"] is None
                Path("artifacts").mkdir(exist_ok=True)
                await page.screenshot(path="artifacts/battlefield-chat-desktop.png")
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.screenshot(path="artifacts/battlefield-chat-mobile.png")
            finally:
                await browser.close()
