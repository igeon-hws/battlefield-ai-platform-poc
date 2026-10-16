import httpx
import pytest
from conftest import server
from platform_api.multi_app import create_multi_app
from playwright.async_api import async_playwright


async def test_missing_conversation_is_explicit_and_does_not_enqueue(tmp_path):
    app = create_multi_app(path=tmp_path / "platform.db", provider=object())
    repo = app.state.repository
    await repo.open()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/analyses",
                json={"question": "inventory", "semanticMode": "off", "conversationId": "old-db"},
            )
            assert response.status_code == 404
            assert response.json() == {"error": "conversation_not_found"}
            assert await repo.runs() == []
            response = await client.post("/api/v1/analyses", json={"question": "inventory"})
            assert response.status_code == 202
            assert response.json()["conversationId"] != "old-db"
    finally:
        await repo.close()


@pytest.mark.ui
@pytest.mark.parametrize("error", ["conversation_not_found", "not_found", "server_error"])
async def test_ui_recovers_only_explicit_missing_conversation(tmp_path, error):
    requests = []

    async def api_route(route):
        request = route.request
        path = request.url.split("/api/v1/")[1]
        if path == "analyses" and request.method == "POST":
            body = request.post_data_json
            requests.append(body)
            if len(requests) == 1:
                await route.fulfill(
                    status=500 if error == "server_error" else 404,
                    json={"error": error},
                )
                return
            await route.fulfill(json={"conversationId": "new-db"}, status=202)
            return
        data = {
            "config": {"profile": "heterogeneous"},
            "situation": {"entities": []},
            "sources": {"sources": {}, "mcp": {}},
            "analyses": {"items": []},
            "comparisons": {"items": []},
        }
        await route.fulfill(json=data.get(path, {}))

    with server(
        "import uvicorn; from platform_api.multi_app import create_multi_app; "
        "uvicorn.run(create_multi_app(provider=object()),host='127.0.0.1',port=PORT,log_level='error')",
        {"PLATFORM_VNEXT_DB": str(tmp_path / "ui.db")},
    ) as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                await page.add_init_script(
                    "sessionStorage.setItem('vnext.conversation', 'old-db');"
                    "sessionStorage.setItem('vnext.mode', 'off');"
                )
                await page.route("**/api/v1/**", api_route)
                await page.goto(url)
                await page.get_by_label("분석 질의").fill("inventory")
                await page.get_by_role("button", name="질의 실행", exact=True).click()
                if error == "conversation_not_found":
                    await page.wait_for_function(
                        "sessionStorage.getItem('vnext.conversation') === 'new-db'"
                    )
                    assert requests == [
                        {
                            "question": "inventory",
                            "semanticMode": "off",
                            "conversationId": "old-db",
                        },
                        {"question": "inventory", "semanticMode": "off", "conversationId": None},
                    ]
                    await page.get_by_role("status").filter(has_text="새 대화").wait_for()
                else:
                    await page.get_by_role("alert").filter(has_text=error).wait_for()
                    assert len(requests) == 1
                    assert (
                        await page.evaluate("sessionStorage.getItem('vnext.conversation')")
                        == "old-db"
                    )
            finally:
                await browser.close()
