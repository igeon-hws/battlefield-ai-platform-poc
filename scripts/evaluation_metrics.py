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
