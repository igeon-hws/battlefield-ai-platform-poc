import pytest


def test_rule_evaluation_is_generic_three_valued_and_never_executes_code():
    from platform_api.agent.domain_tools import classify, evaluate_condition

    assert (
        evaluate_condition(
            {
                "op": "AND",
                "args": [
                    {"op": "EQ", "field": "a", "value": "UP"},
                    {"op": "EQ", "field": "b", "value": "GO"},
                ],
            },
            {"a": "UP"},
        )
        is None
    )
    assert (
        evaluate_condition(
            {
                "op": "OR",
                "args": [
                    {"op": "EQ", "field": "a", "value": "DOWN"},
                    {"op": "EQ", "field": "b", "value": "HOLD"},
                ],
            },
            {"a": "DOWN"},
        )
        is True
    )
    rule = {
        "cases": [{"field": "x", "op": "EQ", "value": "P", "result": "limited"}],
        "default": "unknown",
    }
    assert classify(rule, {"x": "P"}) == "limited"
    assert classify(rule, {}) == "unknown"
    assert evaluate_condition({"op": "EXISTS", "field": "evidenceReport"}, {}) is None
    with pytest.raises(ValueError):
        evaluate_condition({"op": "PYTHON", "value": "1+1"}, {})


async def test_off_cannot_evaluate_semantic_rule_or_cross_run_evidence():
    from platform_api.agent.domain_tools import DomainToolRunner

    pins = {
        "atcis": {
            "datasetId": "c2-domain-demo-v3",
            "epochId": "e",
            "snapshotId": "s",
            "sequence": 1,
            "sourceTime": "2026-10-20T09:10:00Z",
            "stableDataHash": "h",
        }
    }
    runner = DomainToolRunner({}, pins, "off")
    await runner.prepare()
    assert "evaluate_evidence" not in {d["name"] for d in runner.definitions}
    with pytest.raises(ValueError, match="off"):
        await runner.execute(
            "evaluate_evidence",
            {"evidenceIds": ["invented"], "ruleEvidenceId": "invented", "ruleId": "AVAIL-LAND-01"},
        )
    with pytest.raises(ValueError, match="evidence"):
        await runner.execute("aggregate_evidence", {"evidenceIds": ["invented"]})


async def test_claims_cannot_reference_invented_run_evidence():
    import json

    from platform_api.agent.loop import AgentLoop
    from platform_api.agent.tools import ToolRunner
    from test_agent import FakeMCP, FakeProvider, final

    reply = final()
    payload = json.loads(reply["output"][0]["content"][0]["text"])
    payload["claims"] = [
        {"kind": "observation", "text": "unsupported", "evidenceRefs": ["invented"], "ruleRefs": []}
    ]
    reply["output"][0]["content"][0]["text"] = json.dumps(payload)
    result = await AgentLoop(FakeProvider([reply, reply]), ToolRunner(FakeMCP())).run("x")
    assert result["status"] == "validation_failed"


async def test_selected_baseline_is_persisted_for_both_comparison_runs(tmp_path):
    from platform_api.multi_app import ComparisonInput
    from platform_api.multi_repository import MultiRepository

    body = ComparisonInput(question="상황보고 갱신", baselineReportRef="atcis:report:R0")
    repo = MultiRepository(
        tmp_path / "platform.db", policy_version="3-domain-native-off", source_contract="3"
    )
    await repo.open()
    try:
        comparison = await repo.create_comparison(
            body.question, body.firstMode, body.baselineReportRef
        )
        item = await repo.publish_comparison(
            comparison["comparisonId"],
            {"sourceSnapshotSet": {}, "baselineReportRef": body.baselineReportRef},
            {},
        )
        for mode in ("off", "on"):
            run = await repo.get_run(item[mode + "RunId"])
            assert run["baselineReportRef"] == body.baselineReportRef
    finally:
        await repo.close()


def test_empty_reference_query_for_root_only_cannot_claim_complete_subordinate_scope():
    from platform_api.agent.domain_tools import DomainAggregateArgs, DomainToolRunner

    pin = {
        "datasetId": "c2-domain-demo-v3",
        "epochId": "e",
        "snapshotId": "s",
        "sequence": 1,
        "sourceTime": "2026-10-20T09:10:00Z",
        "stableDataHash": "h",
    }
    runner = DomainToolRunner(
        {},
        {"atcis": pin},
        "on",
        {"status": "READY", "graphVersion": "g", "inputStableHashes": {"atcis": "h"}},
    )
    runner.evidence = {
        "native": {
            "systemId": "atcis",
            "originalTool": "list_equipment",
            "arguments": {"snapshotId": "s"},
            "data": {"items": [{"equipmentId": "T1"}], "total": 1, "nextOffset": None},
        },
        "scope": {
            "systemId": "semantic",
            "originalTool": "resolve_unit_scope",
            "data": {
                "status": "resolved",
                "completeness": "complete",
                "unitIds": ["root", "child"],
            },
        },
        "refs": {
            "systemId": "semantic",
            "originalTool": "find_equipment_refs",
            "arguments": {"unitIds": ["root"]},
            "data": {"items": [], "matchedCount": 0, "nextCursor": None, "complete": True},
        },
        "policy": {
            "systemId": "semantic",
            "data": {
                "rules": [
                    {
                        "ruleId": "AGGREGATION-POLICY-01",
                        "definition": {"P1": ["available"], "unit": "unique_registered_asset"},
                    }
                ]
            },
        },
        "states": {
            "systemId": "computed",
            "originalTool": "evaluate_evidence",
            "data": {
                "items": [
                    {
                        "systemId": "atcis",
                        "nativeId": "T1",
                        "inputEvidenceIds": ["native"],
                        "result": "available",
                    }
                ]
            },
        },
    }
    args = DomainAggregateArgs(
        evidenceIds=["native"],
        identityEvidenceIds=["refs"],
        scopeEvidenceIds=["scope"],
        conceptEvidenceIds=["policy"],
        evaluationEvidenceIds=["states"],
    )
    with pytest.raises(ValueError, match="scope"):
        runner.aggregate_domain(args)
