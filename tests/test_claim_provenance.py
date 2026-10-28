import json

import pytest
from platform_api.agent.loop import AgentLoop
from platform_api.agent.tools import ToolRunner
from test_agent import FakeMCP, FakeProvider, final


async def run_claim(
    kind="semantic", rule="LOG-LINK-01", ref="doc", mode="documents", system="knowledge"
):
    runner = ToolRunner(FakeMCP())
    runner.knowledge_mode = mode
    runner.mode = "on" if mode == "structured" else "off"
    runner.evidence = {
        "doc": {
            "evidenceId": "doc",
            "systemId": system,
            "tool": "knowledge__get_knowledge_document",
            "data": {
                "documentKey": "logistics:LOG-01",
                "knowledgeSetVersion": "pinned",
                "document": {
                    "version": "1",
                    "hash": "h",
                    "text": "합성 규칙 LOG-LINK-01: 명시적 등록을 사용한다.",
                },
                **({"ruleId": "LOG-LINK-01"} if system == "semantic" else {}),
            },
        }
    }
    reply = final(evidence=[ref])
    payload = json.loads(reply["output"][0]["content"][0]["text"])
    payload["claims"] = [
        {"kind": kind, "text": "문서를 해석한 주장", "evidenceRefs": [ref], "ruleRefs": [rule]}
    ]
    reply["output"][0]["content"][0]["text"] = json.dumps(payload)
    return await AgentLoop(FakeProvider([reply, reply]), runner).run("test")


async def test_b_legacy_semantic_and_document_rule_do_not_discard_answer():
    result = await run_claim()
    assert result["status"] == "completed"
    claim = result["result"]["claims"][0]
    assert claim["kind"] == "inference"
    assert claim["provenance"]["sources"] == ["document"]
    assert claim["ruleRefs"] == []
    assert claim["provenance"]["documentRuleRefs"] == ["LOG-LINK-01"]


async def test_unknown_rule_is_visible_partial_not_fabricated_proof():
    result = await run_claim(kind="inference", rule="INVENTED")
    assert result["status"] == "partial" and result["result"]["answer"]
    assert result["result"]["claims"][0]["provenance"]["unverifiedRuleRefs"] == ["INVENTED"]


@pytest.mark.parametrize("mode", ["native", "documents"])
async def test_a_b_cannot_cite_actual_semantic_evidence(mode):
    assert (await run_claim(mode=mode, system="semantic"))["status"] == "validation_failed"


async def test_missing_evidence_remains_a_hard_failure():
    assert (await run_claim(ref="missing"))["status"] == "validation_failed"


async def test_c_provenance_comes_from_evidence_not_reported_kind():
    result = await run_claim(mode="structured", system="semantic", kind="inference")
    assert result["status"] == "completed"
    assert result["result"]["claims"][0]["provenance"]["sources"] == ["semantic"]
    assert result["result"]["claims"][0]["ruleRefs"] == ["LOG-LINK-01"]


async def test_native_cannot_cite_document_evidence():
    assert (await run_claim(mode="native"))["status"] == "validation_failed"
