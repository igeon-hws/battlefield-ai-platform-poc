"""Human-readable execution events. DB evidence remains the full audit record."""

import asyncio
import contextlib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

LABELS = {
    "run_started": "실행 시작",
    "run_resumed": "기존 기록에 실행 구간 추가",
    "preparation": "분석 기준 준비",
    "discovery": "MCP 도구 발견",
    "model_started": "모델 요청",
    "model_completed": "모델 응답",
    "tool_started": "도구 호출",
    "tool_completed": "도구 결과",
    "tool_failed": "도구 실패",
    "validation_failed": "출력 검증 실패",
    "claim_provenance": "주장 출처 확인",
    "loop_failed": "모델/루프 실패",
    "loop_stopped": "루프 종료",
    "recovery_interrupted": "서버 재시작으로 중단 확인",
    "run_finished": "최종 실행 결과",
}


def usage_summary(iterations):
    """Missing usage is not zero usage; cached tokens stay in reported totals."""
    usages = [i.get("usage") for i in iterations]
    totals = {}
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        values = [u[field] for u in usages if isinstance(u, dict) and isinstance(u.get(field), int)]
        if values:
            totals[field] = sum(values)
    return {
        "coverage": "complete"
        if usages
        and all(
            isinstance(u, dict) and "input_tokens" in u and "output_tokens" in u for u in usages
        )
        else "partial"
        if totals
        else "unavailable",
        **totals,
    }


class RunLog:
    """One writer per run; append-only, serialized, no persistent file handle."""

    def __init__(self, run, *, directory=None, model=None, budget=None, secrets=()):
        self.run = run
        self.run_id = str(run["runId"])
        self.valid_id = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,160}", self.run_id))
        self.path = (
            Path(directory or os.getenv("AGENT_LOG_DIR", "var/logs/agent")) / (self.run_id + ".log")
            if self.valid_id
            else None
        )
        self.enabled = os.getenv("AGENT_LOG_ENABLED", "true").lower() not in ("false", "0", "no")
        self.model, self.budget = model, budget
        self.secrets = sorted(
            {
                v
                for k, v in os.environ.items()
                if v and any(s in k.upper() for s in ("TOKEN", "PASSWORD", "SECRET", "API_KEY"))
            }
            | {v for v in secrets if isinstance(v, str) and v},
            key=len,
            reverse=True,
        )
        self.lock = asyncio.Lock()
        self.started = time.monotonic()
        self.finished = False
        self.failed = False
        self.model_requests = []
        self.tool_requests = 0

    def clean(self, value):
        if isinstance(value, dict):
            return {
                str(k): "[REDACTED]"
                if any(
                    s in re.sub(r"[^a-z]", "", str(k).lower())
                    for s in (
                        "authorization",
                        "password",
                        "apikey",
                        "secret",
                        "accesstoken",
                        "refreshtoken",
                        "readtoken",
                        "controltoken",
                        "mcptoken",
                        "admintoken",
                    )
                )
                or str(k).lower() in ("token", "api_key")
                else self.clean(v)
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            if value.lstrip().startswith(("{", "[")):
                try:
                    parsed = json.loads(value)
                except ValueError:
                    pass
                else:
                    return self.clean(parsed)
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r'(?i)Bearer\s+[^\s,;"\'}]+', "Bearer [REDACTED]", value)
            return re.sub(
                r'(?i)((?:api[_-]?key|password|authorization|(?:access[_-]?|refresh[_-]?)?token)\s*[=:]\s*)(?:"[^"]*"|\x27[^\x27]*\x27|[^\s,;]+)',
                r"\1[REDACTED]",
                value,
            )
        return value

    def append(self, event, data):
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Mask before bounding output: truncation must not expose a key prefix.
        blocks = []
        for key, value in self.clean(data).items():
            rendered = json.dumps(value, ensure_ascii=False, indent=2, default=str)
            if len(rendered) > 8000:
                original = len(value) if isinstance(value, str) else len(rendered)
                rendered = (
                    rendered[:8000] + f"\n… [생략: 원래 길이 {original}자; 상세는 DB/UI trace]"
                )
            blocks.append(f"{key}: {rendered}")
        resumed = event == "run_started" and self.path.is_file()
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            if resumed:
                stream.write(
                    f"\n{datetime.now(UTC).isoformat()} [run_resumed] {LABELS['run_resumed']}\n"
                )
            stream.write(
                f"\n{datetime.now(UTC).isoformat()} [{event}] {LABELS.get(event, event)}\n"
                + "\n".join(blocks)
                + "\n"
            )
            stream.flush()

    async def emit(self, event, data=None):
        if not self.enabled or self.failed:
            return
        if event == "model_started":
            self.model_requests.append({"usage": None, "responded": False})
        elif event == "model_completed" and self.model_requests:
            self.model_requests[-1]["usage"] = (data or {}).get("usage")
            self.model_requests[-1]["responded"] = True
        elif event == "tool_started":
            self.tool_requests += 1
        if event in ("tool_completed", "tool_failed") and data:
            response = data.get("response") or {}
            response = response if isinstance(response, dict) else {}
            result = response.get("data", response)
            result = result if isinstance(result, dict) else {}
            summary = {
                k: result[k]
                for k in (
                    "matchedCount",
                    "total",
                    "complete",
                    "completeness",
                    "coverage",
                    "counts",
                    "rawRecordCount",
                    "resolvedUniqueCount",
                    "error",
                )
                if k in result
            }
            summary["evidenceId"] = response.get("evidenceId")
            data = {**data, "summary": summary}
        async with self.lock:
            try:
                if not self.valid_id:
                    raise ValueError("invalid server run ID")
                # Finish an in-flight append before releasing the per-run lock on cancellation.
                write = asyncio.create_task(asyncio.to_thread(self.append, event, data or {}))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    with contextlib.suppress(Exception):
                        await write
                    raise
            except Exception as exc:  # noqa: BLE001 - optional logging cannot break analysis
                self.failed = True
                # Never print an exception message/path/payload containing credentials.
                print(
                    f"Agent log failure runId={self.run_id if self.valid_id else 'invalid'} type={type(exc).__name__}",
                    file=sys.stderr,
                )

    async def __aenter__(self):
        await self.emit(
            "run_started",
            {
                k: self.run.get(k)
                for k in (
                    "runId",
                    "conversationId",
                    "comparisonId",
                    "question",
                    "trigger",
                    "semanticMode",
                )
            }
            | {"model": self.model, "budget": self.budget},
        )
        return self

    async def finish(self, state):
        if self.finished:
            return
        self.finished = True
        await self.emit(
            "run_finished",
            {
                "runId": self.run_id,
                "status": state.get("status"),
                "error": state.get("error"),
                "result": state.get("result"),
                "modelCalls": max(len(state.get("iterations", [])), len(self.model_requests)),
                "modelResponses": max(
                    len(state.get("iterations", [])),
                    sum(bool(r["responded"]) for r in self.model_requests),
                ),
                "toolCalls": max(len(state.get("toolCalls", [])), self.tool_requests),
                "usage": usage_summary(self.model_requests or state.get("iterations", [])),
                "sourceContext": state.get("sourceContext"),
                "durationSeconds": round(time.monotonic() - self.started, 4),
            },
        )

    async def __aexit__(self, exc_type, exc, tb):
        if not self.finished:
            await self.finish(
                {
                    "status": "interrupted"
                    if isinstance(exc, asyncio.CancelledError)
                    else "failed",
                    "error": type(exc).__name__ + ": " + str(exc)
                    if exc
                    else "execution ended without terminal state",
                }
            )
