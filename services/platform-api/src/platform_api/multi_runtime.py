import asyncio
import json
import os
import time
from contextlib import AsyncExitStack
from datetime import UTC, datetime

import httpx
from battlefield_geo import decorate
from battlefield_ontology import (
    MAPPING_VERSION,
    ONTOLOGY_VERSION,
    RESOLUTION_VERSION,
    digest,
    normalize_equipment,
)
from c4i_contracts import Entity
from httpx_sse import aconnect_sse

from platform_api.agent.agent import INSTRUCTIONS
from platform_api.agent.loop import AgentLoop
from platform_api.agent.multi_tools import MultiToolRunner
from platform_api.mcp.client import MCPClient
from platform_api.run_log import RunLog


def snapshot_ref(snapshot):
    return {
        k: snapshot[k]
        for k in ("datasetId", "epochId", "snapshotId", "sequence", "sourceTime", "stableDataHash")
    }


def projection(system, snapshot):
    key = "tracks" if system == "atcis" else "contacts"
    entities = []
    for raw in snapshot[key]:
        item = normalize_equipment(system, raw)
        if item.position:
            entity = Entity.model_validate(
                {
                    "entityId": item.native_id,
                    "label": item.native_id,
                    "kind": item.kind,
                    "availability": item.availability,
                    "affiliation": item.affiliation,
                    "unitId": item.unit_id,
                    "position": item.position,
                    "velocity": item.velocity,
                    "source": system,
                    "revision": snapshot["sequence"],
                    "updatedAt": snapshot["sourceTime"],
                    "observedAt": item.observed_at,
                }
            )
            entities.append(decorate(entity))
    return {
        **snapshot_ref(snapshot),
        "systemId": system,
        "running": snapshot["running"],
        "entities": entities,
    }


class BoundMCP:
    def __init__(self, stack, config, status):
        self.stack, self.config, self.status = stack, config, status
        self.session = None

    async def request(self, method, *args):
        try:
            if self.session is None:
                self.session = await self.stack.enter_async_context(
                    MCPClient(self.config["mcpUrl"], self.config.get("mcpToken", ""))
                )
            result = await getattr(self.session, method)(*args)
            self.status.update(connected=True, error=None)
            return result
        except BaseException:
            self.status.update(connected=False, error="MCP connection or call failed")
            raise

    async def list_tools(self):
        return await self.request("list_tools")

    async def call(self, name, arguments):
        return await self.request("call", name, arguments)


class MultiRuntime:
    def __init__(self, repo, provider, sources, semantic):
        self.policy_version = getattr(repo, "policy_version", "2-native-off")
        self.source_contract = getattr(repo, "source_contract", "2")
        self.runner_class = MultiToolRunner
        self.repo, self.provider, self.sources, self.semantic = repo, provider, sources, semantic
        self.agent_limits = {
            "max_iterations": int(os.getenv("AGENT_MAX_ITERATIONS", "24")),
            "max_tools": int(os.getenv("AGENT_MAX_TOOLS", "20")),
            "deadline": int(os.getenv("AGENT_DEADLINE_SECONDS", "120")),
        }
        if any(value < 1 for value in self.agent_limits.values()):
            raise ValueError("agent budgets must be positive")
        self.source_status: dict[str, dict] = {
            s: {"connected": False, "error": None} for s in sources
        }
        self.mcp_status = {s: {"connected": False, "error": None} for s in (*sources, "semantic")}

    async def source_get(self, system, path):
        config = self.sources[system]
        headers = {"Authorization": f"Bearer {config['token']}"} if config.get("token") else {}
        async with httpx.AsyncClient(base_url=config["url"], headers=headers, timeout=10) as client:
            response = await client.get("/api/v1" + path)
            response.raise_for_status()
            return response.json()

    async def capture(self, *, strict=False, overrides=None):
        started = time.monotonic()
        overrides = overrides or {}

        async def one(system):
            if system in overrides:
                return overrides[system]
            return snapshot_ref(await self.source_get(system, "/snapshot"))

        results = await asyncio.gather(*(one(s) for s in self.sources), return_exceptions=True)
        snapshots = {
            system: value
            for system, value in zip(self.sources, results, strict=True)
            if not isinstance(value, BaseException)
        }
        duration = time.monotonic() - started
        self.last_capture = {
            "capturedAt": datetime.now(UTC).isoformat(),
            "captureSpanSeconds": duration,
        }
        if not snapshots or strict and (set(snapshots) != {"atcis", "knccs"} or duration > 2):
            raise ValueError("incomplete or inconsistent source snapshot capture")
        return snapshots

    async def ensure_graph(self, snapshots):
        if not self.semantic.get("adminToken"):
            raise ValueError("BUILDER_ADMIN_TOKEN is required for graph preparation")
        headers = {"Authorization": f"Bearer {self.semantic.get('adminToken', '')}"}
        body = {
            "snapshots": snapshots,
            "ontologyVersion": ONTOLOGY_VERSION,
            "mappingVersion": MAPPING_VERSION,
            "resolutionRuleVersion": RESOLUTION_VERSION,
        }
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self.semantic["builderUrl"] + "/internal/build-requests", json=body, headers=headers
            )
            response.raise_for_status()
            request_id = response.json()["requestId"]
            while time.monotonic() - started < 30:
                status_response = await client.get(
                    self.semantic["builderUrl"] + "/internal/build-requests/" + request_id,
                    headers=headers,
                )
                status_response.raise_for_status()
                status = status_response.json()
                if status["status"] == "FAILED":
                    raise ValueError("graph preparation failed: " + status.get("error", "unknown"))
                if status["status"] == "READY":
                    response = await client.get(
                        self.semantic["url"] + "/v1/builds/" + status["graphVersion"],
                        headers={"Authorization": f"Bearer {self.semantic['token']}"}
                        if self.semantic.get("token")
                        else {},
                    )
                    response.raise_for_status()
                    info = response.json()
                    if info["inputStableHashes"] != {
                        s: r["stableDataHash"] for s, r in snapshots.items()
                    }:
                        raise ValueError("graph snapshot hashes do not match")
                    return info
                await asyncio.sleep(0.2)
        raise TimeoutError("graph preparation deadline exceeded")

    async def ingest(self, system):
        config = self.sources[system]
        headers = {"Authorization": f"Bearer {config['token']}"} if config.get("token") else {}
        while True:
            try:
                current = (await self.repo.situation()).get("sources", {}).get(system)
                if not current:
                    current = projection(system, await self.source_get(system, "/snapshot"))
                    await self.repo.save_source(system, current)
                async with (
                    httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(10, read=30)) as http,
                    aconnect_sse(
                        http,
                        "GET",
                        config["url"] + "/api/v1/stream",
                        params={"epochId": current["epochId"], "after": current["sequence"]},
                    ) as stream,
                ):
                    if stream.response.status_code == 409:
                        fresh = projection(system, await self.source_get(system, "/snapshot"))
                        fresh["historyGap"] = True
                        await self.repo.save_source(system, fresh)
                        continue
                    stream.response.raise_for_status()
                    self.source_status[system].update(connected=True, error=None)
                    async for message in stream.aiter_sse():
                        if not message.data:
                            continue
                        event = json.loads(message.data)
                        if event["systemId"] != system:
                            raise ValueError("source system mismatch")
                        raw = await self.source_get(system, "/snapshots/" + event["snapshotId"])
                        pins = (
                            await self.capture(overrides={system: snapshot_ref(raw)})
                            if event["type"] in ("equipment.changed", "structure.changed")
                            else None
                        )
                        await self.repo.save_source(system, projection(system, raw), event, pins)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - per-source reconnect isolation
                self.source_status[system].update(
                    connected=False, error=f"{type(exc).__name__}: {exc}"
                )
                await asyncio.sleep(1)

    async def execute_run(self, run):
        """Own file tracing outside preparation; the database remains authoritative."""
        secrets = [getattr(self.provider, "api_key", "")]
        for config in [*self.sources.values(), self.semantic]:
            secrets.extend(config.get(k, "") for k in ("token", "mcpToken", "adminToken"))
        async with RunLog(
            run,
            model=getattr(self.provider, "model", None),
            budget=self.agent_limits,
            secrets=secrets,
        ) as log:
            await self._execute_run(run, log)
            await log.finish(await self.repo.get_run(run["runId"]))

    async def _execute_run(self, run, log):
        preparation_started = time.monotonic()
        rid = run["runId"]
        if run.get("semanticPolicyVersion") != self.policy_version:
            await self.repo.update_run(
                rid,
                {
                    "status": "interrupted",
                    "error": "policy changed; create a new analysis",
                    "finishedAt": datetime.now(UTC).isoformat(),
                },
            )
            return
        await self.repo.update_run(
            rid, {"status": "running", "startedAt": datetime.now(UTC).isoformat()}
        )

        async def publish_progress(state):
            # Terminal status is committed below with registry and timing metadata.
            await self.repo.update_run(rid, {**state, "status": "running"})

        try:
            pins = run.get("sourceSnapshotSet") or await self.capture()
            info = run.get("graphInfo")
            if run["semanticMode"] == "on" and not info:
                info = await self.ensure_graph(pins)
            await self.repo.update_run(
                rid,
                {
                    "sourceSnapshotSet": pins,
                    "graphInfo": info,
                    "agentBudget": self.agent_limits,
                    "semanticPolicyVersion": self.policy_version,
                    "sourceToolContractVersion": self.source_contract,
                },
            )
            async with AsyncExitStack() as stack:
                configs = {
                    **self.sources,
                    **({"semantic": self.semantic} if run["semanticMode"] == "on" else {}),
                }
                if hasattr(self, "run_configs"):
                    configs = self.run_configs(run)
                clients = {s: BoundMCP(stack, c, self.mcp_status[s]) for s, c in configs.items()}
                runner = (
                    self.make_runner(run, clients, pins, info)
                    if hasattr(self, "make_runner")
                    else self.runner_class(clients, pins, run["semanticMode"], info)
                )
                if run.get("baselineReportRef"):
                    runner.snapshot["baselineReportRef"] = run["baselineReportRef"]
                historical = run.get("baselineSourceSnapshotSet") or getattr(
                    self, "baseline_snapshots", {}
                )
                if hasattr(self, "prepare_run_context"):
                    historical = await self.prepare_run_context(pins)
                if historical:
                    runner.historical_snapshots = historical
                    runner.snapshot["baselineSourceSnapshotSet"] = historical
                    await self.repo.update_run(rid, {"baselineSourceSnapshotSet": historical})
                await log.emit(
                    "preparation",
                    {
                        "sourceSnapshotSet": pins,
                        "graphVersion": (info or {}).get("graphVersion"),
                        "baselineReportRef": run.get("baselineReportRef"),
                        "baselineSourceSnapshotSet": historical,
                        "preparationSeconds": round(time.monotonic() - preparation_started, 4),
                    },
                )
                history = (
                    []
                    if run.get("comparisonId")
                    else await self.repo.history(run["conversationId"], rid)
                )
                result = await AgentLoop(
                    self.provider,
                    runner,
                    on_progress=publish_progress,
                    on_event=log.emit,
                    **self.agent_limits,
                ).run(run["question"], history)
                if runner.discovery_error and result["status"] == "completed":
                    result["status"] = "partial"
                    result["result"]["outcome"] = "partial"
                    result["result"]["limitations"].append(
                        "일부 원천/도구 조회 불가: " + runner.discovery_error
                    )
                result["registryHash"] = getattr(runner, "registry_hash", None)
                result["registryBindings"] = {
                    name: {k: b[k] for k in ("serverId", "originalName")}
                    for name, b in runner.registry.items()
                }
                result["finishedAt"] = datetime.now(UTC).isoformat()
                await self.repo.update_run(rid, result)
        except asyncio.CancelledError:
            await self.repo.update_run(
                rid,
                {
                    "status": "interrupted",
                    "error": "execution cancelled",
                    "finishedAt": datetime.now(UTC).isoformat(),
                },
            )
            raise
        except Exception as exc:  # noqa: BLE001 - durable run boundary records real failures
            await self.repo.update_run(
                rid,
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}"[:1200],
                    "finishedAt": datetime.now(UTC).isoformat(),
                },
            )

    async def worker(self):
        await self.reconcile_comparisons()
        while True:
            pending = await self.repo.next_comparison()
            if pending:
                await self.prepare_comparison(pending)
            run = await self.repo.next_run()
            if run:
                await self.execute_run(run)
                if run.get("comparisonId"):
                    await self.finish_comparison(run["comparisonId"])
            else:
                await asyncio.sleep(0.1)

    async def reconcile_comparisons(self):
        for comparison in await self.repo.active_comparisons():
            await self.finish_comparison(comparison["comparisonId"])

    async def prepare_comparison(self, comparison):
        """Persist one shared manifest, then run OFF/ON in separate conversations."""
        cid = comparison["comparisonId"]
        started = time.monotonic()
        preparation_started_at = datetime.now(UTC).isoformat()
        try:
            manifest = comparison.get("manifest")
            if manifest and manifest.get("semanticPolicyVersion") != self.policy_version:
                raise ValueError("comparison policy changed; create a new comparison")
            if not manifest:
                pins = await self.capture(strict=True)
                manifest = {
                    "question": comparison["question"],
                    "baselineReportRef": comparison.get("baselineReportRef"),
                    "semanticPolicyVersion": self.policy_version,
                    "sourceToolContractVersion": self.source_contract,
                    "agentBudget": self.agent_limits,
                    "questionHash": digest(comparison["question"]),
                    "sourceSnapshotSet": pins,
                    **self.last_capture,
                    "modelId": getattr(
                        self.provider, "model", "test:" + type(self.provider).__name__
                    ),
                    "systemPromptVersion": digest(INSTRUCTIONS),
                    "schemaAdapterVersion": "1",
                    "conversationPolicy": "two-empty-isolated-conversations",
                    "executionOrder": comparison["executionOrder"],
                    "modelConfig": {
                        "toolChoice": "auto",
                        "parallelToolCalls": False,
                        "maxOutputTokens": 4000,
                        "store": False,
                    },
                }
                await self.repo.update_comparison(cid, {"manifest": manifest})
            info = await self.ensure_graph(manifest["sourceSnapshotSet"])
            manifest.update(
                {
                    k: info[k]
                    for k in (
                        "graphVersion",
                        "ontologyVersion",
                        "mappingVersion",
                        "resolutionRuleVersion",
                        "inputStableHashes",
                        "inputSnapshotSet",
                    )
                }
            )
            manifest.update(
                preparationStartedAt=preparation_started_at,
                preparedAt=datetime.now(UTC).isoformat(),
                preparationSeconds=time.monotonic() - started,
            )
            await self.repo.publish_comparison(cid, manifest, info)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - preparation failure is a visible comparison state
            await self.repo.update_comparison(
                cid, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:1200]}
            )

    async def finish_comparison(self, cid):
        item = await self.repo.comparison(cid)
        runs = {mode: await self.repo.get_run(item[mode + "RunId"]) for mode in ("off", "on")}
        if any(r["status"] in ("queued", "running") for r in runs.values()):
            return
        manifest = item["manifest"]
        manifest["registries"] = {
            mode: {"hash": run.get("registryHash"), "bindings": run.get("registryBindings", {})}
            for mode, run in runs.items()
        }
        await self.repo.update_comparison(
            cid,
            {
                "status": "completed"
                if all(r["status"] == "completed" for r in runs.values())
                else "incomplete",
                "manifest": manifest,
                "finishedAt": datetime.now(UTC).isoformat(),
            },
        )
