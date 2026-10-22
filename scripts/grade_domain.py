"""Offline evidence checks. Does not score natural-language correctness or call an LLM."""

import argparse
import json
from pathlib import Path


def rule_ids(value):
    if isinstance(value, dict):
        found = {value["ruleId"]} if isinstance(value.get("ruleId"), str) else set()
        return found | {r for nested in value.values() for r in rule_ids(nested)}
    if isinstance(value, list):
        return {r for nested in value for r in rule_ids(nested)}
    return set()


def grade_record(record, expected):
    state = record["state"]
    evidence = state.get("evidence", [])
    ids = {e["evidenceId"] for e in evidence}
    claims = (state.get("result") or {}).get("claims", [])
    semantic = [e for e in evidence if e["systemId"] == "semantic"]
    proof_rules = {r for e in semantic for r in rule_ids(e["data"])}
    cited_rules = {r for c in claims for r in c.get("ruleRefs", [])}
    missing = sorted(set(expected.get("ruleIds", [])) - proof_rules)
    boundary = (
        not any(c["name"].startswith("semantic__") for c in state.get("toolCalls", []))
        and not semantic
        and not any(
            e["originalTool"] == "evaluate_evidence"
            or e["data"].get("interpretation") == "semantic_evidence"
            for e in evidence
        )
    )
    deterministic = None
    aggregates = [
        e["data"]
        for e in evidence
        if e["originalTool"] == "aggregate_evidence"
        and e["data"].get("interpretation") == "semantic_evidence"
    ]
    if aggregates and "counts" in expected:
        result = aggregates[-1]
        actual_ids = {i["canonicalId"] for i in result["items"]}
        deterministic = result["counts"] == expected["counts"] and actual_ids == set(
            expected["includedIds"]
        )
    if record["scenario"] == "F3":
        evaluations = [
            e["data"]
            for e in evidence
            if e["originalTool"] == "evaluate_evidence"
            and e["data"].get("ruleId") == "ACTIVITY-STEP-01"
        ]
        if evaluations:
            outcomes = {
                i["record"]["stepCode"]: i["result"] for e in evaluations for i in e["items"]
            }
            deterministic = all(
                outcomes.get(step) == expected[step]
                for step in ("SITE_CHECK", "IDENTIFICATION", "REVIEW")
            )
    return {
        "executionCompleted": state["status"] == "completed",
        "offBoundaryValid": boundary if record["mode"] == "off" else None,
        "claimReferencesValid": all(set(c.get("evidenceRefs", [])) <= ids for c in claims),
        "queriedRuleIds": sorted(proof_rules),
        "citedRuleIds": sorted(cited_rules),
        "missingRuleIds": missing if record["mode"] == "on" else [],
        "deterministicFactsMatch": deterministic,
        "answerReviewRequired": True,
        "naturalLanguageAccuracy": "not_automatically_scored",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--gold", type=Path, default=Path("tests/fixtures/c2-domain-demo-v3/expected.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.artifact.read_text(encoding="utf-8"))
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    layers = {
        "F1": ["L1", "L2"],
        "F2": ["L3", "L5"],
        "F3": ["L6"],
        "F4": ["L5"],
        "F5": ["L5", "L6", "L7"],
        "F6": ["L2", "L3", "L4"],
        "F7": ["L1", "L2", "L3", "L4", "L7"],
    }
    result = {
        "sourceArtifact": str(args.artifact),
        "model": report["model"],
        "records": [
            {
                "scenario": r["scenario"],
                "mode": r["mode"],
                "layers": layers[r["scenario"]],
                "grade": grade_record(r, gold[r["scenario"]]),
                "toolCalls": len(r["state"].get("toolCalls", [])),
                "durationSeconds": r["durationSeconds"],
                "inputTokens": r["inputTokens"],
                "outputTokens": r["outputTokens"],
            }
            for r in report["records"]
        ],
        "limits": "Evidence-only checks. No fabricated answer score or automatic ON superiority. Same artifact context applies to each pair. No dollar price inferred from token usage.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"gradedRecords": len(result["records"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
