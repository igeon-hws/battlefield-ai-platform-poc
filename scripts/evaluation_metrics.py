"""Offline measurements, independent of natural-language correctness review."""

import json
from collections import Counter
from datetime import datetime
from statistics import median


def valid_context(run, fixed, mode):
    names = run.get("registryBindings") or {}
    return (
        run.get("sourceSnapshotSet") == fixed["sourceSnapshotSet"]
        and (mode == "native" or run.get("knowledgeSetVersion") == fixed["knowledgeSetVersion"])
        and (mode == "structured" or not any(n.startswith("semantic__") for n in names))
        and (mode != "native" or not any(n.startswith("knowledge__") for n in names))
    )


def measure_run(run):
    def elapsed(start, end):
        try:
            return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        except (TypeError, ValueError):
            return None

    iterations = []
    seen = set()
    for index, item in enumerate(run.get("iterations", [])):
        key = item.get("responseId") or ("iteration", index)
        if key not in seen:
            seen.add(key)
            iterations.append(item)
    usages = [item["usage"] for item in iterations if isinstance(item.get("usage"), dict)]

    def total(key, detail=None):
        values = [(u.get(detail) or {}).get(key) if detail else u.get(key) for u in usages]
        numbers = [v for v in values if isinstance(v, (int, float))]
        return sum(numbers) if numbers else None

    calls = run.get("toolCalls", [])
    signatures = [
        json.dumps([call.get("name"), call.get("arguments")], sort_keys=True, ensure_ascii=False)
        for call in calls
    ]
    duplicate_calls = len(signatures) - len(set(signatures))
    return {
        "inputTokens": total("input_tokens"),
        "outputTokens": total("output_tokens"),
        "cachedTokens": total("cached_tokens", "input_tokens_details"),
        "reasoningTokens": total("reasoning_tokens", "output_tokens_details"),
        "usageCoverage": "complete"
        if iterations
        and len(usages) == len(iterations)
        and all(
            isinstance(u.get(k), int) for u in usages for k in ("input_tokens", "output_tokens")
        )
        else "partial"
        if usages
        else "unavailable",
        "modelResponses": len(iterations),
        "validationFailures": run.get("validationFailures"),
        "correctionAttempts": run.get("correctionAttempts"),
        "unverifiedRuleReferences": sum(
            len(c.get("provenance", {}).get("unverifiedRuleRefs", []))
            for c in (run.get("result") or {}).get("claims", [])
        ),
        "toolCalls": len(calls),
        "duplicateToolCalls": duplicate_calls,
        "duplicateCallRate": duplicate_calls / len(calls) if calls else 0.0,
        "cacheHits": sum(bool(call.get("cacheHit")) for call in calls),
        "toolResponseCharacters": sum(
            len(json.dumps(call["response"], ensure_ascii=False))
            for call in calls
            if "response" in call
        ),
        "toolFailures": sum(c.get("status") not in ("completed", "succeeded") for c in calls),
        "toolsByService": dict(Counter(c.get("name", "unknown").split("__")[0] for c in calls)),
        "durationSeconds": run.get("loopDurationSeconds", run.get("durationSeconds")),
        "loopDurationSeconds": run.get("loopDurationSeconds"),
        "requestToFinishSeconds": elapsed(run.get("createdAt"), run.get("finishedAt")),
        "runStartToFirstModelSeconds": elapsed(run.get("startedAt"), run.get("modelLoopStartedAt")),
        "responseModels": sorted({i["model"] for i in iterations if i.get("model")}),
        "knowledgePreparationSeconds": run.get("knowledgePreparationSeconds"),
        "accuracyReview": "unreviewed",
        "evidenceSupportReview": "unreviewed",
    }


def summarize(records):
    result = {}
    for mode in sorted({r["mode"] for r in records}):
        group = [r for r in records if r["mode"] == mode]
        durations = [
            measure_run(r["state"])["durationSeconds"]
            for r in group
            if isinstance(measure_run(r["state"])["durationSeconds"], (float, int))
        ]
        result[mode] = {
            "runs": len(group),
            "statuses": dict(Counter(r["state"].get("status", "unknown") for r in group)),
            "durationMedianSeconds": median(durations) if durations else None,
            "durationRangeSeconds": [min(durations), max(durations)] if durations else None,
            "accuracyReview": "unreviewed",
            "byScenario": {
                scenario: {
                    "runs": sum(r["scenario"] == scenario for r in group),
                    "statuses": dict(
                        Counter(
                            r["state"].get("status", "unknown")
                            for r in group
                            if r["scenario"] == scenario
                        )
                    ),
                }
                for scenario in sorted({r["scenario"] for r in group})
            },
            "usageCoverage": dict(Counter(measure_run(r["state"])["usageCoverage"] for r in group)),
            "scope": "All attempted runs, including failures; correctness requires independent review.",
        }
    return result


def review_template(report):
    return {
        "goldHash": report["goldHash"],
        "reviewer": None,
        "instructions": "Score facts and prohibited conclusions against independent gold. Evidence existence is not logical support. Leave unreviewed values null.",
        "judgments": [
            {
                "runId": r["state"].get("runId"),
                "scenario": r["scenario"],
                "mode": r["mode"],
                "repeat": r.get("repeat", 1),
                "factCoverage": None,
                "fullyCorrect": None,
                "prohibitedConclusion": None,
                "evidenceSupport": None,
                "interpretationKey": None,
                "notes": None,
            }
            for r in report["records"]
        ],
    }


def main():
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Export an independent human review worksheet and offline measured summaries; never invokes a model."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-review", action="store_true")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = (
        review_template(report)
        if args.export_review
        else {
            "summary": summarize(report["records"]),
            "measurements": [
                {
                    "scenario": r["scenario"],
                    "mode": r["mode"],
                    "repeat": r.get("repeat", 1),
                    **measure_run(r["state"]),
                }
                for r in report["records"]
            ],
        }
    )
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()


# v6: advisory automatic checks for consistency, traceability and changeability.
ADVISORY = "advisory regex over answer text; Human Review is authoritative"


def answer_text(run):
    result = run.get("result") or {}
    parts = [result.get("answer") or ""]
    parts += [f.get("text", "") for f in result.get("findings") or []]
    parts += [c.get("text", "") for c in result.get("claims") or []]
    parts += list(result.get("limitations") or [])
    return "\n".join(parts)


def grade(run, gold):
    import re

    if run.get("status") != "completed" or not run.get("result"):
        return {"verdict": "no_answer", "facts": {}, "forbidden": {}, "method": ADVISORY}
    text = answer_text(run)
    facts = {f["id"]: bool(re.search(f["pattern"], text, re.MULTILINE)) for f in gold["facts"]}
    forbidden = {
        f["id"]: bool(re.search(f["pattern"], text, re.MULTILINE)) for f in gold["forbidden"]
    }
    matched, hits = sum(facts.values()), sum(forbidden.values())
    verdict = "fail" if hits or not matched else "pass" if matched == len(facts) else "partial"
    return {
        "verdict": verdict,
        "facts": facts,
        "forbidden": forbidden,
        "factsMatched": matched,
        "factsTotal": len(facts),
        "forbiddenHits": hits,
        "method": ADVISORY,
    }


def consistency(records, gold, variant_gold):
    groups: dict[tuple, list] = {}
    for record in records:
        key = (record["scenario"], record["mode"], bool(record.get("variant")))
        reference = (variant_gold if key[2] else gold).get(record["scenario"])
        if reference is None:
            continue
        graded = grade(record["state"], reference)
        groups.setdefault(key, []).append(
            tuple(sorted(k for k, v in graded["facts"].items() if v))
            if graded["verdict"] != "no_answer"
            else None
        )
    result = {}
    for key, sets in groups.items():
        modal, count = Counter(sets).most_common(1)[0]
        result[key] = {
            "runs": len(sets),
            "consistency": count / len(sets),
            "modalFacts": list(modal) if modal is not None else None,
        }
    return result


def trace_completeness(run):
    result = run.get("result") or {}
    evidence = {e["evidenceId"]: e for e in run.get("evidence", [])}
    claims = result.get("claims") or []
    traced = document = source_only = 0
    for claim in claims:
        provenance = claim.get("provenance") or {}
        sources = set(provenance.get("sources") or [])
        cited = [evidence.get(ref) or {} for ref in claim.get("evidenceRefs", [])]
        if any("queryId" in (e.get("data") or {}) for e in cited) or (
            "semantic" in sources
            and claim.get("ruleRefs")
            and not provenance.get("unverifiedRuleRefs")
        ):
            traced += 1
        elif "document" in sources:
            document += 1
        elif sources == {"source"}:
            source_only += 1
    return {
        "claims": len(claims),
        "traced": traced,
        "documentCited": document,
        "sourceOnly": source_only,
        "ratio": traced / len(claims) if claims else 0.0,
    }


def query_selection(run, expected):
    used = sorted(
        {
            str(query)
            for c in run.get("toolCalls", [])
            if c.get("name", "").endswith("run_business_query")
            and (query := (c.get("arguments") or {}).get("queryId"))
        }
    )
    return {
        "used": used,
        "expected": expected,
        "correct": set(expected) <= set(used) if expected else not used,
    }


def summarize_v6(records, fixture):
    groups = fixture["groups"]
    by_group: dict[str, dict] = {}
    checks = consistency(records, fixture["gold"], fixture["variantGold"])
    for name, scenarios in groups.items():
        for mode in sorted({r["mode"] for r in records}):
            chosen = [
                r
                for r in records
                if r["mode"] == mode
                and r["scenario"] in scenarios
                and bool(r.get("variant")) == (name == "definitionChange")
            ]
            if not chosen:
                continue
            gold = fixture["variantGold"] if name == "definitionChange" else fixture["gold"]
            grades = [grade(r["state"], gold[r["scenario"]]) for r in chosen]
            traces = [trace_completeness(r["state"]) for r in chosen]
            item = {
                "runs": len(chosen),
                "verdicts": dict(Counter(g["verdict"] for g in grades)),
                "forbiddenHits": sum(g.get("forbiddenHits", 0) for g in grades),
                "consistency": {
                    s: checks[(s, mode, name == "definitionChange")]["consistency"]
                    for s in sorted({r["scenario"] for r in chosen})
                },
                "traceRatio": sum(t["traced"] for t in traces)
                / max(sum(t["claims"] for t in traces), 1),
                "toolCallsMedian": median(measure_run(r["state"])["toolCalls"] for r in chosen),
            }
            if mode == "structured":
                item["querySelectionAccuracy"] = sum(
                    query_selection(r["state"], fixture["expectedQueries"][r["scenario"]])[
                        "correct"
                    ]
                    for r in chosen
                ) / len(chosen)
            if name == "definitionChange":
                item["newDefinitionCompliance"] = sum(g["verdict"] == "pass" for g in grades) / len(
                    grades
                )
            by_group.setdefault(name, {})[mode] = item
    return {
        "byGroup": by_group,
        "method": ADVISORY,
        "holdOut": fixture["holdOut"],
        "scope": "Per group and condition; no single overall average. Failures are counted.",
    }
