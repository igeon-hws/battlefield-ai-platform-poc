"""Explicit billable 7-pair v3 experiment. No fake provider and no hidden retries."""

import json
import os
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from platform_api.agent.domain_tools import DomainToolRunner
from platform_api.agent.loop import AgentLoop
from platform_api.mcp.client import MCPClient
from platform_api.providers.openai import OpenAIProvider
from test_domain_integration import domain_stack  # noqa: F401 - real independent processes

QUESTIONS = {
    "F1": "육군·해군에 올라온 이 장비 내용 모아줘. L-V01 기준으로.",
    "F2": "모의 해안중대 관련 보고 경과 정리해줘.",
    "F3": "INC-1 건 지금 어디까지 진행됐어?",
    "F4": "INC-1 보고가 늘었는데 새로 확인된 내용이 있어?",
    "F5": "지난 보고 R0 이후 INC-1 상황보고 갱신해줘.",
    "F6": "모의 1사단의 가용한 전차와 제한 사항을 정리해줘.",
    "F7": "모의 1사단과 1함대의 장비 현황을 유형·상태별로 통합해줘.",
}


async def execute_live(env, context, provider, question, mode):
    async with AsyncExitStack() as stack:
        clients = {}
        for system in ("atcis", "knccs") + (("semantic",) if mode == "on" else ()):
            clients[system] = await stack.enter_async_context(
                MCPClient(env[system.upper() + "_MCP_URL"])
            )
        runner = DomainToolRunner(
            clients,
            context["sourceSnapshotSet"],
            mode,
            context["graphInfo"] if mode == "on" else None,
        )
        runner.historical_snapshots = context["baselineSourceSnapshotSet"]
        runner.snapshot["baselineSourceSnapshotSet"] = context["baselineSourceSnapshotSet"]
        state = await AgentLoop(
            provider, runner, max_iterations=24, max_tools=20, deadline=120
        ).run(question)
        return runner, state


@pytest.mark.live
@pytest.mark.neo4j
async def test_real_gpt_domain_seven_pairs(domain_stack):  # noqa: F811 - fixture
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
        pytest.skip("Local OpenAI configuration absent; live experiment NOT completed")
    env = domain_stack
    async with httpx.AsyncClient(base_url=env["SEMANTIC_BASE_URL"], timeout=45) as http:
        r = await http.post("/v1/analysis-contexts", json={"semanticMode": "off"})
        r.raise_for_status()
        off = r.json()
        r = await http.post(
            "/v1/analysis-contexts",
            json={"semanticMode": "on", "sourceSnapshotSet": off["sourceSnapshotSet"]},
        )
        r.raise_for_status()
        on = r.json()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact = Path("artifacts") / f"domain-live-{stamp}.json"
    artifact.parent.mkdir(exist_ok=True)
    provider = OpenAIProvider()
    requested = (
        os.getenv("DOMAIN_LIVE_SCENARIOS", "").split(",")
        if os.getenv("DOMAIN_LIVE_SCENARIOS")
        else list(QUESTIONS)
    )
    questions = {scenario: QUESTIONS[scenario] for scenario in requested}
    report = {
        "startedAt": datetime.now(UTC).isoformat(),
        "model": provider.model,
        "requestedScenarios": requested,
        "context": on,
        "records": [],
        "answerReviewRequired": True,
        "budget": {"maxIterations": 24, "maxTools": 20, "deadlineSeconds": 120},
        "pricing": "not calculated; token usage recorded",
    }
    for scenario, question in questions.items():
        for mode in ("off", "on"):
            started = datetime.now(UTC)
            runner, state = await execute_live(env, on, provider, question, mode)
            usage = [i.get("usage") or {} for i in state["iterations"]]
            record = {
                "scenario": scenario,
                "mode": mode,
                "question": question,
                "registryHash": runner.registry_hash,
                "durationSeconds": (datetime.now(UTC) - started).total_seconds(),
                "inputTokens": sum(u.get("input_tokens", 0) for u in usage),
                "outputTokens": sum(u.get("output_tokens", 0) for u in usage),
                "state": state,
            }
            report["records"].append(record)
            artifact.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "scenario": scenario,
                        "mode": mode,
                        "status": state["status"],
                        "toolCalls": len(state["toolCalls"]),
                        "artifact": str(artifact),
                    }
                ),
                flush=True,
            )
    assert len(report["records"]) == len(questions) * 2
    assert all(r["state"]["status"] == "completed" for r in report["records"]), (
        "Some live runs incomplete; inspect preserved artifact"
    )
    assert all(
        not any(c["name"].startswith("semantic__") for c in r["state"]["toolCalls"])
        for r in report["records"]
        if r["mode"] == "off"
    )
