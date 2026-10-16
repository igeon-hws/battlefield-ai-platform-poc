import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite


def timestamp():
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()

    async def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        await self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS source_events(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, status TEXT, created TEXT, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL);
        """)
        for run in await self.runs():
            if run["status"] == "running":
                await self.update_run(
                    run["runId"], {"status": "interrupted", "error": "server restarted"}
                )

    async def close(self):
        await self.db.close()

    async def _row(self, query: str, args=()):
        async with self.db.execute(query, args) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def _emit(self, kind: str, data: dict):
        await self.db.execute(
            "INSERT INTO events(body) VALUES(?)", (json.dumps({"type": kind, "data": data}),)
        )

    async def bootstrap(self, snapshot, *, gap=False):
        async with self.lock:
            try:
                snapshot = {**snapshot, "historyGap": gap}
                await self.db.execute(
                    "INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(snapshot),)
                )
                await self._emit("situation", snapshot)
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise

    def _new_run(self, question: str, conversation_id=None, event=None):
        return {
            "runId": uuid4().hex,
            "conversationId": None if event else (conversation_id or uuid4().hex),
            "question": question,
            "trigger": "c4i_event" if event else "user_query",
            "sourceEvent": event,
            "createdAt": timestamp(),
            "updatedAt": timestamp(),
            "status": "queued",
            "result": None,
            "toolCalls": [],
            "evidence": [],
            "iterations": [],
            "sourceContext": None,
            "selectedCourseId": None,
        }

    async def _insert_run(self, run):
        await self.db.execute(
            "INSERT INTO runs VALUES(?,?,?,?)",
            (run["runId"], run["status"], run["createdAt"], json.dumps(run)),
        )
        await self._emit("analysis", {"runId": run["runId"], "status": run["status"]})

    async def ingest(self, event):
        async with self.lock:
            if await self._row("SELECT body FROM source_events WHERE id=?", (event["eventId"],)):
                return False
            try:
                await self.db.execute(
                    "INSERT INTO source_events VALUES(?,?)", (event["eventId"], json.dumps(event))
                )
                await self.db.execute(
                    "INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(event["snapshot"]),)
                )
                await self._emit("situation", event["snapshot"])
                await self._emit(
                    "source_event", {k: v for k, v in event.items() if k != "snapshot"}
                )
                if event["type"] == "entity.status_changed":
                    safe_event = {k: v for k, v in event.items() if k != "snapshot"}
                    run = self._new_run(
                        "C4I 상태 변경을 분석하고 관측된 변화와 주의 사항을 근거와 함께 요약해줘. 방책은 요청하지 않았다. 이벤트: "
                        + json.dumps(safe_event, ensure_ascii=False),
                        event=safe_event,
                    )
                    await self._insert_run(run)
                await self.db.commit()
                return True
            except BaseException:
                await self.db.rollback()
                raise

    async def situation(self):
        async with self.lock:
            data = await self._row("SELECT body FROM state WHERE id=1") or {"entities": []}
            async with self.db.execute("SELECT COALESCE(MAX(seq),0) FROM events") as cursor:
                row = await cursor.fetchone()
            assert row is not None
            return data | {"platformCursor": row[0]}

    async def create_run(self, question: str, conversation_id=None):
        async with self.lock:
            async with self.db.execute("SELECT body FROM runs ORDER BY created") as cursor:
                existing = [json.loads(row[0]) for row in await cursor.fetchall()]
            if conversation_id:
                matching = [run for run in existing if run["conversationId"] == conversation_id]
                if not matching:
                    raise KeyError("conversation not found")
                if any(run["status"] in ("queued", "running") for run in matching):
                    raise ValueError("conversation busy")
            run = self._new_run(question, conversation_id)
            try:
                await self._insert_run(run)
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise
            return run

    async def get_run(self, run_id):
        async with self.lock:
            run = await self._row("SELECT body FROM runs WHERE id=?", (run_id,))
        if not run:
            raise KeyError(run_id)
        return run

    async def runs(self):
        async with (
            self.lock,
            self.db.execute("SELECT body FROM runs ORDER BY created DESC LIMIT 200") as cursor,
        ):
            return [json.loads(row[0]) for row in await cursor.fetchall()]

    async def conversation(self, conversation_id):
        async with (
            self.lock,
            self.db.execute("SELECT body FROM runs ORDER BY created, rowid") as cursor,
        ):
            return [
                run
                for row in await cursor.fetchall()
                if (run := json.loads(row[0]))["conversationId"] == conversation_id
                and run["trigger"] == "user_query"
            ]

    async def next_run(self):
        async with self.lock:
            return await self._row(
                "SELECT body FROM runs WHERE status='queued' ORDER BY created LIMIT 1"
            )

    async def update_run(self, run_id, changes):
        async with self.lock:
            run = await self._row("SELECT body FROM runs WHERE id=?", (run_id,))
            if not run:
                raise KeyError(run_id)
            run.update(changes)
            run["updatedAt"] = timestamp()
            await self.db.execute(
                "UPDATE runs SET status=?,body=? WHERE id=?",
                (run["status"], json.dumps(run), run_id),
            )
            await self._emit("analysis", {"runId": run_id, "status": run["status"]})
            await self.db.commit()
            return run

    async def history(self, conversation_id, exclude_run=None):
        if not conversation_id:
            return []
        runs = await self.conversation(conversation_id)
        completed = [
            r
            for r in runs
            if r["conversationId"] == conversation_id and r["runId"] != exclude_run and r["result"]
        ]
        history: list[dict[str, str]] = []
        size = 0
        for run in reversed(completed[-6:]):
            pair = [
                {"role": "user", "content": run["question"]},
                {
                    "role": "assistant",
                    "content": f"[과거 분석 {run['createdAt']}; 최신 사실 아님] "
                    + json.dumps(
                        {
                            "runId": run["runId"],
                            "answer": run["result"]["answer"],
                            "selectedCourseId": run.get("selectedCourseId"),
                            "selectedCourse": next(
                                (
                                    course
                                    for course in (run["result"].get("courses") or [])
                                    if course["id"] == run.get("selectedCourseId")
                                ),
                                None,
                            ),
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
            length = sum(len(item["content"].encode("utf-8")) for item in pair)
            if size + length > 8000:
                break
            history[0:0] = pair
            size += length
        return history

    async def select(self, run_id, course_id):
        run = await self.get_run(run_id)
        if (
            run["status"] != "completed"
            or not run.get("result")
            or course_id not in [c["id"] for c in (run["result"].get("courses") or [])]
        ):
            raise ValueError("invalid course selection")
        return await self.update_run(run_id, {"selectedCourseId": course_id})

    async def events(self, after):
        async with (
            self.lock,
            self.db.execute(
                "SELECT seq,body FROM events WHERE seq>? ORDER BY seq LIMIT 100", (after,)
            ) as cursor,
        ):
            return [(row[0], json.loads(row[1])) for row in await cursor.fetchall()]
