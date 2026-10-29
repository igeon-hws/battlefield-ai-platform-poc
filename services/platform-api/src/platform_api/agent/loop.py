import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

from platform_api.agent.agent import INSTRUCTIONS, RESULT_FORMAT
from platform_contracts.models import AnalysisResult


class AgentLoop:
    def __init__(
        self,
        provider,
        runner,
        *,
        max_iterations=12,
        max_tools=20,
        deadline=120,
        on_progress=None,
        on_event=None,
    ):
        self.provider, self.runner = provider, runner
        self.max_iterations, self.max_tools, self.deadline = max_iterations, max_tools, deadline
        self.on_progress = on_progress
        self.on_event = on_event

    async def event(self, name, data):
        if self.on_event:
            await self.on_event(name, data)

    async def run(self, question: str, history=None):
        """Keep assistant calls and their outputs in one context; evidence is run-local."""
        state: dict[str, Any] = {
            "status": "running",
            "result": None,
            "toolCalls": [],
            "evidence": [],
            "iterations": [],
            "validationFailures": 0,
            "correctionAttempts": 0,
        }
        first_model_started = None

        async def publish():
            state["toolCalls"] = self.runner.calls
            state["evidence"] = list(self.runner.evidence.values())
            state["sourceContext"] = self.runner.snapshot
            if self.on_progress:
                await self.on_progress(state)

        result_format: dict[str, Any] = RESULT_FORMAT
        if getattr(self.runner, "knowledge_mode", None):
            from copy import deepcopy

            result_format = deepcopy(RESULT_FORMAT)
            result_format["schema"]["$defs"]["Claim"]["properties"]["kind"]["enum"] = [
                "observation",
                "inference",
                "calculation",
            ]
        inputs = list(history or []) + [{"role": "user", "content": question}]
        if getattr(self.runner, "knowledge_mode", None):
            inputs.append(
                {
                    "role": "developer",
                    "content": "이번 A/B/C 실행의 claim.kind는 observation/inference/calculation만 사용한다. 의미를 해석했더라도 semantic으로 분류하지 않는다. 실제 원천/문서/Semantic/계산 출처는 서버가 인용 근거에서 산출한다. 문서 해석은 inference로 쓰고 문서 evidenceId를 인용한다. 문서 본문의 규칙 이름은 주장 본문에 언급할 수 있지만 ruleRefs에는 구조화된 도구 결과의 실제 ruleId만 넣는다. 답변 타당성과 가정은 별도로 설명한다.",
                }
            )
        if self.runner.snapshot:
            inputs.append(
                {
                    "role": "developer",
                    "content": "이 실행의 고정 기준 컨텍스트: " + json.dumps(self.runner.snapshot),
                }
            )
        corrected = False
        repeats = 0
        last_signature = None
        final_only = False
        final_notice_added = False
        try:
            async with asyncio.timeout(self.deadline):
                await self.runner.prepare()
                state["toolDiscovery"] = {
                    "tools": [t["name"] for t in self.runner.definitions],
                    "error": self.runner.discovery_error,
                }
                servers: dict[str, int] = {}
                for name in state["toolDiscovery"]["tools"]:
                    server = (
                        name.split("__", 1)[0]
                        if "__" in name
                        else "c4i"
                        if name.startswith("c4i_")
                        else "local"
                    )
                    servers[server] = servers.get(server, 0) + 1
                await self.event(
                    "discovery",
                    {
                        **state["toolDiscovery"],
                        "registryHash": getattr(self.runner, "registry_hash", None),
                        "serverToolCounts": servers,
                    },
                )
                if self.runner.discovery_error:
                    inputs.append(
                        {
                            "role": "developer",
                            "content": self.runner.discovery_error
                            + ". MCP 조회가 필요한 질문은 조회 불가와 한계를 명시하고 근거 없이 사실을 만들지 마세요.",
                        }
                    )
                for iteration in range(self.max_iterations):
                    final_only = (
                        final_only
                        or len(self.runner.calls) >= self.max_tools
                        or iteration == self.max_iterations - 1
                    )
                    if final_only and not final_notice_added:
                        final_notice_added = True
                        inputs.append(
                            {
                                "role": "developer",
                                "content": "도구 조회 예산이 끝났습니다. 지금까지 확보한 근거로 답변하세요. 확인하지 못한 항목은 한계로 명시하고 필요한 경우 partial로 표시하세요. 추가 도구를 호출하지 마세요.",
                            }
                        )
                    requested = time.monotonic()
                    if first_model_started is None:
                        first_model_started = requested
                        state["modelLoopStartedAt"] = datetime.now(UTC).isoformat()
                    await self.event(
                        "model_started", {"iteration": iteration + 1, "historyItems": len(inputs)}
                    )
                    response = await self.provider.respond(
                        inputs,
                        instructions=INSTRUCTIONS,
                        tools=[] if final_only else self.runner.definitions,
                        result_format=result_format,
                    )
                    await self.event(
                        "model_completed",
                        {
                            "iteration": iteration + 1,
                            "responseId": response.get("id"),
                            "model": response.get("model"),
                            "status": response.get("status"),
                            "usage": response.get("usage"),
                            "durationSeconds": round(time.monotonic() - requested, 4),
                            "outputKinds": [i.get("type") for i in response.get("output", [])],
                            "selectedTools": [
                                i.get("name")
                                for i in response.get("output", [])
                                if i.get("type") == "function_call"
                            ],
                        },
                    )
                    state["iterations"].append(
                        {
                            "iteration": iteration + 1,
                            "responseId": response.get("id"),
                            "model": response.get("model"),
                            "durationSeconds": round(time.monotonic() - requested, 4),
                            "usage": response.get("usage"),
                            "time": datetime.now(UTC).isoformat(),
                        }
                    )
                    if response.get("status") != "completed":
                        state["status"] = response.get("status", "failed")
                        break
                    output = response.get("output", [])
                    # Preserve call IDs/order so the next turn consumes exact tool outputs.
                    inputs.extend(output)
                    calls = [item for item in output if item.get("type") == "function_call"]
                    if calls:
                        for item in calls:
                            if len(self.runner.calls) >= self.max_tools:
                                inputs.append(
                                    {
                                        "type": "function_call_output",
                                        "call_id": item["call_id"],
                                        "output": json.dumps({"error": "tool_budget_exceeded"}),
                                    }
                                )
                                final_only = True
                                continue
                            started = datetime.now(UTC).isoformat()
                            record = {
                                "name": item["name"],
                                "callId": item["call_id"],
                                "startedAt": started,
                                "iteration": iteration + 1,
                                "status": "running",
                            }
                            self.runner.calls.append(record)
                            tool_started = time.monotonic()
                            await self.event(
                                "tool_started", {**record, "arguments": item["arguments"]}
                            )
                            await publish()
                            try:
                                args = json.loads(item["arguments"])
                                record["arguments"] = args
                                result = await self.runner.execute(item["name"], args)
                                record["status"] = "completed"
                                record["cacheHit"] = bool(
                                    getattr(self.runner, "last_cache_hit", False)
                                )
                            except Exception as exc:  # noqa: BLE001 - tool boundary records any adapter error
                                result = {"error": type(exc).__name__, "detail": str(exc)[:1500]}
                                record["status"] = "failed"
                            record["response"] = result
                            record["endedAt"] = datetime.now(UTC).isoformat()
                            await self.event(
                                "tool_completed"
                                if record["status"] == "completed"
                                else "tool_failed",
                                {
                                    **record,
                                    "durationSeconds": round(time.monotonic() - tool_started, 4),
                                },
                            )
                            signature = json.dumps(
                                [
                                    item["name"],
                                    item["arguments"],
                                    {k: v for k, v in result.items() if k != "evidenceId"},
                                ],
                                sort_keys=True,
                            )
                            repeats = repeats + 1 if signature == last_signature else 0
                            last_signature = signature
                            inputs.append(
                                {
                                    "type": "function_call_output",
                                    "call_id": item["call_id"],
                                    "output": json.dumps(result, ensure_ascii=False),
                                }
                            )
                            await publish()
                            if repeats >= 2:
                                final_only = True
                        continue
                    refusal = any(
                        c.get("type") == "refusal"
                        for item in output
                        for c in item.get("content", [])
                    )
                    if refusal:
                        state["status"] = "refused"
                        break
                    text = "".join(
                        c.get("text", "")
                        for item in output
                        for c in item.get("content", [])
                        if c.get("type") == "output_text"
                    )
                    try:
                        result_model = AnalysisResult.model_validate_json(text)
                        result = result_model.public()
                        ids = set(result["evidenceIds"])
                        for finding in result["findings"] + (result["courses"] or []):
                            ids.update(finding["evidenceIds"])
                        for claim in result["claims"]:
                            ids.update(claim["evidenceRefs"])
                            if getattr(self.runner, "knowledge_mode", None):
                                continue
                            if (
                                claim["kind"] == "semantic"
                                and getattr(self.runner, "mode", None) == "off"
                            ):
                                raise ValueError(
                                    "OFF claim must identify interpretation as model inference"
                                )
                            if claim["kind"] != "inference" and not claim["evidenceRefs"]:
                                raise ValueError("grounded claim requires evidence")
                            allowed_rules: set[str] = set()

                            def collect_rules(value, allowed_rules=allowed_rules):
                                if isinstance(value, dict):
                                    if isinstance(value.get("ruleId"), str):
                                        allowed_rules.add(value["ruleId"])
                                    for nested in value.values():
                                        collect_rules(nested)
                                elif isinstance(value, list):
                                    for nested in value:
                                        collect_rules(nested)

                            for ref in claim["evidenceRefs"]:
                                if ref in self.runner.evidence:
                                    collect_rules(self.runner.evidence[ref]["data"])
                            if set(claim["ruleRefs"]) - allowed_rules:
                                raise ValueError(
                                    "claim rule reference not present in cited evidence"
                                )
                        if ids - self.runner.evidence.keys():
                            raise ValueError("invalid evidence reference")
                        if getattr(self.runner, "knowledge_mode", None):
                            from platform_api.agent.provenance import annotate_result

                            annotate_result(
                                result, self.runner.evidence, self.runner.knowledge_mode
                            )
                            await self.event(
                                "claim_provenance",
                                {
                                    "version": "1",
                                    "claims": [
                                        {
                                            "kind": c["kind"],
                                            "evidenceRefs": c["evidenceRefs"],
                                            "ruleRefs": c["ruleRefs"],
                                            **c["provenance"],
                                        }
                                        for c in result["claims"]
                                    ],
                                },
                            )
                        if result["courses"] and len({c["id"] for c in result["courses"]}) != 3:
                            raise ValueError("course IDs must be unique")
                        state["result"] = result
                        state["status"] = (
                            "completed" if result["outcome"] == "answer" else result["outcome"]
                        )
                        break
                    except (ValueError, TypeError) as exc:
                        state["validationFailures"] += 1
                        await self.event(
                            "validation_failed",
                            {
                                "iteration": iteration + 1,
                                "error": str(exc),
                                "correctionAttempted": corrected,
                            },
                        )
                        if corrected:
                            state["status"] = "validation_failed"
                            state["error"] = str(exc)[:500]
                            break
                        # One repair is allowed; repeated invalid output stops the loop.
                        corrected = True
                        state["correctionAttempts"] += 1
                        inputs.append(
                            {
                                "role": "developer",
                                "content": f"결과 검증 실패: {exc}. 실제 확보한 근거 ID와 결과 스키마를 사용해 교정하세요.",
                            }
                        )
                else:
                    state["status"] = "budget_exceeded"
        except asyncio.CancelledError:
            state["status"] = "interrupted"
            raise
        except TimeoutError:
            state["status"] = "timeout"
        except Exception as exc:  # noqa: BLE001 - persist provider/runtime failure, never fabricate success
            state["status"] = "failed"
            state["error"] = str(exc)[:1000]
            await self.event(
                "loop_failed", {"error": state["error"], "errorType": type(exc).__name__}
            )
        finally:
            state["loopDurationSeconds"] = (
                round(time.monotonic() - first_model_started, 4)
                if first_model_started is not None
                else None
            )
            state["loopFinishedAt"] = datetime.now(UTC).isoformat()
            for record in self.runner.calls:
                if record["status"] == "running":
                    record["status"] = state["status"]
                    record["endedAt"] = datetime.now(UTC).isoformat()
                    await self.event("tool_failed", record)
            await publish()
            await self.event(
                "loop_stopped", {"status": state["status"], "error": state.get("error")}
            )
        return state
