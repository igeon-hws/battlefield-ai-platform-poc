"""Actual Knowledge MCP reproduction without paid model calls or Neo4j."""

import json

import httpx
from test_knowledge_integration import v4_stack, wait_run


class DocumentClaimProvider:
    async def respond(self, inputs, **kwargs):
        assert (
            "semantic"
            not in kwargs["result_format"]["schema"]["$defs"]["Claim"]["properties"]["kind"]["enum"]
        )
        outputs = [
            json.loads(i["output"]) for i in inputs if i.get("type") == "function_call_output"
        ]
        if not outputs:
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "name": "knowledge__get_knowledge_document",
                        "call_id": "doc",
                        "arguments": json.dumps({"documentKey": "logistics:LOG-01"}),
                    }
                ],
            }
        evidence = outputs[-1]
        result = {
            "outcome": "answer",
            "answer": "문서의 명시적 등록 관계를 해석한 답변",
            "findings": [],
            "evidenceIds": [evidence["evidenceId"]],
            "limitations": [],
            "courses": None,
            "claims": [
                {
                    "kind": "semantic",
                    "text": "명시적 등록 관계를 사용한다.",
                    "evidenceRefs": [evidence["evidenceId"]],
                    "ruleRefs": ["LOG-LINK-01"],
                }
            ],
        }
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(result)}],
                }
            ],
        }


async def test_b_real_document_mcp_returns_answer_without_label_repair(tmp_path):
    with v4_stack(
        tmp_path,
        version="5",
        provider_module="test_claim_provenance_integration",
        provider_class="DocumentClaimProvider",
    ) as (url, _env):
        async with httpx.AsyncClient(base_url=url, timeout=60) as c:
            session = (await c.post("/api/v1/demo-sessions", json={"mode": "documents"})).json()
            c.headers["x-demo-session"] = session["sessionId"]
            response = await c.post(
                "/api/v1/analyses",
                json={"question": "문서의 등록 연결 규칙을 설명해줘", "knowledgeMode": "documents"},
            )
            assert response.status_code == 202, response.text
            run = await wait_run(c, response.json()["runId"])
            assert run["status"] == "completed", run.get("error")
            assert len(run["iterations"]) == 2
            claim = run["result"]["claims"][0]
            assert claim["kind"] == "inference" and claim["ruleRefs"] == []
            assert claim["provenance"]["sources"] == ["document"]
            assert claim["provenance"]["documentRuleRefs"] == ["LOG-LINK-01"]
            assert claim["provenance"]["documents"][0]["hash"]
