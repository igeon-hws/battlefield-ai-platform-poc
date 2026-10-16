from platform_api.evaluation import grade_run, metrics


def run(data):
    return {
        "status": "completed",
        "result": {"answer": "T-A01 T-A02"},
        "toolCalls": [{"name": "aggregate_evidence"}],
        "iterations": [{"usage": {"input_tokens": 100, "output_tokens": 20}}],
        "evidence": [{"tool": "aggregate_evidence", "data": data}],
    }


def test_s1_grading_rejects_wrong_scope_and_missing_aggregation():
    good = run(
        {
            "rawRecordCount": 4,
            "confirmedAvailable": 2,
            "confirmedUnavailable": 1,
            "unknown": 1,
            "items": [
                {"status": "available", "sourceRefs": [{"systemId": "atcis", "nativeId": "T-A01"}]},
                {"status": "available", "sourceRefs": [{"systemId": "atcis", "nativeId": "T-A02"}]},
            ],
        }
    )
    assert grade_run("S1", good)["correct"] is True
    wrong = run({**good["evidence"][0]["data"], "rawRecordCount": 5, "confirmedAvailable": 3})
    assert grade_run("S1", wrong)["correct"] is False
    assert grade_run("S1", {**good, "evidence": []})["correct"] is None
    assert metrics(good)["totalTokens"] == 120


def test_s2_counts_require_explicit_conflict_and_no_double_count():
    data = {
        "rawRecordCount": 8,
        "resolvedUniqueCount": 7,
        "confirmedAvailable": 3,
        "confirmedUnavailable": 2,
        "unknown": 1,
        "conflicting": 1,
        "items": [
            {"canonicalId": cid}
            for cid in ("EX-T01", "EX-T02", "EX-T03", "EX-T04", "EX-S01", "EX-S02", "EX-U01")
        ],
    }
    assert grade_run("S2", run(data))["correct"] is True
    assert grade_run("S2", run({**data, "resolvedUniqueCount": 8}))["correct"] is False


def test_identity_records_do_not_replace_equipment_status_reports():
    evidence = []
    for system, key, native, status in (
        ("atcis", "trackKey", "U-A01", {"readyCode": "R"}),
        ("knccs", "contactNo", "C-K77", {"serviceability": "NOT_READY"}),
    ):
        identity = {key: native, "exerciseAssetRef": "EX-U01"}
        evidence.append(
            {
                "tool": system + "__get_equipment",
                "systemId": system,
                "data": {"item": {**identity, **status}},
            }
        )
        evidence.append(
            {
                "tool": system + "__list_identity_records",
                "systemId": system,
                "data": {"items": [identity]},
            }
        )
    assert grade_run("S3", {"status": "completed", "evidence": evidence})["correct"] is True


def test_metrics_reports_measured_execution_time_and_unknown_for_old_runs():
    data = {
        "status": "completed",
        "startedAt": "2026-10-16T00:00:00+00:00",
        "finishedAt": "2026-10-16T00:00:12.500000+00:00",
    }
    assert metrics(data)["executionSeconds"] == 12.5
    assert metrics({"status": "completed"})["executionSeconds"] is None


def test_v2_evaluation_keeps_off_native_and_on_semantic_results_separate():
    native = run(
        {
            "interpretation": "native_records_only",
            "rawRecordCount": 4,
            "items": [
                {"systemId": "atcis", "nativeId": n} for n in ("T-A01", "T-A02", "T-A03", "T-A04")
            ],
        }
    )
    native.update(semanticMode="off", semanticPolicyVersion="2-native-off")
    assert grade_run("S1", native)["checks"]["noSemanticAggregation"] is True
    leaked = {
        **native,
        "evidence": [{"tool": "aggregate_evidence", "data": {"resolvedUniqueCount": 7}}],
    }
    assert grade_run("S1", leaked)["correct"] is False
