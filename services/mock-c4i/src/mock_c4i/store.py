import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
from battlefield_geo import advance, decorate
from c4i_contracts import Entity, EntityFilter, EntityPatch

from mock_c4i.scenario import get_scenario, legacy_scenario


def now() -> str:
    return datetime.now(UTC).isoformat()


class CursorExpired(ValueError):
    pass


class C4IStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()
        self.seed: list[Entity] = []

    async def open(self, seed: list[Entity], *, scenario=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        await self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, epoch TEXT, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS current_state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
        """)
        self.seed = seed
        self.target_scenario = scenario or legacy_scenario()
        async with self.db.execute("SELECT body FROM current_state WHERE id=1") as cursor:
            row = await cursor.fetchone()
        self.state = json.loads(row[0]) if row else {}
        if not row:
            await self.reset()

    async def close(self):
        await self.db.close()

    async def _save(self, entities: list[Entity], event_type: str, payload: dict, *, reset=False):
        stamp = now()
        revision = 0 if reset else self.state["revision"] + 1
        epoch = uuid4().hex if reset else self.state["epochId"]
        updated = [
            e.model_copy(update={"revision": revision, "updated_at": stamp, "observed_at": stamp})
            for e in entities
        ]
        scenario = (
            self.target_scenario
            if reset
            else self.state.get("scenario") or get_scenario(self.state["scenarioId"])
        )
        snapshot = {
            "scenarioId": scenario["scenarioId"],
            "scenario": scenario,
            "epochId": epoch,
            "revision": revision,
            "previousSnapshotId": None if reset else self.state["snapshotId"],
            "snapshotId": uuid4().hex,
            "sourceTime": stamp,
            "simulationTime": 0
            if reset
            else self.state["simulationTime"] + (1 if event_type == "positions.updated" else 0),
            "running": False if reset else self.state["running"],
            "entities": [decorate(e) for e in updated],
        }
        event = {
            "eventId": uuid4().hex,
            "epochId": epoch,
            "revision": revision,
            "snapshotId": snapshot["snapshotId"],
            "occurredAt": stamp,
            "type": event_type,
            "payload": payload,
        }
        try:
            cursor = await self.db.execute(
                "INSERT INTO events(epoch,body) VALUES(?,?)", (epoch, "{}")
            )
            sequence = cursor.lastrowid
            snapshot["sequence"] = sequence
            event["sequence"] = sequence
            event["entityId"] = payload.get("entityId")
            event["snapshot"] = snapshot
            await self.db.execute(
                "UPDATE events SET body=? WHERE seq=?", (json.dumps(event), sequence)
            )
            await self.db.execute(
                "INSERT INTO snapshots VALUES(?,?)", (snapshot["snapshotId"], json.dumps(snapshot))
            )
            await self.db.execute(
                "INSERT OR REPLACE INTO current_state VALUES(1,?)", (json.dumps(snapshot),)
            )
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise
        self.state = snapshot
        return snapshot

    def _models(self) -> list[Entity]:
        fields = set(Entity.model_fields)
        aliases = {field.alias for field in Entity.model_fields.values()}
        return [
            Entity.model_validate({k: v for k, v in e.items() if k in fields or k in aliases})
            for e in self.state["entities"]
        ]

    async def reset(self):
        async with self.lock:
            return await self._save(self.seed, "scenario.reset", {}, reset=True)

    async def running(self, value: bool):
        async with self.lock:
            previous = self.state
            self.state = {**self.state, "running": value}
            try:
                return await self._save(self._models(), "simulation.changed", {"running": value})
            except BaseException:
                self.state = previous
                raise

    async def tick(self):
        async with self.lock:
            entities = [advance(e, 1) for e in self._models()]
            scenario = self.state.get("scenario") or get_scenario(self.state["scenarioId"])
            zones = {zone["id"]: zone for zone in scenario["zones"]}
            for entity in entities:
                west, south, east, north = zones.get(entity.zone_id, {}).get(
                    "bounds", scenario["bounds"]
                )
                if (
                    not west <= entity.position.longitude <= east
                    or not south <= entity.position.latitude <= north
                ):
                    entity.position.longitude = min(east, max(west, entity.position.longitude))
                    entity.position.latitude = min(north, max(south, entity.position.latitude))
                    entity.velocity.east_mps = entity.velocity.north_mps = 0
            return await self._save(entities, "positions.updated", {})

    async def patch(self, entity_id: str, data: dict):
        patch = EntityPatch.model_validate(data)
        async with self.lock:
            entities = self._models()
            for index, entity in enumerate(entities):
                if entity.entity_id == entity_id:
                    before = entity.public()
                    entities[index] = Entity.model_validate(
                        {
                            **before,
                            **patch.model_dump(mode="json", by_alias=True, exclude_unset=True),
                        }
                    )
                    return await self._save(
                        entities,
                        "entity.status_changed",
                        {
                            "entityId": entity_id,
                            "changedFields": list(data),
                            "before": before,
                            "after": entities[index].public(),
                        },
                    )
            raise KeyError(entity_id)

    async def snapshot(self, snapshot_id: str | None = None):
        if snapshot_id is None:
            return json.loads(json.dumps(self.state)) | {
                "scenario": self.state.get("scenario") or get_scenario(self.state["scenarioId"])
            }
        async with self.db.execute(
            "SELECT body FROM snapshots WHERE id=?", (snapshot_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise KeyError(snapshot_id)
        snapshot = json.loads(row[0])
        return snapshot | {
            "scenario": snapshot.get("scenario") or get_scenario(snapshot["scenarioId"])
        }

    async def entities(self, snapshot_id: str | None, filters: EntityFilter, limit=100, cursor=0):
        snapshot = await self.snapshot(snapshot_id)
        items = [
            e
            for e in snapshot["entities"]
            if filters.matches(
                Entity.model_validate(
                    {
                        k: v
                        for k, v in e.items()
                        if k not in ("displayVector", "speedMps", "bearingDegrees")
                    }
                )
            )
        ]
        return {
            "items": items[cursor : cursor + limit],
            "matchedCount": len(items),
            "nextCursor": cursor + limit if cursor + limit < len(items) else None,
            "snapshotId": snapshot["snapshotId"],
            "sourceTime": snapshot["sourceTime"],
            "appliedFilter": filters.public(),
        }

    async def summary(self, snapshot_id: str | None, filters: EntityFilter, group_by: list[str]):
        if set(group_by) - {
            "kind",
            "affiliation",
            "availability",
            "status",
            "maintenanceStatus",
            "unitId",
            "zoneId",
        }:
            raise ValueError("invalid groupBy")
        result = await self.entities(snapshot_id, filters, limit=10000)
        groups = Counter(
            tuple(
                e.get(field, "unknown" if field == "maintenanceStatus" else None)
                for field in group_by
            )
            for e in result["items"]
        )
        return {k: v for k, v in result.items() if k not in ("items", "nextCursor")} | {
            "countUnit": "entity",
            "groups": [
                dict(zip(group_by, values)) | {"count": count} for values, count in groups.items()
            ],
        }

    async def events(
        self,
        epoch_id: str,
        after: int,
        through: int | None = None,
        limit=100,
        *,
        across_epochs=False,
    ):
        async with self.db.execute(
            "SELECT 1 FROM events WHERE epoch=? LIMIT 1", (epoch_id,)
        ) as cursor:
            if not await cursor.fetchone():
                raise CursorExpired(epoch_id)
        if after:
            async with self.db.execute("SELECT 1 FROM events WHERE seq=?", (after,)) as cursor:
                if not await cursor.fetchone():
                    raise CursorExpired(str(after))
        query = "SELECT body FROM events WHERE seq>? AND seq<=?"
        args: list[Any] = [after, through if through is not None else 2**62]
        if not across_epochs:
            query += " AND epoch=?"
            args.append(epoch_id)
        query += " ORDER BY seq LIMIT ?"
        args.append(limit)
        async with self.db.execute(query, args) as cursor:
            return [json.loads(row[0]) for row in await cursor.fetchall()]

    async def entity_history(
        self, entity_id: str, epoch_id: str, after: int, through: int, limit: int
    ):
        if after > through:
            raise ValueError("after must not exceed throughSequence")
        events = await self.events(epoch_id, after, through, limit + 1)
        page = events[:limit]
        items = []
        for event in page:
            entity = next(
                (item for item in event["snapshot"]["entities"] if item["entityId"] == entity_id),
                None,
            )
            if entity:
                items.append(
                    {
                        "sequence": event["sequence"],
                        "snapshotId": event["snapshotId"],
                        "sourceTime": event["occurredAt"],
                        "eventType": event["type"],
                        "entity": entity,
                    }
                )
        return {
            "entityId": entity_id,
            "epochId": epoch_id,
            "throughSequence": through,
            "items": items,
            "nextAfter": page[-1]["sequence"] if len(events) > limit else None,
        }

    async def changes(self, before: str, after: str):
        a, b = await self.snapshot(before), await self.snapshot(after)
        if a["epochId"] != b["epochId"]:
            raise ValueError("cannot compare different epochs")
        previous = {e["entityId"]: e for e in a["entities"]}

        def comparable(item):
            return {
                k: v
                for k, v in (item or {}).items()
                if k not in ("revision", "updatedAt", "observedAt")
            }

        return {
            "fromSnapshotId": before,
            "snapshotId": after,
            "sourceTime": b["sourceTime"],
            "items": [
                {"entityId": e["entityId"], "before": previous.get(e["entityId"]), "after": e}
                for e in b["entities"]
                if comparable(previous.get(e["entityId"])) != comparable(e)
            ],
        }
