import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from platform_api.agent.agent import INSTRUCTIONS, RESULT_FORMAT
from platform_contracts.models import AnalysisResult


class AgentLoop:
    def __init__(
        self, provider, runner, *, max_iterations=12, max_tools=20, deadline=120, on_progress=None
    ):
        self.provider, self.runner = provider, runner
        self.max_iterations, self.max_tools, self.deadline = max_iterations, max_tools, deadline
        self.on_progress = on_progress

    async def run(self, question: str, history=None):
        state: dict[str, Any] = {
            "status": "running",
            "result": None,
            "toolCalls": [],
            "evidence": [],
            "iterations": [],
        }

        async def publish():
            state["toolCalls"] = self.runner.calls
            state["evidence"] = list(self.runner.evidence.values())
            state["sourceContext"] = self.runner.snapshot
            if self.on_progress:
                await self.on_progress(state)

        inputs = list(history or []) + [{"role": "user", "content": question}]
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
        try:
            async with asyncio.timeout(self.deadline):
                await self.runner.prepare()
                state["toolDiscovery"] = {
                    "tools": [t["name"] for t in self.runner.definitions],
                    "error": self.runner.discovery_error,
                }
                if self.runner.discovery_error:
                    inputs.append(
                        {
                            "role": "developer",
                            "content": self.runner.discovery_error
                            + ". MCP 조회가 필요한 질문은 조회 불가와 한계를 명시하고 근거 없이 사실을 만들지 마세요.",
                        }
                    )
                for iteration in range(self.max_iterations):
                    response = await self.provider.respond(
                        inputs,
                        instructions=INSTRUCTIONS,
                        tools=self.runner.definitions,
                        result_format=RESULT_FORMAT,
                    )
                    state["iterations"].append(
                        {
                            "iteration": iteration + 1,
                            "responseId": response.get("id"),
                            "model": response.get("model"),
                            "usage": response.get("usage"),
                            "time": datetime.now(UTC).isoformat(),
                        }
                    )
                    if response.get("status") != "completed":
                        state["status"] = response.get("status", "failed")
                        break
                    output = response.get("output", [])
                    inputs.extend(output)
                    calls = [item for item in output if item.get("type") == "function_call"]
                    if calls:
                        for item in calls:
                            if len(self.runner.calls) >= self.max_tools:
                                state["status"] = "budget_exceeded"
                                return state
                            started = datetime.now(UTC).isoformat()
                            record = {
                                "name": item["name"],
                                "callId": item["call_id"],
                                "startedAt": started,
                                "iteration": iteration + 1,
                                "status": "running",
                            }
                            self.runner.calls.append(record)
                            await publish()
                            try:
                                args = json.loads(item["arguments"])
                                record["arguments"] = args
                                result = await self.runner.execute(item["name"], args)
                                record["status"] = "completed"
                            except Exception as exc:  # noqa: BLE001 - tool boundary records any adapter error
                                result = {"error": type(exc).__name__, "detail": str(exc)[:1500]}
                                record["status"] = "failed"
                            record["response"] = result
                            record["endedAt"] = datetime.now(UTC).isoformat()
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
                                state["status"] = "budget_exceeded"
                                return state
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
                        if result["courses"] and len({c["id"] for c in result["courses"]}) != 3:
                            raise ValueError("course IDs must be unique")
                        state["result"] = result
                        state["status"] = (
                            "completed" if result["outcome"] == "answer" else result["outcome"]
                        )
                        break
                    except (ValueError, TypeError) as exc:
                        if corrected:
                            state["status"] = "validation_failed"
                            state["error"] = str(exc)[:500]
                            break
                        corrected = True
                        inputs.append(
                            {
                                "role": "developer",
                                "content": f"결과 검증 실패: {exc}. 실제 확보한 근거 ID와 결과 스키마를 사용해 교정하세요.",
                            }
                        )
                else:
                    state["status"] = "budget_exceeded"
        except TimeoutError:
            state["status"] = "timeout"
            for record in self.runner.calls:
                if record["status"] == "running":
                    record["status"] = "timeout"
                    record["endedAt"] = datetime.now(UTC).isoformat()
        except Exception as exc:  # noqa: BLE001 - persist provider/runtime failure, never fabricate success
            state["status"] = "failed"
            state["error"] = str(exc)[:1000]
        finally:
            await publish()
        return state
