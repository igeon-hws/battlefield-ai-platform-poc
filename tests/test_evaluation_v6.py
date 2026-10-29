"""v6 evaluation metrics for the three presentation claims: consistency, traceability,
changeability. Automatic grading is advisory; Human Review stays authoritative."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

FIXTURE = json.loads(
    Path("tests/fixtures/c2-ontology-demo-v6/expected.json").read_text(encoding="utf-8")
)


def run(answer, claims=(), calls=(), evidence=(), status="completed"):
    return {
        "status": status,
        "result": {
            "answer": answer,
            "findings": [],
            "claims": list(claims),
            "limitations": [],
        }
        if status == "completed"
        else None,
        "toolCalls": list(calls),
        "evidence": list(evidence),
        "iterations": [],
    }


def test_fixture_groups_cover_every_question_and_gold_is_independent():
    groups = FIXTURE["groups"]
    grouped = {q for name, ids in groups.items() if name != "definitionChange" for q in ids}
    assert grouped == set(FIXTURE["questions"]) == set(FIXTURE["gold"])
    assert set(groups["definitionChange"]) == set(FIXTURE["variantGold"])
    assert set(FIXTURE["holdOut"]) <= set(FIXTURE["questions"])
    for name in ("uncovered",):
        assert all(FIXTURE["expectedQueries"][q] == [] for q in groups[name])


def test_grade_matches_facts_and_flags_forbidden_conclusions():
    from evaluation_metrics import grade

    good = run(
        "모의 1사단 예하 전차는 2대입니다. L-T01은 가용, L-T02는 제한(PMC)입니다. 가용 전차는 1대입니다."
    )
    result = grade(good, FIXTURE["gold"]["K1"])
    assert result["verdict"] == "pass" and result["forbiddenHits"] == 0
    wrong = run("L-T01 가용, L-T02 제한. 가용 전차는 2대입니다.")
    result = grade(wrong, FIXTURE["gold"]["K1"])
    assert result["verdict"] == "fail" and result["forbiddenHits"] == 1
    assert grade(run("", status="failed"), FIXTURE["gold"]["K1"])["verdict"] == "no_answer"
    variant = run("L-T01, L-T02(제한 PMC) 모두 집계 기준상 가용 2대입니다.")
    assert grade(variant, FIXTURE["variantGold"]["K1"])["verdict"] == "pass"


def test_consistency_is_the_share_of_runs_matching_the_modal_fact_set():
    from evaluation_metrics import consistency

    gold = FIXTURE["gold"]["K1"]
    same = "L-T01 가용, L-T02 제한(PMC). 가용 전차는 1대입니다."
    records = [
        {"scenario": "K1", "mode": "documents", "variant": False, "state": run(same)},
        {"scenario": "K1", "mode": "documents", "variant": False, "state": run(same)},
        {"scenario": "K1", "mode": "documents", "variant": False, "state": run("L-T01만 있음")},
    ]
    result = consistency(records, {"K1": gold}, {})
    assert result[("K1", "documents", False)]["runs"] == 3
    assert round(result[("K1", "documents", False)]["consistency"], 2) == 0.67


def test_trace_completeness_counts_claims_reaching_rules_graph_and_source():
    from evaluation_metrics import trace_completeness

    evidence = [
        {
            "evidenceId": "ev-bq",
            "systemId": "semantic",
            "data": {"queryId": "asset-availability-summary"},
        },
        {"evidenceId": "ev-doc", "systemId": "knowledge", "data": {}},
        {"evidenceId": "ev-src", "systemId": "atcis", "data": {}},
    ]
    claims = [
        {
            "evidenceRefs": ["ev-bq"],
            "ruleRefs": ["AGGREGATION-POLICY-01"],
            "provenance": {"sources": ["semantic"], "unverifiedRuleRefs": []},
        },
        {
            "evidenceRefs": ["ev-doc"],
            "ruleRefs": [],
            "provenance": {"sources": ["document"], "unverifiedRuleRefs": []},
        },
        {
            "evidenceRefs": ["ev-src"],
            "ruleRefs": [],
            "provenance": {"sources": ["source"], "unverifiedRuleRefs": []},
        },
    ]
    result = trace_completeness(run("x", claims=claims, evidence=evidence))
    assert result == {"claims": 3, "traced": 1, "documentCited": 1, "sourceOnly": 1, "ratio": 1 / 3}


def test_business_query_selection_accuracy():
    from evaluation_metrics import query_selection

    calls = [
        {
            "name": "semantic__run_business_query",
            "arguments": {"queryId": "asset-availability-summary"},
        }
    ]
    assert query_selection(run("x", calls=calls), ["asset-availability-summary"])["correct"] is True
    assert query_selection(run("x", calls=calls), [])["correct"] is False
    assert query_selection(run("x"), [])["correct"] is True


def test_v6_summary_groups_by_group_and_mode_without_a_single_average():
    from evaluation_metrics import summarize_v6

    records = [
        {
            "scenario": "K1",
            "mode": "structured",
            "variant": False,
            "state": run("L-T01 가용, L-T02 제한. 가용 전차는 1대입니다."),
        },
        {
            "scenario": "K7",
            "mode": "structured",
            "variant": False,
            "state": run("현장확인 완료, 식별 진행 중, 검토 미착수"),
        },
        {
            "scenario": "K1",
            "mode": "structured",
            "variant": True,
            "state": run("가용 2대, L-T01, L-T02 제한"),
        },
    ]
    summary = summarize_v6(records, FIXTURE)
    assert set(summary["byGroup"]) >= {"covered", "uncovered", "definitionChange"}
    assert summary["byGroup"]["covered"]["structured"]["verdicts"] == {"pass": 1}
    assert summary["byGroup"]["definitionChange"]["structured"]["newDefinitionCompliance"] == 1.0
    assert "overall" not in summary
    assert summary["method"].startswith("advisory")
