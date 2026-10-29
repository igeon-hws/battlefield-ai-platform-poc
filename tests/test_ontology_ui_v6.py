"""v6 presentation flow in real browsers: C answer trace to graph/source and the Fabric
ontology edit → impact → approval → publish. Deterministic provider, no model cost."""

import json
from pathlib import Path

import httpx
import pytest
from test_knowledge_integration import v4_stack, wait_run

QUESTION = "모의 1사단 예하 가용 전차 현황을 정리해줘."
SHOTS = Path("artifacts/ontology-v6")


def message(body):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(body, ensure_ascii=False)}],
            }
        ],
    }


def call(name, args, call_id):
    return {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": name,
                "call_id": call_id,
                "arguments": json.dumps(args),
            }
        ],
    }


class V6Provider:
    """C cites one business query; A/B cite source records. Not an accuracy measurement."""

    async def respond(self, inputs, **kwargs):
        outputs = [
            json.loads(i["output"]) for i in inputs if i.get("type") == "function_call_output"
        ]
        names = {t["name"] for t in kwargs["tools"]}
        if not outputs and "semantic__run_business_query" in names:
            return call(
                "semantic__run_business_query",
                {
                    "queryId": "asset-availability-summary",
                    "unit": "D1",
                    "kind": "tank",
                    "systemId": None,
                    "nativeId": None,
                    "partId": None,
                },
                "bq",
            )
        if not outputs:
            return call("atcis__list_equipment", {}, "src")
        structured = outputs[0].get("tool") == "semantic__run_business_query"
        if structured and len(outputs) == 1 and "evidenceId" in outputs[0]:
            return call(
                "semantic__run_business_query",
                {
                    "queryId": "asset-maintenance-chain",
                    "unit": None,
                    "kind": None,
                    "systemId": "atcis",
                    "nativeId": "L-T02",
                    "partId": None,
                },
                "chain",
            )
        if "evidenceId" not in outputs[0]:
            return message(
                {
                    "outcome": "partial",
                    "answer": "tool error: " + json.dumps(outputs[0], ensure_ascii=False)[:400],
                    "findings": [],
                    "claims": [],
                    "evidenceIds": [],
                    "limitations": ["test provider"],
                    "courses": None,
                }
            )
        evidence = outputs[0]["evidenceId"]
        counts = (outputs[0].get("data") or {}).get("counts") or {}
        if structured:
            # Three claims share two evidences; the analysis view must still render twice.
            chain = outputs[1]["evidenceId"]
            return message(
                {
                    "outcome": "answer",
                    "answer": f"가용 전차는 {counts.get('available', '?')}대입니다.",
                    "findings": [],
                    "claims": [
                        {
                            "kind": "calculation",
                            "text": "모의 1사단 예하 전차 L-T01 가용, L-T02 제한(PMC)",
                            "evidenceRefs": [evidence],
                            "ruleRefs": ["AGGREGATION-POLICY-01"],
                        },
                        {
                            "kind": "observation",
                            "text": "L-T02는 10-21 15:00 정비 완료가 조건부로 전망됩니다.",
                            "evidenceRefs": [chain],
                            "ruleRefs": [],
                        },
                        {
                            "kind": "inference",
                            "text": "전망은 전제 조건부라 가용 전환으로 확정할 수 없습니다.",
                            "evidenceRefs": [chain],
                            "ruleRefs": [],
                        },
                    ],
                    "evidenceIds": [evidence, chain],
                    "limitations": ["test provider"],
                    "courses": None,
                }
            )
        return message(
            {
                "outcome": "answer",
                "answer": f"가용 전차는 {counts.get('available', '?')}대입니다."
                if structured
                else "원천 장비 기록을 확인했습니다.",
                "findings": [],
                "claims": [
                    {
                        "kind": "calculation" if structured else "observation",
                        "text": "모의 1사단 예하 전차 L-T01 가용, L-T02 제한(PMC)",
                        "evidenceRefs": [evidence],
                        "ruleRefs": ["AGGREGATION-POLICY-01"] if structured else [],
                    }
                ],
                "evidenceIds": [evidence],
                "limitations": ["test provider"],
                "courses": None,
            }
        )


@pytest.mark.neo4j
@pytest.mark.ui
async def test_v6_trace_and_fabric_publish_in_browser(tmp_path):
    from playwright.async_api import async_playwright, expect

    expect.set_options(timeout=60000)
    SHOTS.mkdir(parents=True, exist_ok=True)
    extra = {"C4I_ONTOLOGY_PROFILE": "6", "FABRIC_KNOWLEDGE_STORE": str(tmp_path / "store")}
    with v4_stack(
        tmp_path,
        graph=True,
        version="5",
        provider_module="test_ontology_ui_v6",
        provider_class="V6Provider",
        extra_env=extra,
    ) as (url, env):
        async with httpx.AsyncClient(base_url=url, timeout=60) as c:
            sessions = {
                m: (await c.post("/api/v1/demo-sessions", json={"mode": m})).json()["sessionId"]
                for m in ("documents", "structured")
            }
            runs = {}
            for mode, sid in sessions.items():
                r = await c.post(
                    "/api/v1/analyses",
                    json={"question": QUESTION, "knowledgeMode": mode},
                    headers={"x-demo-session": sid},
                )
                assert r.status_code == 202, r.text
                c.headers["x-demo-session"] = sid
                runs[mode] = await wait_run(c, r.json()["runId"])
                assert runs[mode]["status"] == "completed", (
                    mode,
                    runs[mode].get("error"),
                    (runs[mode].get("result") or {}).get("answer"),
                )
        assert "semantic__run_business_query" in runs["structured"]["registryBindings"]
        assert not any(n.startswith("semantic__") for n in runs["documents"]["registryBindings"])
        result = runs["structured"]["result"]
        assert result["outcome"] == "answer", result["answer"]
        assert result["claims"][0]["ruleRefs"] == ["AGGREGATION-POLICY-01"]
        assert result["claims"][0]["provenance"]["unverifiedRuleRefs"] == []
        classes = [c["provenance"]["claimClass"] for c in result["claims"]]
        assert classes == ["fact", "fact", "judgment"]
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(60000)
            try:
                await page.goto(url + "/demo/c", wait_until="domcontentloaded")
                box = page.get_by_placeholder("상황에 대해 질문하세요…")
                await box.fill(QUESTION)
                await box.press("Enter")
                await expect(page.get_by_text("가용 전차는 1대입니다.").first).to_be_visible()
                await page.get_by_text("주장별 해석·근거").last.click()
                # Two evidences cited by three claims: each analysis renders once.
                await expect(page.get_by_label("분석 과정")).to_have_count(2)
                await expect(page.get_by_label("주장 분류 요약")).to_contain_text(
                    "계산된 사실 2 · 모델 판단 1"
                )
                await expect(page.get_by_label("모델 판단").first).to_contain_text("검토 필요")
                await page.get_by_label("모델 판단").first.scroll_into_view_if_needed()
                await page.screenshot(path=str(SHOTS / "c-claims-list.png"))
                analysis = page.get_by_label("분석 과정").first
                await expect(analysis).to_contain_text("1. 범위 정하기")
                await expect(analysis).to_contain_text("전차만 남김: 5 → 2대")
                await expect(analysis).to_contain_text("L-T02 PMC → 제한")
                await expect(analysis).to_contain_text("가용 1대 / 전체 2대")
                await expect(analysis.get_by_label("제외 항목")).to_contain_text("전차 아님")
                graph = analysis.get_by_role("img", name="분석에 쓰인 지식그래프")
                await expect(graph).to_contain_text("모의 1사단")
                await expect(graph).to_contain_text("L-V01")
                step = analysis.get_by_role("button", name="4. 상태 판정")
                await step.click()
                await expect(step).to_have_attribute("aria-pressed", "true")
                await analysis.scroll_into_view_if_needed()
                await page.screenshot(path=str(SHOTS / "c-analysis.png"))
                await graph.scroll_into_view_if_needed()
                await graph.screenshot(path=str(SHOTS / "c-analysis-graph.png"))
                await page.set_viewport_size({"width": 390, "height": 844})
                await analysis.scroll_into_view_if_needed()
                width = await page.evaluate("document.documentElement.scrollWidth")
                assert width <= 390
                await page.screenshot(path=str(SHOTS / "c-analysis-mobile.png"))
                await page.set_viewport_size({"width": 1440, "height": 900})
                await page.get_by_role(
                    "button", name="근거 2. 자산 정비·부품·수송 의존 체인"
                ).first.click()
                await expect(page.locator(".evidence-block.flash")).to_have_count(1)
                await page.screenshot(path=str(SHOTS / "c-claims.png"))
                await page.get_by_text("세부 근거 (업무 질의·선언·간선·원천 기록)").first.click()
                chain = page.get_by_label("근거 추적").first
                await expect(chain).to_contain_text("업무 질의")
                await expect(chain).to_contain_text("선언 6.0.0-r1")
                await expect(chain).to_contain_text("AGGREGATION-POLICY-01")
                await expect(chain).to_contain_text("atcis/equipment/L-T01")
                await chain.scroll_into_view_if_needed()
                await page.screenshot(path=str(SHOTS / "c-trace.png"))
                href = await chain.get_by_role("link").first.get_attribute("href")
                assert href and "graphVersion=" in href and "node=" in href
                fabric_href = env["SEMANTIC_BASE_URL"] + "/?" + href.split("?", 1)[1]
                await page.goto(fabric_href, wait_until="domcontentloaded")
                await expect(page.get_by_text("연결 지식 탐색").first).to_be_visible()
                await page.screenshot(path=str(SHOTS / "fabric-deeplink.png"))

                await page.goto(env["SEMANTIC_BASE_URL"], wait_until="domcontentloaded")
                await page.get_by_role("button", name="온톨로지 정의 · 검토 · 발행").click()
                await expect(page.get_by_text("현재 선언")).to_contain_text("6.0.0-r1")
                await page.get_by_role("combobox").first.select_option("P2")
                await page.get_by_label("작성자").fill("analyst")
                await page.get_by_role("button", name="초안 검증·영향 분석").click()
                preview = page.get_by_label("업무 질의 전후 미리보기")
                await expect(preview).to_contain_text("가용 2")
                await expect(page.get_by_label("영향 분석")).to_contain_text(
                    "asset-availability-summary"
                )
                await page.screenshot(path=str(SHOTS / "fabric-impact.png"), full_page=True)
                await page.get_by_label("승인자 (작성자와 달라야 함)").fill("reviewer")
                await page.get_by_role("button", name="승인·발행").click()
                await expect(
                    page.get_by_role("status").filter(has_text="발행 완료")
                ).to_be_visible()
                await expect(page.get_by_text("현재 선언")).to_contain_text("6.0.0-r2")
                await page.screenshot(path=str(SHOTS / "fabric-published.png"), full_page=True)

                mobile = await browser.new_page(viewport={"width": 390, "height": 844})
                await mobile.goto(env["SEMANTIC_BASE_URL"], wait_until="domcontentloaded")
                await mobile.get_by_role("button", name="온톨로지 정의 · 검토 · 발행").click()
                await expect(mobile.get_by_text("발행 이력")).to_be_visible()
                width = await mobile.evaluate("document.documentElement.scrollWidth")
                assert width <= 390
                await mobile.screenshot(path=str(SHOTS / "fabric-mobile.png"), full_page=True)

                await page.goto(url + "/demo/c", wait_until="domcontentloaded")
                # A running conversation keeps its starting knowledge version by design.
                await page.get_by_role("button", name="새 대화", exact=True).first.click()
                box = page.get_by_placeholder("상황에 대해 질문하세요…")
                await box.fill(QUESTION)
                await box.press("Enter")
                await expect(page.get_by_text("가용 전차는 2대입니다.").first).to_be_visible(
                    timeout=180000
                )
                await page.get_by_text("주장별 해석·근거").last.click()
                await expect(page.get_by_label("근거 추적").last).to_contain_text("선언 6.0.0-r2")
                await page.screenshot(path=str(SHOTS / "c-trace-after-publish.png"))
            except AssertionError:
                await page.screenshot(path=str(SHOTS / "debug.png"), full_page=True)
                import sqlite3

                with sqlite3.connect(env["PLATFORM_VNEXT_DB"]) as db:
                    rows = [json.loads(r[0]) for r in db.execute("SELECT body FROM runs")]
                (SHOTS / "debug-runs.json").write_text(
                    json.dumps(
                        [
                            {
                                k: r.get(k)
                                for k in (
                                    "status",
                                    "knowledgeMode",
                                    "error",
                                    "createdAt",
                                    "updatedAt",
                                )
                            }
                            | {
                                "toolCalls": [
                                    {
                                        k: c.get(k)
                                        for k in (
                                            "name",
                                            "status",
                                            "startedAt",
                                            "endedAt",
                                            "response",
                                        )
                                    }
                                    for c in r.get("toolCalls", [])
                                ]
                            }
                            for r in rows
                        ],
                        ensure_ascii=False,
                        indent=1,
                    )[:20000],
                    encoding="utf-8",
                )
                raise
            finally:
                await browser.close()
