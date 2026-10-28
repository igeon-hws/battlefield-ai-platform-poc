import pytest
from platform_api.agent.provenance import annotate_result
from playwright.async_api import async_playwright, expect
from test_workspace_ui import mock_api, ui_server


@pytest.mark.ui
async def test_document_interpretation_shows_separate_server_provenance():
    with ui_server() as url:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            state = await mock_api(page)
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.get_by_label("지식 제공 방식", exact=True).select_option("documents")
                await page.get_by_label("분석 질의", exact=True).fill("문서 해석")
                await page.get_by_role("button", name="분석 실행", exact=True).click()
                await expect(page.get_by_text("응답 1: 문서 해석", exact=True)).to_be_visible()
                result = state["runs"][0]["result"]
                result.update(
                    outcome="answer",
                    evidenceIds=["doc"],
                    claims=[
                        {
                            "kind": "semantic",
                            "text": "문서 해석 예시",
                            "evidenceRefs": ["doc"],
                            "ruleRefs": ["LOG-LINK-01"],
                        }
                    ],
                )
                annotate_result(
                    result,
                    {
                        "doc": {
                            "systemId": "knowledge",
                            "data": {
                                "documentKey": "logistics:LOG-01",
                                "knowledgeSetVersion": "pinned",
                                "document": {
                                    "version": "1",
                                    "hash": "h",
                                    "text": "LOG-LINK-01: 명시적 등록",
                                },
                            },
                        }
                    },
                    "documents",
                )
                await page.get_by_text("주장별 해석·근거", exact=True).click()
                await expect(
                    page.get_by_text("모델의 주장 분류 · 서버 확인 출처: 문서", exact=True)
                ).to_be_visible()
                await expect(
                    page.get_by_text("문서 내 규칙 표기: LOG-LINK-01", exact=True)
                ).to_be_visible()
                await page.screenshot(path="artifacts/claim-document-provenance.png")
            finally:
                await browser.close()
