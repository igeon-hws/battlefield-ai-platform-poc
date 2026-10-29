"""Server-judged claim class for C answers: a claim is a computed fact only when its values are
found in cited business-query/calculation evidence; everything else is a model judgment.
Mirrors run 4cadb5fe ("21일까지 준비되는 1사단 장비"), where 3+1=4 was added by the model."""

import copy

from test_business_queries_v6 import model, run  # noqa: F401  (fixture reuse)


def evidence(model):  # noqa: F811
    return {
        "ev-a": {
            "systemId": "semantic",
            "data": run(model, "asset-availability-summary", {"unit": "모의 1사단"}),
        },
        "ev-c": {
            "systemId": "semantic",
            "data": run(
                model, "asset-maintenance-chain", {"systemId": "atcis", "nativeId": "L-T02"}
            ),
        },
        "ev-s": {"systemId": "atcis", "data": {"items": [{"equipmentId": "L-T01"}]}},
    }


def claim(kind, text, refs, rules=()):
    return {"kind": kind, "text": text, "evidenceRefs": refs, "ruleRefs": list(rules)}


def annotate(claims, items, mode="structured"):
    from platform_api.agent.provenance import annotate_result

    result = {
        "outcome": "answer",
        "answer": "test",
        "findings": [],
        "claims": copy.deepcopy(claims),
        "evidenceIds": [],
        "limitations": [],
        "courses": None,
    }
    annotate_result(result, items, mode)
    return result


def test_values_found_in_business_query_evidence_are_facts(model):  # noqa: F811
    result = annotate(
        [
            claim("observation", "가용 장비는 L-T01, L-U01, L-V01 3대입니다.", ["ev-a"]),
            claim(
                "observation",
                "L-T02는 10-21 15:00 정비 완료가 조건부로 전망됩니다.",
                ["ev-c"],
                ["LOG-LINK-01"],
            ),
        ],
        evidence(model),
    )
    first, second = (c["provenance"] for c in result["claims"])
    assert first["claimClass"] == "fact" and second["claimClass"] == "fact"
    assert "일치" in first["classReason"]
    assert second["unverifiedRuleRefs"] == []


def test_model_arithmetic_inference_and_unknown_ids_are_judgments(model):  # noqa: F811
    result = annotate(
        [
            claim("calculation", "조건부 전망을 포함하면 준비 후보는 4대입니다.", ["ev-a", "ev-c"]),
            claim("inference", "15:00 전망은 전제 조건부라 확정할 수 없습니다.", ["ev-c"]),
            claim("observation", "L-T09는 가용 1대입니다.", ["ev-a"]),
            claim("observation", "L-T01 기록을 확인했습니다.", ["ev-s"]),
            claim("observation", "예하 부대가 포함됩니다.", ["ev-a"]),
        ],
        evidence(model),
    )
    classes = [c["provenance"]["claimClass"] for c in result["claims"]]
    reasons = [c["provenance"]["classReason"] for c in result["claims"]]
    assert classes == ["judgment"] * 5
    assert "4대" in reasons[0]
    assert "추론" in reasons[1]
    assert "L-T09" in reasons[2]
    assert "업무 질의" in reasons[3]
    assert "확인할" in reasons[4]
    # The model's own label is kept for transparency; verification is unchanged.
    assert result["claims"][0]["provenance"]["reportedKind"] == "calculation"
    assert result["outcome"] == "answer"


def test_claim_class_only_for_structured_answers(model):  # noqa: F811
    items = {"ev-s": evidence(model)["ev-s"]}
    result = annotate([claim("observation", "L-T01 기록 1건", ["ev-s"])], items, "native")
    provenance = result["claims"][0]["provenance"]
    assert provenance.get("claimClass") is None and provenance.get("classReason") is None
