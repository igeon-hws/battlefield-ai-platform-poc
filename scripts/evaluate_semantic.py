"""Evaluate a RUNNING full-profile platform using its configured real provider."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from platform_api.evaluation import SCENARIOS, grade_run, metrics


async def evaluate(args):
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = (
        json.loads(output.read_text(encoding="utf-8"))
        if output.exists()
        else {"startedAt": datetime.now(UTC).isoformat(), "records": []}
    )
    async with httpx.AsyncClient(base_url=args.base_url, timeout=15) as client:
        situation_response = await client.get("/api/v1/situation")
        situation_response.raise_for_status()
        sources = situation_response.json().get("sources", {})
        if set(sources) != {"atcis", "knccs"} or any(s.get("running") for s in sources.values()):
            raise RuntimeError("Both source simulators must be connected and paused for evaluation")
        scenarios = (
            SCENARIOS if args.scenario == "all" else {args.scenario: SCENARIOS[args.scenario]}
        )
        for scenario, question in scenarios.items():
            for repetition in range(args.repetitions):
                if any(
                    r["scenario"] == scenario and r["repetition"] == repetition + 1
                    for r in report["records"]
                ):
                    continue
                response = await client.post(
                    "/api/v1/comparisons",
                    json={
                        "question": question,
                        "firstMode": "off" if repetition % 2 == 0 else "on",
                    },
                )
                response.raise_for_status()
                cid = response.json()["comparisonId"]
                for _ in range(660):
                    response = await client.get("/api/v1/comparisons/" + cid)
                    response.raise_for_status()
                    comparison = response.json()
                    if comparison["status"] not in ("preparing", "running"):
                        break
                    await asyncio.sleep(0.5)
                runs = {}
                for mode in ("off", "on"):
                    if comparison.get(mode + "RunId"):
                        response = await client.get(
                            "/api/v1/analyses/" + comparison[mode + "RunId"]
                        )
                        response.raise_for_status()
                        runs[mode] = response.json()
                record = {
                    "scenario": scenario,
                    "repetition": repetition + 1,
                    "comparison": comparison,
                    "runs": runs,
                    "metrics": {m: metrics(r) for m, r in runs.items()},
                    "grades": {m: grade_run(scenario, r) for m, r in runs.items()},
                    "comparisonSeconds": (
                        (
                            datetime.fromisoformat(comparison["finishedAt"])
                            - datetime.fromisoformat(comparison["createdAt"])
                        ).total_seconds()
                        if comparison.get("finishedAt")
                        else None
                    ),
                }
                report["records"].append(record)
                output.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            "scenario": scenario,
                            "repetition": repetition + 1,
                            "status": comparison["status"],
                            "grades": {m: g["correct"] for m, g in record["grades"].items()},
                            "metrics": record["metrics"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:4300")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--scenario", choices=("all", "S1", "S2", "S3"), default="all")
    parser.add_argument("--output", default="artifacts/semantic-evaluation-v2.json")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    asyncio.run(evaluate(args))


if __name__ == "__main__":
    main()
