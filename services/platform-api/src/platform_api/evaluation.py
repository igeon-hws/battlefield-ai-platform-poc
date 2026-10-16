"""Independent synthetic gold checks, never imported by graph mapping or Agent tools."""

from datetime import datetime

SCENARIOS = {
    "S1": "모의 1사단의 가용한 탱크를 보여줘. 예하 조직을 포함하고 가용·불가·미확인 수와 원천 객체 ID를 근거와 함께 구분해줘.",
    "S2": "모의 1사단과 모의 1함대의 가용 전력을 통합해서 보여줘. 예하 조직을 포함하고 유형별 수량, 원천 레코드 수와 중복 제거 객체 수, 가용·불가·미확인을 구분해줘.",
    "S3": "U-A01과 C-K77은 같은 객체야? 두 체계의 상태와 공동지원 배속, 출처, 관측 시각과 동일성 근거를 보여줘. 중복 집계하지 않도록 설명해줘.",
}


def metrics(run):
    usage = [i.get("usage") or {} for i in run.get("iterations", [])]
    input_tokens = sum(u.get("input_tokens", 0) for u in usage)
    output_tokens = sum(u.get("output_tokens", 0) for u in usage)
    return {
        "toolCalls": len(run.get("toolCalls", [])),
        "modelTurns": len(run.get("iterations", [])),
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
        "registryHash": run.get("registryHash"),
        "status": run["status"],
        "executionSeconds": (
            (
                datetime.fromisoformat(run["finishedAt"]) - datetime.fromisoformat(run["startedAt"])
            ).total_seconds()
            if run.get("startedAt") and run.get("finishedAt")
            else None
        ),
    }


def grade_legacy_run(scenario, run):
    base = {"basis": "tool-evidence-and-counts", "answerReviewRequired": True}
    if run["status"] != "completed":
        return {**base, "correct": False, "reason": "run_not_completed"}
    aggregates = [e["data"] for e in run.get("evidence", []) if e["tool"] == "aggregate_evidence"]
    if scenario in ("S1", "S2"):
        if not aggregates:
            return {**base, "correct": None, "reason": "no_deterministic_aggregation_evidence"}
        data = aggregates[-1]
        expected = (
            {"rawRecordCount": 4, "confirmedAvailable": 2, "confirmedUnavailable": 1, "unknown": 1}
            if scenario == "S1"
            else {
                "rawRecordCount": 8,
                "resolvedUniqueCount": 7,
                "confirmedAvailable": 3,
                "confirmedUnavailable": 2,
                "unknown": 1,
                "conflicting": 1,
            }
        )
        checks = {k: data.get(k) == v for k, v in expected.items()}
        if scenario == "S1":
            actual = {
                ref["nativeId"]
                for item in data.get("items", [])
                if item["status"] == "available"
                for ref in item["sourceRefs"]
            }
            checks["availableIds"] = actual == {"T-A01", "T-A02"}
        else:
            actual = {item.get("canonicalId") for item in data.get("items", [])}
            checks["canonicalIds"] = actual == {
                "EX-T01",
                "EX-T02",
                "EX-T03",
                "EX-T04",
                "EX-S01",
                "EX-S02",
                "EX-U01",
            }
        return {**base, "correct": all(checks.values()), "checks": checks}
    if scenario != "S3":
        raise ValueError("unknown evaluation scenario")
    identity = any(
        e["data"].get("canonicalId") == "EX-U01" and e["data"].get("status") == "resolved"
        for e in run.get("evidence", [])
    )
    reports = {}
    for evidence in run.get("evidence", []):
        data, system = evidence["data"], evidence.get("systemId")
        rows = [data["item"]] if "item" in data else data.get("items", [])
        for row in rows:
            if system == "atcis" and row.get("trackKey") == "U-A01" and "readyCode" in row:
                reports["atcis"] = row
            if system == "knccs" and row.get("contactNo") == "C-K77" and "serviceability" in row:
                reports["knccs"] = row
    raw_identity = len(reports) == 2 and all(
        r.get("exerciseAssetRef") == "EX-U01" for r in reports.values()
    )
    checks = {
        "explicitIdentity": identity or raw_identity,
        "bothSourceReports": len(reports) == 2,
        "sourceConflict": reports.get("atcis", {}).get("readyCode") == "R"
        and reports.get("knccs", {}).get("serviceability") == "NOT_READY",
    }
    return {
        **base,
        "correct": all(checks.values()),
        "checks": checks,
        "reason": "Natural-language conflict explanation and unknown cause need human review",
    }


def grade_run(scenario, run):
    if run.get("semanticPolicyVersion") != "2-native-off":
        return grade_legacy_run(scenario, run)
    base = {"basis": "v2-tool-evidence-not-free-text", "answerReviewRequired": True}
    if run["status"] != "completed":
        return {**base, "correct": False, "reason": "run_not_completed"}
    evidence = run.get("evidence", [])
    aggregates = [e["data"] for e in evidence if e["tool"] == "aggregate_evidence"]
    off = run["semanticMode"] == "off"
    checks = {}
    if off:
        checks["noSemanticCalls"] = not any(
            c.get("name", "").startswith("semantic__") for c in run.get("toolCalls", [])
        )
        checks["noSemanticAggregation"] = all(
            d.get("interpretation") == "native_records_only"
            and not ({"resolvedUniqueCount", "canonicalId", "confirmedAvailable"} & d.keys())
            for d in aggregates
        )
        expected = {("atcis", n) for n in ("T-A01", "T-A02", "T-A03", "T-A04")}
        if scenario == "S2":
            expected |= {
                ("atcis", "U-A01"),
                ("knccs", "C-K77"),
                ("knccs", "V-K01"),
                ("knccs", "V-K02"),
            }
        actual = {
            (item.get("systemId"), item.get("nativeId"))
            for d in aggregates
            for item in d.get("items", [])
        }
        if scenario in ("S1", "S2"):
            checks["nativeScopeCoverage"] = expected <= actual
            return {
                **base,
                "correct": all(checks.values()) if aggregates else None,
                "checks": checks,
                "reason": "Raw evidence coverage only; any cross-system identity/count in answer is model inference requiring review",
            }
    elif scenario in ("S1", "S2"):
        if not aggregates:
            return {**base, "correct": None, "reason": "no_aggregation_evidence"}
        data = aggregates[-1]
        expected_counts = (
            {"rawRecordCount": 4, "confirmedAvailable": 2, "confirmedUnavailable": 1, "unknown": 1}
            if scenario == "S1"
            else {
                "rawRecordCount": 8,
                "resolvedUniqueCount": 7,
                "confirmedAvailable": 4,
                "confirmedUnavailable": 2,
                "unknown": 1,
                "conflicting": 0,
            }
        )
        checks.update({k: data.get(k) == v for k, v in expected_counts.items()})
        checks["semanticAggregation"] = data.get("interpretation") == "semantic_evidence"
        ids = {
            r["nativeId"]
            for i in data.get("items", [])
            if i.get("status") == "available"
            for r in i["sourceRefs"]
        }
        checks["availableIds"] = ids == (
            {"T-A01", "T-A02"}
            if scenario == "S1"
            else {"T-A01", "T-A02", "V-K01", "U-A01", "C-K77"}
        )
        return {**base, "correct": all(checks.values()), "checks": checks}
    reports = {}
    for e in evidence:
        d = e["data"]
        for row in [d["item"]] if "item" in d else d.get("items", []):
            if row.get("trackKey") == "U-A01" and "readyCode" in row:
                reports["atcis"] = row
            if row.get("contactNo") == "C-K77" and "serviceability" in row:
                reports["knccs"] = row
    checks["consistentSourceState"] = (
        reports.get("atcis", {}).get("readyCode") == "R"
        and reports.get("knccs", {}).get("serviceability") == "READY"
    )
    checks["sharedSupport"] = len(reports) == 2 and all(
        r.get("assignmentRole") == "shared_support" for r in reports.values()
    )
    if not off:
        checks["semanticIdentity"] = any(
            i.get("canonicalId") == "EX-U01"
            for e in evidence
            if e.get("systemId") == "semantic"
            for i in (e["data"].get("items") or [e["data"]])
        )
    return {**base, "correct": all(checks.values()), "checks": checks}
