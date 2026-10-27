"""V4 repository/runtime: three isolated runs, one native Agent loop."""

import json
import os
import sqlite3
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from battlefield_ontology import digest

from platform_api.agent.agent import INSTRUCTIONS
from platform_api.agent.knowledge_tools import KnowledgeToolRunner
from platform_api.domain_runtime import DomainRuntime
from platform_api.multi_repository import MultiRepository

MODES = ("native", "documents", "structured")
POLICY = "4-knowledge-abc"


class KnowledgeRepository(MultiRepository):
    async def open(self):
        if self.path.exists():
            with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                has_runs = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'"
                ).fetchone()
                if has_runs and any(
                    json.loads(row[0]).get("sourceToolContractVersion") != "4"
                    for row in db.execute("SELECT body FROM runs")
                ):
                    raise ValueError(
                        "legacy analyses require their original policy; use a separate platform-v4.db"
                    )
        await super().open()

    async def create_comparison(self, question, first_mode="native", baseline_report_ref=None):
        if first_mode not in MODES:
            raise ValueError("knowledgeMode required")
        index = MODES.index(first_mode)
        item = {
            "comparisonId": uuid4().hex,
            "question": question,
            "baselineReportRef": baseline_report_ref,
            "status": "preparing",
            "createdAt": datetime.now(UTC).isoformat(),
            "manifest": None,
            "runIds": {},
            "error": None,
            "executionOrder": list(MODES[index:] + MODES[:index]),
        }
        async with self.lock:
            await self.db.execute(
                "INSERT INTO comparisons VALUES(?,?,?)",
                (item["comparisonId"], item["status"], json.dumps(item)),
            )
            await self.db.commit()
        return item

    async def publish_abc(self, item, manifest, graph_info):
        async with self.lock:
            current = await self._row(
                "SELECT body FROM comparisons WHERE id=?", (item["comparisonId"],)
            )
            if current["runIds"]:
                return current
            try:
                for mode in item["executionOrder"]:
                    run = self._new_run(item["question"])
                    run.update(
                        knowledgeMode=mode,
                        semanticMode="on" if mode == "structured" else "off",
                        sourceSnapshotSet=manifest["sourceSnapshotSet"],
                        baselineSourceSnapshotSet=manifest["baselineSourceSnapshotSet"],
                        baselineReportRef=item.get("baselineReportRef"),
                        comparisonId=item["comparisonId"],
                        graphInfo=graph_info if mode == "structured" else None,
                    )
                    if mode != "native":
                        run.update(
                            knowledgeSetVersion=manifest["knowledgeSetVersion"],
                            knowledgeSetHash=manifest["knowledgeSetHash"],
                        )
                    if mode == "structured" and graph_info is None:
                        run.update(
                            status="failed",
                            error=manifest.get(
                                "structuredPreparationError", "structured preparation failed"
                            ),
                        )
                    await self._insert_run(run)
                    current["runIds"][mode] = run["runId"]
                current.update(status="running", manifest=manifest)
                await self.db.execute(
                    "UPDATE comparisons SET status=?,body=? WHERE id=?",
                    (current["status"], json.dumps(current), item["comparisonId"]),
                )
                await self.db.commit()
                return current
            except BaseException:
                await self.db.rollback()
                raise


class KnowledgeRuntime(DomainRuntime):
    def __init__(self, *args):
        super().__init__(*args)
        self.mcp_status["knowledge"] = {"connected": False, "error": None}

    async def capture(self, *, strict=False, overrides=None):
        context = await self.fabric_request(
            "POST",
            "/v1/analysis-contexts",
            json={
                "knowledgeMode": "native",
                "sourceSnapshotSet": None,
                "allowPartial": not strict,
            },
        )
        if overrides:
            pins = {**context["sourceSnapshotSet"], **overrides}
            context = await self.fabric_request(
                "POST",
                "/v1/analysis-contexts",
                json={
                    "knowledgeMode": "native",
                    "sourceSnapshotSet": pins,
                    "allowPartial": not strict,
                },
            )
        if strict and (
            set(context["sourceSnapshotSet"]) != {"atcis", "knccs"}
            or any(context["sourceRunning"].values())
            and context["captureSpanSeconds"] > 2
        ):
            raise ValueError("incomplete or inconsistent Fabric capture")
        self.last_capture = {
            k: context[k]
            for k in (
                "capturedAt",
                "captureSpanSeconds",
                "sourceRunning",
                "baselineSourceSnapshotSet",
            )
        }
        self.baseline_snapshots = context["baselineSourceSnapshotSet"]
        return context["sourceSnapshotSet"]

    async def prepare_run_context(self, pins):
        context = await self.fabric_request(
            "POST",
            "/v1/analysis-contexts",
            json={
                "knowledgeMode": "native",
                "sourceSnapshotSet": pins,
                "allowPartial": len(pins) < 2,
            },
        )
        return context["baselineSourceSnapshotSet"]

    def run_configs(self, run):
        configs = dict(self.sources)
        if run["knowledgeMode"] != "native":
            configs["knowledge"] = {
                "mcpUrl": os.getenv("KNOWLEDGE_MCP_URL", "http://127.0.0.1:4430/mcp"),
                "mcpToken": os.getenv("KNOWLEDGE_MCP_TOKEN", ""),
            }
        if run["knowledgeMode"] == "structured":
            configs["semantic"] = self.semantic
        return configs

    def make_runner(self, run, clients, pins, info):
        return KnowledgeToolRunner(
            clients, pins, run["knowledgeMode"], info, run.get("knowledgeManifest")
        )

    async def _execute_run(self, run, log):
        started = monotonic()
        try:
            mode = run["knowledgeMode"]
            if mode not in MODES:
                raise ValueError("knowledge mode required")
            pins = run.get("sourceSnapshotSet") or await self.capture()
            context = await self.fabric_request(
                "POST",
                "/v1/analysis-contexts",
                json={
                    "knowledgeMode": mode,
                    "sourceSnapshotSet": pins,
                    "knowledgeSetVersion": run.get("knowledgeSetVersion"),
                    "allowPartial": mode != "structured" and len(pins) < 2,
                },
            )
            run.update(
                sourceSnapshotSet=pins,
                graphInfo=context["graphInfo"],
                baselineSourceSnapshotSet=context["baselineSourceSnapshotSet"],
            )
            if mode != "native":
                manifest = await self.fabric_request(
                    "GET", "/v1/knowledge/sets/" + context["knowledgeSetVersion"]
                )
                run.update(
                    knowledgeManifest=manifest,
                    knowledgeSetVersion=context["knowledgeSetVersion"],
                    knowledgeSetHash=context["knowledgeSetHash"],
                )
            run["knowledgePreparationSeconds"] = monotonic() - started
            await self.repo.update_run(run["runId"], run)
            await log.emit(
                "knowledge_context",
                {
                    "knowledgeMode": mode,
                    "knowledgeSetVersion": run.get("knowledgeSetVersion"),
                    "knowledgeSetHash": run.get("knowledgeSetHash"),
                },
            )
            await super()._execute_run(run, log)
        except Exception as exc:  # noqa: BLE001 - preserve per-run/discovery failure
            await self.repo.update_run(
                run["runId"], {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:1200]}
            )

    async def prepare_comparison(self, item):
        cid = item["comparisonId"]
        started = monotonic()
        try:
            pins = await self.capture(strict=True)
            docs = await self.fabric_request(
                "POST",
                "/v1/analysis-contexts",
                json={"knowledgeMode": "documents", "sourceSnapshotSet": pins},
            )
            manifest = {
                "question": item["question"],
                "baselineReportRef": item.get("baselineReportRef"),
                "questionHash": digest(item["question"]),
                "sourceSnapshotSet": pins,
                **self.last_capture,
                "knowledgeSetVersion": docs["knowledgeSetVersion"],
                "knowledgeSetHash": docs["knowledgeSetHash"],
                "comparisonPolicyVersion": POLICY,
                "knowledgePreparationSeconds": docs["preparationSeconds"],
                "semanticPolicyVersion": POLICY,
                "sourceToolContractVersion": "4",
                "agentBudget": self.agent_limits,
                "modelId": getattr(self.provider, "model", "test:" + type(self.provider).__name__),
                "systemPromptVersion": digest(INSTRUCTIONS),
                "executionOrder": item["executionOrder"],
                "conversationPolicy": "three-empty-isolated-conversations",
                "effects": {
                    "A-B": "domain knowledge access",
                    "B-C": "structured knowledge and evaluation stack",
                },
            }
            # Graph preparation failure is recorded on C, not used to discard A/B.
            graph_info = None
            try:
                context = await self.fabric_request(
                    "POST",
                    "/v1/analysis-contexts",
                    json={
                        "knowledgeMode": "structured",
                        "sourceSnapshotSet": pins,
                        "knowledgeSetVersion": docs["knowledgeSetVersion"],
                    },
                )
                graph_info = context["graphInfo"]
                manifest["graphVersion"] = graph_info["graphVersion"]
                manifest["structuredPreparationSeconds"] = context["preparationSeconds"]
            except Exception as exc:  # noqa: BLE001 - preserve per-run/discovery failure
                manifest["structuredPreparationError"] = type(exc).__name__ + ": " + str(exc)[:400]
            manifest["preparationSeconds"] = monotonic() - started
            await self.repo.publish_abc(item, manifest, graph_info)
        except Exception as exc:  # noqa: BLE001 - preserve per-run/discovery failure
            await self.repo.update_comparison(
                cid, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:1200]}
            )

    async def finish_comparison(self, cid):
        item = await self.repo.comparison(cid)
        runs = {m: await self.repo.get_run(r) for m, r in item.get("runIds", {}).items()}
        if not runs or any(r["status"] in ("queued", "running") for r in runs.values()):
            return
        manifest = item["manifest"]
        manifest["registries"] = {
            m: {"hash": r.get("registryHash"), "bindings": r.get("registryBindings", {})}
            for m, r in runs.items()
        }
        await self.repo.update_comparison(
            cid,
            {
                "status": "completed"
                if len(runs) == 3 and all(r["status"] == "completed" for r in runs.values())
                else "incomplete",
                "manifest": manifest,
                "finishedAt": datetime.now(UTC).isoformat(),
            },
        )
