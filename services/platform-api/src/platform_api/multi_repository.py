import json
import sqlite3
from uuid import uuid4

from platform_api.repository import Repository, timestamp


class ConversationNotFound(KeyError):
    pass


class MultiRepository(Repository):
    def __init__(self, path, auto_mode="off", policy_version="2-native-off", source_contract="2"):
        super().__init__(path)
        if auto_mode not in ("off", "on"):
            raise ValueError("invalid automatic semantic mode")
        self.auto_mode = auto_mode
        self.policy_version, self.source_contract = policy_version, source_contract

    async def open(self):
        # Read-only compatibility check BEFORE base.open can modify interrupted runs.
        if self.path.exists():
            with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                tables = {
                    r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                if tables and "platform_meta" not in tables:
                    raise ValueError("incompatible schema: use a separate platform-vnext.db")
                if "platform_meta" in tables and db.execute(
                    "SELECT version FROM platform_meta WHERE id=1"
                ).fetchone() != (2,):
                    raise ValueError("incompatible platform schema")
        await super().open()
        await self.db.executescript("""
          CREATE TABLE IF NOT EXISTS platform_meta(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL);
          INSERT OR IGNORE INTO platform_meta VALUES(1,2);
          CREATE TABLE IF NOT EXISTS comparisons(id TEXT PRIMARY KEY,status TEXT NOT NULL,body TEXT NOT NULL);
        """)

    def _new_run(self, question, conversation_id=None, event=None):
        return super()._new_run(question, conversation_id, event) | {
            "semanticMode": self.auto_mode if event else "off",
            "sourceSnapshotSet": None,
            "graphInfo": None,
            "comparisonId": None,
            "semanticPolicyVersion": self.policy_version,
            "sourceToolContractVersion": self.source_contract,
            **({"knowledgeMode": "native"} if self.source_contract == "4" else {}),
        }

    async def enqueue(
        self,
        question,
        mode="off",
        conversation_id=None,
        snapshots=None,
        graph_info=None,
        event=None,
        baseline_report_ref=None,
        knowledge_mode=None,
    ):
        # New modes/policies must not inherit another mode's interpreted conversation.
        if mode not in ("off", "on"):
            raise ValueError("invalid semantic mode")
        if self.source_contract == "4" and knowledge_mode not in (
            "native",
            "documents",
            "structured",
        ):
            raise ValueError("knowledgeMode required")
        async with self.lock:
            if conversation_id:
                async with self.db.execute("SELECT body FROM runs") as cursor:
                    previous = [json.loads(row[0]) for row in await cursor.fetchall()]
                matching = [r for r in previous if r["conversationId"] == conversation_id]
                if not matching:
                    raise ConversationNotFound("conversation not found")
                if self.source_contract == "4" and any(
                    r.get("knowledgeMode") != knowledge_mode for r in matching
                ):
                    raise ValueError("knowledge mode switch requires a new conversation")
                if any(r.get("semanticMode", "off") != mode for r in matching):
                    raise ValueError("mode switch requires a new conversation")
                if any(r.get("semanticPolicyVersion") != self.policy_version for r in matching):
                    raise ValueError("policy changed; start a new conversation")
                if any(r["status"] in ("queued", "running") for r in matching):
                    raise ValueError("conversation busy")
            run = self._new_run(question, conversation_id, event)
            run.update(semanticMode=mode, sourceSnapshotSet=snapshots, graphInfo=graph_info)
            if knowledge_mode:
                run["knowledgeMode"] = knowledge_mode
                if conversation_id and knowledge_mode != "native":
                    previous_version = next(
                        (
                            r.get("knowledgeSetVersion")
                            for r in reversed(matching)
                            if r.get("knowledgeSetVersion")
                        ),
                        None,
                    )
                    if previous_version:
                        run["knowledgeSetVersion"] = previous_version
            run["baselineReportRef"] = baseline_report_ref
            try:
                await self._insert_run(run)
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise
            return run

    async def save_source(self, system, snapshot, event=None, snapshots=None):
        async with self.lock:
            event_key = json.dumps([system, event["epochId"], event["eventId"]]) if event else None
            if event_key and await self._row(
                "SELECT body FROM source_events WHERE id=?", (event_key,)
            ):
                return False
            state = await self._row("SELECT body FROM state WHERE id=1") or {
                "schemaVersion": 2,
                "sources": {},
            }
            state["sources"][system] = snapshot
            state["entities"] = [
                {
                    **e,
                    "entityId": source + "/" + e["entityId"],
                    "nativeId": e["entityId"],
                    "source": source,
                }
                for source, data in state["sources"].items()
                for e in data.get("entities", [])
            ]
            try:
                if event_key:
                    await self.db.execute(
                        "INSERT INTO source_events VALUES(?,?)", (event_key, json.dumps(event))
                    )
                await self.db.execute(
                    "INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(state),)
                )
                await self._emit("situation", state)
                if event:
                    await self._emit("source_event", {**event, "systemId": system})
                if event and event["type"] in (
                    "equipment.changed",
                    "structure.changed",
                    "activity.changed",
                    "report.received",
                    "message.received",
                ):
                    run = self._new_run(
                        "모의 C4I 이벤트에 따른 관측 변화와 한계를 근거와 함께 설명해줘. 이벤트: "
                        + json.dumps({**event, "systemId": system}, ensure_ascii=False),
                        event={**event, "systemId": system},
                    )
                    run["sourceSnapshotSet"] = snapshots
                    await self._insert_run(run)
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise
            return True

    async def create_comparison(self, question, first_mode="off", baseline_report_ref=None):
        item = {
            "comparisonId": uuid4().hex,
            "question": question,
            "baselineReportRef": baseline_report_ref,
            "status": "preparing",
            "createdAt": timestamp(),
            "manifest": None,
            "offRunId": None,
            "onRunId": None,
            "error": None,
        }
        item["executionOrder"] = [first_mode, "on" if first_mode == "off" else "off"]
        async with self.lock:
            await self.db.execute(
                "INSERT INTO comparisons VALUES(?,?,?)",
                (item["comparisonId"], item["status"], json.dumps(item)),
            )
            await self.db.commit()
        return item

    async def comparison(self, comparison_id):
        async with self.lock:
            result = await self._row("SELECT body FROM comparisons WHERE id=?", (comparison_id,))
        if not result:
            raise KeyError(comparison_id)
        return result

    async def next_comparison(self):
        async with self.lock:
            return await self._row(
                "SELECT body FROM comparisons WHERE status='preparing' ORDER BY rowid LIMIT 1"
            )

    async def active_comparisons(self):
        async with (
            self.lock,
            self.db.execute("SELECT body FROM comparisons WHERE status='running'") as cursor,
        ):
            return [json.loads(r[0]) for r in await cursor.fetchall()]

    async def comparisons(self):
        async with (
            self.lock,
            self.db.execute("SELECT body FROM comparisons ORDER BY rowid DESC LIMIT 100") as cursor,
        ):
            return [json.loads(r[0]) for r in await cursor.fetchall()]

    async def update_comparison(self, comparison_id, changes):
        async with self.lock:
            result = await self._row("SELECT body FROM comparisons WHERE id=?", (comparison_id,))
            if not result:
                raise KeyError(comparison_id)
            result.update(changes)
            await self.db.execute(
                "UPDATE comparisons SET status=?,body=? WHERE id=?",
                (result["status"], json.dumps(result), comparison_id),
            )
            await self.db.commit()
            return result

    async def publish_comparison(self, comparison_id, manifest, graph_info):
        async with self.lock:
            item = await self._row("SELECT body FROM comparisons WHERE id=?", (comparison_id,))
            if not item:
                raise KeyError(comparison_id)
            if item["offRunId"]:
                return item
            try:
                for mode in item.get("executionOrder", ("off", "on")):
                    run = self._new_run(item["question"])
                    run.update(
                        semanticMode=mode,
                        sourceSnapshotSet=manifest["sourceSnapshotSet"],
                        graphInfo=graph_info if mode == "on" else None,
                        comparisonId=comparison_id,
                        baselineReportRef=manifest.get("baselineReportRef"),
                    )
                    await self._insert_run(run)
                    item[mode + "RunId"] = run["runId"]
                item.update(status="running", manifest=manifest)
                await self.db.execute(
                    "UPDATE comparisons SET status=?,body=? WHERE id=?",
                    (item["status"], json.dumps(item), comparison_id),
                )
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise
            return item
