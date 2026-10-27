"""Opt-in real-model A/B/C evaluation through the running platform. Never overwrites artifacts."""

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

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
    parser.add_argument("--url", default="http://127.0.0.1:4300")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scenario", choices=list(QUESTIONS), action="append")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; this calls the configured real model")
    if args.output.exists():
        parser.error("output exists; choose a new path")
    modes = ("native", "documents", "structured")
    report: dict[str, Any] = {
        "sourceToolContractVersion": "4",
        "comparisonPolicyVersion": "4-knowledge-abc",
        "model": None,
        "comparisons": [],
        "records": [],
        "limits": "A/B tests supplied knowledge access; B/C tests the structured knowledge stack. Human answer review is required.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with httpx.Client(base_url=args.url, timeout=60) as client:
        config = client.get("/api/v1/config")
        config.raise_for_status()
        if config.json()["sourceToolContractVersion"] != "4":
            raise ValueError("requires v4 platform")
        for index, scenario in enumerate(args.scenario or QUESTIONS):
            response = client.post(
                "/api/v1/comparisons",
                json={
                    "question": QUESTIONS[scenario],
                    "firstKnowledgeMode": modes[index % 3],
                    "baselineReportRef": "atcis:report:R0" if scenario == "F5" else None,
                },
            )
            response.raise_for_status()
            cid = response.json()["comparisonId"]
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
            for mode, rid in comparison.get("runIds", {}).items():
                response = client.get("/api/v1/analyses/" + rid)
                response.raise_for_status()
                run = response.json()
                report["records"].append(
                    {
                        "scenario": scenario,
                        "mode": mode,
                        "knowledgeMode": mode,
                        "state": run,
                        "durationSeconds": run.get("durationSeconds"),
                        "inputTokens": None,
                        "outputTokens": None,
                    }
                )
            save()
    print(
        f"Saved {len(report['records'])} runs to {args.output}; natural-language correctness requires review"
    )


if __name__ == "__main__":
    main()
