"""Opt-in real-model A/B/C evaluation through the running platform. Never overwrites artifacts."""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from evaluation_metrics import measure_run, summarize, valid_context

QUESTIONS = {
    "F1": "육군·해군에 올라온 이 장비 내용 모아줘. L-V01 기준으로.",
    "F2": "모의 해안중대 관련 보고 경과 정리해줘.",
    "F3": "INC-1 지금 어디까지 진행됐어?",
    "F4": "보고가 늘었는데 새로 확인된 내용이 있어?",
    "F5": "지난 보고 이후 상황보고 갱신해줘.",
    "F6": "모의 1사단의 가용한 전차와 제한 사항을 정리해줘.",
    "F7": "모의 1사단과 1함대의 장비 현황을 유형·상태별로 통합해줘.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly authorize billable model runs on the configured platform",
    )
    parser.add_argument("--contract-version", choices=("4", "5"), default="4")
    logistics_questions = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests/fixtures/c2-logistics-demo-v5/expected.json"
        ).read_text(encoding="utf-8")
    )["questions"]
    parser.add_argument("--url", default="http://127.0.0.1:4300")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare immutable context and manifest without model calls",
    )
    parser.add_argument("--max-runs", type=int, default=63)
    parser.add_argument("--max-model-responses", type=int, default=1512)
    parser.add_argument(
        "--max-total-tokens",
        type=int,
        default=2000000,
        help="Observed token stop threshold checked between comparisons; in-flight ABC may exceed it",
    )
    parser.add_argument("--phase", choices=("pilot", "formal"), default="pilot")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Reuse a prior dry-run manifest with the exact pins/model/budgets",
    )
    parser.add_argument(
        "--scenario", choices=list(QUESTIONS) + list(logistics_questions), action="append"
    )
    args = parser.parse_args()
    if not args.live and not args.dry_run:
        parser.error("--live is required; this calls the configured real model")
    if args.output.exists():
        parser.error("output exists; choose a new path")
    questions = logistics_questions if args.contract_version == "5" else QUESTIONS
    if any(q not in questions for q in args.scenario or []):
        parser.error("scenario does not belong to selected contract")
    selected = args.scenario or list(questions)
    if args.repeat < 1 or len(selected) * args.repeat * 3 > args.max_runs:
        parser.error("repeat must be positive and planned runs must not exceed --max-runs")
    modes = ("native", "documents", "structured")
    report: dict[str, Any] = {
        "sourceToolContractVersion": args.contract_version,
        "comparisonPolicyVersion": "5-logistics-abc"
        if args.contract_version == "5"
        else "4-knowledge-abc",
        "model": None,
        "comparisons": [],
        "records": [],
        "attempts": [],
        "limits": "A/B tests supplied knowledge access; B/C tests the structured knowledge stack. Human answer review is required.",
        "phase": args.phase,
        "repeat": args.repeat,
        "scenarios": selected,
        "plannedRuns": len(selected) * args.repeat * 3,
        "caps": {
            "runs": args.max_runs,
            "modelResponses": args.max_model_responses,
            "observedTotalTokens": args.max_total_tokens,
            "boundary": "between ABC comparisons; no hidden re-run",
        },
        "reviewRubric": {
            "gold": "tests/fixtures/c2-logistics-demo-v5/expected.json"
            if args.contract_version == "5"
            else "tests/fixtures/c2-domain-demo-v4/expected.json",
            "accuracy": "Human review: required facts, prohibited conclusions, uncertainty and completeness; not provenance success",
            "evidence": "Mechanical references plus human judgment of logical support",
            "reviewStatus": "unreviewed",
            "simple": ["L0"],
            "complex": ["L1", "L2", "L3", "L4", "L5"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve this artifact before any service request. Concurrent invocations cannot
    # overwrite one another after the earlier existence check.
    with args.output.open("x", encoding="utf-8") as reserved:
        json.dump(
            {"status": "preparing", "records": [], "plannedRuns": report["plannedRuns"]}, reserved
        )

    def save():
        report["summary"] = summarize(report["records"])
        temp = args.output.with_suffix(args.output.suffix + ".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(args.output)

    with httpx.Client(base_url=args.url, timeout=60) as client:
        config = client.get("/api/v1/config")
        config.raise_for_status()
        if config.json()["sourceToolContractVersion"] != args.contract_version:
            raise ValueError("platform contract mismatch")
        if args.contract_version == "5":
            session = client.post("/api/v1/demo-sessions", json={"mode": "compare"})
            session.raise_for_status()
            client.headers["x-demo-session"] = session.json()["sessionId"]
        context_response = client.post("/api/v1/evaluation-context")
        context_response.raise_for_status()
        current = context_response.json()
        fixed = current
        if args.manifest:
            prior = json.loads(args.manifest.read_text(encoding="utf-8"))
            fixed = prior["fixedContext"]
            for key in ("modelId", "agentBudget", "systemPromptVersion", "modelSettings"):
                if fixed[key] != current[key]:
                    raise ValueError("manifest setting changed: " + key)
        report["fixedContext"] = fixed
        report["model"] = fixed["modelId"]
        report["codeRevision"] = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
            ).stdout.strip()
            or "unavailable"
        )
        report["goldHash"] = hashlib.sha256(
            (Path(__file__).resolve().parents[1] / report["reviewRubric"]["gold"]).read_bytes()
        ).hexdigest()
        report["status"] = "dry_run" if args.dry_run else "running"
        save()
        if args.dry_run:
            print(f"Saved no-model manifest for {report['plannedRuns']} runs to {args.output}")
            return
        schedule = [(repeat, scenario) for repeat in range(args.repeat) for scenario in selected]
        for index, (repeat, scenario) in enumerate(schedule):
            responses = sum(r["metrics"]["modelResponses"] for r in report["records"])
            tokens = sum(
                (r["metrics"]["inputTokens"] or 0) + (r["metrics"]["outputTokens"] or 0)
                for r in report["records"]
            )
            remaining_worst_case = 3 * fixed["agentBudget"]["max_iterations"]
            if (
                responses + remaining_worst_case > args.max_model_responses
                or tokens >= args.max_total_tokens
            ):
                report["status"] = "budget_stopped"
                save()
                break
            wall_started = time.monotonic()
            report["attempts"].append(
                {
                    "scenario": scenario,
                    "repeat": repeat + 1,
                    "executionOrder": list(modes[index % 3 :] + modes[: index % 3]),
                    "status": "requesting",
                }
            )
            save()
            try:
                response = client.post(
                    "/api/v1/comparisons",
                    json={
                        "question": questions[scenario],
                        "firstKnowledgeMode": modes[index % 3],
                        "baselineReportRef": "atcis:report:R0" if scenario == "F5" else None,
                        "fixedContext": {
                            k: fixed[k] for k in ("sourceSnapshotSet", "knowledgeSetVersion")
                        },
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                report["attempts"][-1].update(status="service_error", error=str(exc))
                for mode in modes:
                    run: dict[str, Any] = {"status": "service_error", "error": str(exc)}
                    report["records"].append(
                        {
                            "scenario": scenario,
                            "repeat": repeat + 1,
                            "mode": mode,
                            "state": run,
                            "metrics": measure_run(run),
                            "validContext": False,
                        }
                    )
                report["status"] = "stopped_service_error"
                save()
                break
            cid = response.json()["comparisonId"]
            report["attempts"][-1].update(status="accepted", comparisonId=cid)
            save()
            deadline = time.monotonic() + 600
            while True:
                response = client.get("/api/v1/comparisons/" + cid)
                response.raise_for_status()
                comparison = response.json()
                if comparison["status"] not in ("preparing", "running"):
                    break
                if time.monotonic() > deadline:
                    comparison["evaluationWaitTimeout"] = True
                    break
                time.sleep(0.5)
            report["comparisons"].append(comparison)
            report["model"] = (comparison.get("manifest") or {}).get("modelId", report["model"])
            for mode in modes:
                rid = comparison.get("runIds", {}).get(mode)
                if rid:
                    response = client.get("/api/v1/analyses/" + rid)
                    response.raise_for_status()
                    run = response.json()
                else:
                    run = {
                        "status": "preparation_failed",
                        "error": comparison.get("error"),
                        "iterations": [],
                        "toolCalls": [],
                    }
                report["records"].append(
                    {
                        "scenario": scenario,
                        "repeat": repeat + 1,
                        "group": "simple" if scenario == "L0" else "complex",
                        "mode": mode,
                        "knowledgeMode": mode,
                        "state": run,
                        "durationSeconds": measure_run(run)["durationSeconds"],
                        "metrics": measure_run(run),
                        "inputTokens": measure_run(run)["inputTokens"],
                        "outputTokens": measure_run(run)["outputTokens"],
                        "comparisonWallSeconds": time.monotonic() - wall_started,
                        "validContext": valid_context(run, fixed, mode),
                    }
                )
            save()
            if (
                comparison.get("evaluationWaitTimeout")
                or any(not r["validContext"] for r in report["records"])
                or any(r["metrics"]["usageCoverage"] != "complete" for r in report["records"])
            ):
                report["status"] = "stopped_incomplete_context_or_usage"
                save()
                break
        else:
            report["status"] = "finished"
            save()
    print(
        f"Saved {len(report['records'])} runs to {args.output}; natural-language correctness requires review"
    )


if __name__ == "__main__":
    main()
