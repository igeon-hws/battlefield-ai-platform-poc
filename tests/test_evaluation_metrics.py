"""Missing usage stays missing; failed runs remain in denominators."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "evaluation_metrics", Path(__file__).resolve().parents[1] / "scripts/evaluation_metrics.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
measure_run, summarize = module.measure_run, module.summarize


def test_usage_counts_each_model_response_once_and_preserves_missing():
    run = {
        "status": "validation_failed",
        "iterations": [
            {
                "responseId": "r1",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "input_tokens_details": {"cached_tokens": 8},
                    "output_tokens_details": {"reasoning_tokens": 2},
                },
            },
            {"responseId": "r1", "usage": {"input_tokens": 10, "output_tokens": 4}},
            {"responseId": "r2", "usage": None},
        ],
        "toolCalls": [
            {"name": "atcis__list_equipment", "status": "completed"},
            {"name": "semantic__resolve_entity", "status": "failed"},
        ],
    }
    metric = measure_run(run)
    assert metric["inputTokens"] == 10
    assert metric["usageCoverage"] == "partial"
    assert metric["modelResponses"] == 2
    assert metric["cachedTokens"] == 8
    assert metric["toolFailures"] == 1
    assert measure_run({"iterations": []})["inputTokens"] is None
    summary = summarize([{"mode": "native", "scenario": "L0", "state": run}])
    assert summary["native"]["runs"] == 1
    assert summary["native"]["statuses"] == {"validation_failed": 1}
    assert summary["native"]["accuracyReview"] == "unreviewed"


def test_tool_efficiency_metrics_count_duplicates_and_response_size():
    run = {
        "toolCalls": [
            {
                "name": "logistics__list_cargo",
                "arguments": {"snapshotId": "s", "offset": 0},
                "response": {"data": {"items": [{"id": "a"}]}},
                "status": "completed",
            },
            {
                "name": "logistics__list_cargo",
                "arguments": {"offset": 0, "snapshotId": "s"},
                "response": {"data": {"items": [{"id": "a"}]}},
                "status": "completed",
                "cacheHit": True,
            },
        ]
    }
    metric = measure_run(run)
    assert metric["duplicateToolCalls"] == 1
    assert metric["duplicateCallRate"] == 0.5
    assert metric["cacheHits"] == 1
    assert metric["toolResponseCharacters"] > 0


async def test_comparison_repository_preserves_fixed_context(tmp_path):
    from platform_api.knowledge_runtime import KnowledgeRepository

    repo = KnowledgeRepository(tmp_path / "evaluation.db", source_contract="5")
    await repo.open()
    try:
        pins = {"atcis": {"snapshotId": "fixed"}}
        item = await repo.create_comparison(
            "question",
            fixed_context={"sourceSnapshotSet": pins, "knowledgeSetVersion": "knowledge-fixed"},
        )
        assert item["fixedContext"]["sourceSnapshotSet"] == pins
        assert (await repo.comparison(item["comparisonId"]))["fixedContext"] == item["fixedContext"]
    finally:
        await repo.close()


async def test_model_loop_timing_is_saved_separately_from_preparation():
    from platform_api.agent.loop import AgentLoop
    from platform_api.agent.tools import ToolRunner
    from test_agent import FakeMCP, FakeProvider, final

    result = await AgentLoop(FakeProvider([final()]), ToolRunner(FakeMCP())).run("usage")
    assert result["loopDurationSeconds"] >= 0
    assert result["modelLoopStartedAt"]
    assert result["iterations"][0]["durationSeconds"] >= 0
    failed = await AgentLoop(
        FakeProvider([final(evidence=["missing"]), final(evidence=["missing"])]),
        ToolRunner(FakeMCP()),
    ).run("invalid")
    assert failed["validationFailures"] == 2
    assert failed["correctionAttempts"] == 1
