import asyncio
import json

import pytest
from platform_api.agent.loop import AgentLoop
from platform_api.agent.tools import ToolRunner
from test_agent import FakeMCP, FakeProvider, call, final


async def test_readable_run_file_records_loop_without_changing_result(tmp_path):
    from platform_api.run_log import RunLog

    async def execute(log=None):
        runner = ToolRunner(FakeMCP())
        provider = FakeProvider([call("c4i_get_snapshot", {}), final("조회 완료")])
        return await AgentLoop(provider, runner, on_event=log.emit if log else None).run(
            "현재 상황"
        )

    expected = await execute()
    async with RunLog(
        {"runId": "run-off", "question": "현재 상황", "semanticMode": "off"}, directory=tmp_path
    ) as log:
        result = await execute(log)
        await log.finish(result)
        await log.finish(result)
    text = (tmp_path / "run-off.log").read_text(encoding="utf-8")
    assert result["status"] == expected["status"] == "completed"
    assert result["result"] == expected["result"]
    events = [
        "run_started",
        "discovery",
        "model_started",
        "model_completed",
        "tool_started",
        "tool_completed",
        "run_finished",
    ]
    assert [text.index("[" + e + "]") for e in events] == sorted(
        text.index("[" + e + "]") for e in events
    )
    assert text.count("[run_finished]") == 1
    assert "현재 상황" in text and "조회 완료" in text
    assert result["toolCalls"][0]["response"]["evidenceId"] in text
    assert "unavailable" in text  # No invented usage for the fake provider.


async def test_masking_precedes_truncation_and_runs_are_isolated(tmp_path, monkeypatch):
    from platform_api.run_log import RunLog

    monkeypatch.setenv("OPENAI_API_KEY", "secret-example-123")
    for mode in ("off", "on"):
        async with RunLog({"runId": mode, "semanticMode": mode}, directory=tmp_path) as log:
            await log.emit(
                "tool_completed",
                {
                    "nested": {"Authorization": "Bearer anything", "api_key": "another-secret"},
                    "error": "failed secret-example-123",
                    "payload": "가" * 9000,
                },
            )
            await log.finish({"status": "completed"})
    text = (tmp_path / "off.log").read_text(encoding="utf-8")
    assert (
        "secret-example-123" not in text
        and "another-secret" not in text
        and "Bearer anything" not in text
    )
    assert "[REDACTED]" in text and "생략" in text and "9000" in text
    assert 'semanticMode: "on"' not in text


async def test_existing_file_disabled_path_and_io_failure(tmp_path, monkeypatch, capsys):
    from platform_api.run_log import RunLog

    path = tmp_path / "same.log"
    path.write_text("이전 기록\n", encoding="utf-8")
    async with RunLog({"runId": "same"}, directory=tmp_path) as log:
        await log.finish({"status": "interrupted"})
    assert path.read_text(encoding="utf-8").startswith("이전 기록\n")
    assert "[run_resumed]" in path.read_text(encoding="utf-8")
    monkeypatch.setenv("AGENT_LOG_ENABLED", "false")
    async with RunLog({"runId": "disabled"}, directory=tmp_path):
        pass
    assert not (tmp_path / "disabled.log").exists()
    monkeypatch.setenv("AGENT_LOG_ENABLED", "true")
    async with RunLog({"runId": "../../escape"}, directory=tmp_path):
        pass
    assert not (tmp_path.parent / "escape.log").exists()
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")
    async with RunLog({"runId": "io-failure"}, directory=blocked) as log:
        result = await AgentLoop(
            FakeProvider([final()]), ToolRunner(FakeMCP()), on_event=log.emit
        ).run("설명")
        await log.finish(result)
    assert result["status"] == "completed"
    assert "io-failure" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["provider", "tool", "validation", "budget", "timeout", "cancel"])
async def test_abnormal_termination_is_recorded(tmp_path, kind):
    from platform_api.run_log import RunLog

    class Provider:
        async def respond(self, *args, **kwargs):
            if kind == "provider":
                raise RuntimeError("provider failed")
            if kind == "timeout":
                raise TimeoutError("deadline")
            if kind == "cancel":
                raise asyncio.CancelledError()
            if kind == "validation":
                return {"status": "completed", "output": []}
            if kind == "tool":
                return call("does_not_exist", {})
            return final()

    async with RunLog({"runId": kind}, directory=tmp_path) as log:
        try:
            result = await AgentLoop(
                Provider(),
                ToolRunner(FakeMCP()),
                max_iterations=0 if kind == "budget" else 3,
                on_event=log.emit,
            ).run("질문")
            await log.finish(result)
        except asyncio.CancelledError:
            await log.finish({"status": "interrupted", "error": "cancelled"})
    text = (tmp_path / f"{kind}.log").read_text(encoding="utf-8")
    assert text.count("[run_finished]") == 1
    assert '"status": "completed"' not in text.split("[run_finished]")[-1]
    if kind == "tool":
        assert "[tool_failed]" in text
    if kind == "cancel":
        assert "modelCalls: 1" in text


async def test_preparation_exception_is_recorded_and_propagates(tmp_path):
    from platform_api.run_log import RunLog

    with pytest.raises(ValueError, match="snapshot missing"):
        async with RunLog({"runId": "prepare-failed"}, directory=tmp_path):
            raise ValueError("snapshot missing")
    text = (tmp_path / "prepare-failed.log").read_text(encoding="utf-8")
    assert "snapshot missing" in text and "failed" in text


async def test_json_arguments_and_credential_error_strings_are_redacted(tmp_path):
    from platform_api.run_log import RunLog

    async with RunLog({"runId": "credentials"}, directory=tmp_path) as log:
        await log.emit(
            "tool_started",
            {
                "arguments": json.dumps(
                    {"password": "not-in-env", "nested": {"token": "private-token"}}
                ),
                "error": "api_key=other-private-value",
            },
        )
        await log.finish({"status": "failed"})
    text = (tmp_path / "credentials.log").read_text(encoding="utf-8")
    assert (
        "not-in-env" not in text
        and "private-token" not in text
        and "other-private-value" not in text
    )


async def test_stat_permission_failure_does_not_break_execution(tmp_path, monkeypatch):
    from pathlib import Path

    from platform_api.run_log import RunLog

    def forbidden(*args):
        raise PermissionError("private/path")

    monkeypatch.setattr(Path, "is_file", forbidden)
    async with RunLog({"runId": "stat"}, directory=tmp_path):
        pass


async def test_runtime_preparation_failure_and_restart_are_durable(tmp_path, monkeypatch):
    from platform_api.multi_repository import MultiRepository
    from platform_api.multi_runtime import MultiRuntime

    monkeypatch.setenv("AGENT_LOG_DIR", str(tmp_path / "logs"))
    repo = MultiRepository(tmp_path / "platform.db")
    await repo.open()
    try:
        run = await repo.enqueue("준비 실패 검증", "off")
        runtime = MultiRuntime(repo, None, {}, {})

        async def missing(*args, **kwargs):
            raise ValueError("snapshot missing")

        monkeypatch.setattr(runtime, "capture", missing)
        await runtime.execute_run(run)
        saved = await repo.get_run(run["runId"])
        text = (tmp_path / "logs" / (run["runId"] + ".log")).read_text(encoding="utf-8")
        assert saved["status"] == "failed" and "snapshot missing" in text
        assert "[model_started]" not in text
        await repo.update_run(run["runId"], {"status": "running"})
    finally:
        await repo.close()
    await repo.open()
    try:
        assert (await repo.get_run(run["runId"]))["status"] == "interrupted"
        text = (tmp_path / "logs" / (run["runId"] + ".log")).read_text(encoding="utf-8")
        assert "[recovery_interrupted]" in text
        assert text.count("[run_started]") == 1
    finally:
        await repo.close()


async def test_legacy_runtime_trace_matches_saved_run(tmp_path, monkeypatch):
    from platform_api.repository import Repository
    from platform_api.runtime import LazyMCP, Runtime

    monkeypatch.setenv("AGENT_LOG_DIR", str(tmp_path / "logs"))

    async def fake_request(self, method, *args):
        return await getattr(FakeMCP(), method)(*args)

    monkeypatch.setattr(LazyMCP, "_request", fake_request)
    repo = Repository(tmp_path / "legacy.db")
    await repo.open()
    try:
        run = await repo.create_run("사용법")
        await Runtime(repo, FakeProvider([final("사용법 안내")]), "", "").execute_run(run)
        saved = await repo.get_run(run["runId"])
        text = (tmp_path / "logs" / (run["runId"] + ".log")).read_text(encoding="utf-8")
        assert saved["status"] == "completed" and "사용법 안내" in text
        assert text.count("[run_finished]") == 1
    finally:
        await repo.close()


async def test_cancel_during_tool_records_interruption_and_tool_end(tmp_path):
    from platform_api.run_log import RunLog

    entered = asyncio.Event()

    class SlowMCP(FakeMCP):
        async def call(self, name, args):
            entered.set()
            await asyncio.Event().wait()

    async def execute():
        async with RunLog({"runId": "cancel-tool"}, directory=tmp_path) as log:
            await AgentLoop(
                FakeProvider([call("c4i_get_snapshot", {})]),
                ToolRunner(SlowMCP()),
                on_event=log.emit,
            ).run("취소")

    task = asyncio.create_task(execute())
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    text = (tmp_path / "cancel-tool.log").read_text(encoding="utf-8")
    assert "[tool_failed]" in text and "interrupted" in text
    assert "modelCalls: 1" in text and "toolCalls: 1" in text
    assert "modelResponses: 1" in text
    assert text.count("[run_finished]") == 1


def test_usage_partial_is_not_reported_as_complete():
    from platform_api.run_log import usage_summary

    result = usage_summary([{"usage": {"input_tokens": 10, "output_tokens": 3}}, {"usage": None}])
    assert result == {"coverage": "partial", "input_tokens": 10, "output_tokens": 3}
