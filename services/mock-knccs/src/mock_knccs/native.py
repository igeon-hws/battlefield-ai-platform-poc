"""Standalone synthetic maritime C2: envelopes, composite tracks and knots."""

import base64
import json
import math
import os
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from battlefield_source_runtime.ledger import Ledger, content_hash, create_ledger_app, mount_ui
from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field


class ForcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engineering: Literal["UP", "DOWN", "UNKNOWN"] | None = None
    mission: Literal["GO", "HOLD", "UNKNOWN"] | None = None
    formationRef: str | None = None


class TransportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    delayHours: float = Field(ge=0, le=168)


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    serial: str
    thread: str
    text: str
    relayOf: str | None = None


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receiptId: str
    serial: str
    delivery: Literal["ACK"]


class MaritimeStore(Ledger):
    async def setup_native(self):
        schema = """
        CREATE TABLE IF NOT EXISTS navy_force_master(pennant TEXT PRIMARY KEY, hull_class TEXT, formation_ref TEXT);
        CREATE TABLE IF NOT EXISTS navy_force_state(pennant TEXT PRIMARY KEY, engineering TEXT, mission TEXT, geo_json TEXT, motion_json TEXT, report_time TEXT);
        CREATE TABLE IF NOT EXISTS navy_contacts(originator TEXT, track_no TEXT, domain TEXT, identity TEXT, PRIMARY KEY(originator,track_no));
        CREATE TABLE IF NOT EXISTS navy_contact_state(originator TEXT, track_no TEXT, geo_json TEXT, motion_json TEXT, reported_at TEXT, PRIMARY KEY(originator,track_no));
        CREATE TABLE IF NOT EXISTS navy_observations(observation_id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS navy_formations(formation_ref TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS navy_messages(serial TEXT PRIMARY KEY, received_at TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS navy_delivery_events(receipt_id TEXT PRIMARY KEY, serial TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS navy_associations(association_id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS navy_relations(relation_id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS navy_documents(document_id TEXT, version TEXT, hash TEXT, body TEXT, PRIMARY KEY(document_id,version));
        """
        if self.seed["sourceSchemaVersion"] in ("4.0.0", "5.0.0"):
            schema = "\n".join(line for line in schema.splitlines() if "_documents(" not in line)
        await self.db.executescript(schema)
        if self.seed["sourceSchemaVersion"] == "5.0.0":
            await self.db.execute(
                "CREATE TABLE IF NOT EXISTS navy_transports(transport_id TEXT PRIMARY KEY,body TEXT)"
            )

    async def persist_native(self, state):
        if self.seed["sourceSchemaVersion"] == "5.0.0":
            await self.db.execute("DELETE FROM navy_transports")
            for row in state["records"]["transports"]:
                await self.db.execute(
                    "INSERT INTO navy_transports VALUES(?,?)", (row["transportId"], json.dumps(row))
                )
        for table in (
            "navy_force_master",
            "navy_force_state",
            "navy_contacts",
            "navy_contact_state",
            "navy_observations",
            "navy_formations",
            "navy_messages",
            "navy_delivery_events",
            "navy_associations",
            "navy_relations",
            "navy_documents",
        ):
            if table.endswith("_documents") and self.seed["sourceSchemaVersion"] in (
                "4.0.0",
                "5.0.0",
            ):
                continue
            await self.db.execute(f"DELETE FROM {table}")
        r = state["records"]
        for force in r["own-forces"]:
            await self.db.execute(
                "INSERT INTO navy_force_master VALUES(?,?,?)",
                (force["pennant"], force["hullClass"], force["formationRef"]),
            )
            await self.db.execute(
                "INSERT INTO navy_force_state VALUES(?,?,?,?,?,?)",
                (
                    force["pennant"],
                    force["engineering"],
                    force["mission"],
                    json.dumps(force["geo"]),
                    json.dumps(force["motion"]),
                    state["sourceTime"],
                ),
            )
        for contact in r["contacts"]:
            await self.db.execute(
                "INSERT INTO navy_contacts VALUES(?,?,?,?)",
                (contact["originator"], contact["trackNo"], contact["domain"], contact["identity"]),
            )
            await self.db.execute(
                "INSERT INTO navy_contact_state VALUES(?,?,?,?,?)",
                (
                    contact["originator"],
                    contact["trackNo"],
                    json.dumps(contact["geo"]),
                    json.dumps(contact["motion"]),
                    contact["reportedAt"],
                ),
            )
        for row in r["tracks"]:
            await self.db.execute(
                "INSERT INTO navy_observations VALUES(?,?)", (row["observationId"], json.dumps(row))
            )
        for row in r["formations"]:
            await self.db.execute(
                "INSERT INTO navy_formations VALUES(?,?)", (row["formationRef"], json.dumps(row))
            )
        for row in r["messages"]:
            await self.db.execute(
                "INSERT INTO navy_messages VALUES(?,?,?)",
                (row["serial"], row["receivedAt"], json.dumps(row)),
            )
        for row in r["delivery-events"]:
            await self.db.execute(
                "INSERT INTO navy_delivery_events VALUES(?,?,?)",
                (row["receiptId"], row["serial"], json.dumps(row)),
            )
        for row in r["associations"]:
            await self.db.execute(
                "INSERT INTO navy_associations VALUES(?,?)", (row["associationId"], json.dumps(row))
            )
        for row in r["relations"]:
            await self.db.execute(
                "INSERT INTO navy_relations VALUES(?,?)", (row["id"], json.dumps(row))
            )
        for doc in r.get("documents", []):
            await self.db.execute(
                "INSERT INTO navy_documents VALUES(?,?,?,?)",
                (doc["documentId"], doc["version"], doc["hash"], json.dumps(doc)),
            )


def stable(state):
    records = deepcopy(state["records"])
    for row in records["own-forces"]:
        for key in ("geo", "motion", "engineering", "mission"):
            row.pop(key, None)
    for row in records["contacts"]:
        for key in ("geo", "motion", "reportedAt"):
            row.pop(key, None)
    for row in records.get("transports", []):
        for key in ("arrivalAt", "deliveryAt", "status", "updatedAt"):
            row.pop(key, None)
    records.pop("tracks")
    records.pop("delivery-events")
    return {
        **{k: state[k] for k in ("systemId", "datasetId", "epochId", "sourceSchemaVersion")},
        "records": records,
    }


def advance(state):
    for row in state["records"]["own-forces"] + state["records"]["contacts"]:
        pos, motion = row["geo"], row["motion"]
        distance = motion["knots"] * 1852 / 3600
        pos["latitude"] += distance * math.cos(math.radians(motion["course"])) / 111320
        pos["longitude"] += (
            distance
            * math.sin(math.radians(motion["course"]))
            / (111320 * math.cos(math.radians(pos["latitude"])))
        )


def install(app, store, read, control):
    def route(resource):
        async def listing(
            snapshotId: str,
            continuation: str | None = None,
            limit: int = Query(100, ge=1, le=100),
            originator: str | None = None,
            trackNo: str | None = None,
        ):
            snap = await store.snapshot(snapshotId)
            offset = 0
            binding = [snapshotId, resource, originator, trackNo, limit]
            if continuation:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(continuation))
                    if (
                        decoded["binding"] != binding
                        or not isinstance(decoded["offset"], int)
                        or decoded["offset"] < 0
                    ):
                        raise ValueError("cursor scope mismatch")
                    offset = decoded["offset"]
                except Exception as exc:
                    raise ValueError("invalid snapshot/resource-bound continuation") from exc
            rows = [
                r
                for r in snap["records"][resource]
                if (originator is None or r.get("originator") == originator)
                and (trackNo is None or r.get("trackNo") == trackNo)
            ]
            cursor = (
                base64.urlsafe_b64encode(
                    json.dumps({"binding": binding, "offset": offset + limit}).encode()
                ).decode()
                if offset + limit < len(rows)
                else None
            )
            return {
                "header": {
                    "source": "knccs",
                    "snapshotRef": snapshotId,
                    "total": len(rows),
                    "continuation": cursor,
                },
                "payload": rows[offset : offset + limit],
            }

        app.add_api_route(
            f"/api/v1/{resource}", listing, dependencies=[Depends(read)], name=f"sea_{resource}"
        )

    for resource in store.seed["records"]:
        route(resource)

    if store.seed["sourceSchemaVersion"] == "5.0.0":

        @app.patch("/api/v1/transports/{transport_id}", dependencies=[Depends(control)])
        async def delay_transport(transport_id: str, body: TransportPatch):
            async with store.lock:
                state = deepcopy(store.state)
                row = next(
                    (r for r in state["records"]["transports"] if r["transportId"] == transport_id),
                    None,
                )
                if row is None:
                    raise KeyError(transport_id)
                for key in ("arrivalAt", "deliveryAt"):
                    row[key] = (
                        datetime.fromisoformat(row[key]) + timedelta(hours=body.delayHours)
                    ).isoformat()
                row["updatedAt"] = state["sourceTime"]
                return await store.save(state, "transport.changed", {"transportId": transport_id})

    @app.post("/api/v1/messages", dependencies=[Depends(control)], status_code=201)
    async def receive_message(body: MessageInput):
        async with store.lock:
            state = deepcopy(store.state)
            if not body.serial or any(
                r["serial"] == body.serial for r in state["records"]["messages"]
            ):
                raise ValueError("new native message serial required")
            if body.thread not in {m["thread"] for m in state["records"]["messages"]}:
                raise ValueError("unknown native exercise thread")
            state["sourceTime"] = (
                datetime.fromisoformat(state["sourceTime"]) + timedelta(seconds=1)
            ).isoformat()
            state["records"]["messages"].append(
                {
                    **body.model_dump(exclude_none=True),
                    "sentAt": state["sourceTime"],
                    "receivedAt": state["sourceTime"],
                }
            )
            return await store.save(state, "message.received", {"serial": body.serial})

    @app.post("/api/v1/delivery-events", dependencies=[Depends(control)], status_code=201)
    async def receive_ack(body: ReceiptInput):
        async with store.lock:
            state = deepcopy(store.state)
            if (
                body.serial not in {r["serial"] for r in state["records"]["messages"]}
                or not body.receiptId
                or body.receiptId in {r["receiptId"] for r in state["records"]["delivery-events"]}
            ):
                raise ValueError("invalid native receipt/message reference")
            state["sourceTime"] = (
                datetime.fromisoformat(state["sourceTime"]) + timedelta(seconds=1)
            ).isoformat()
            state["records"]["delivery-events"].append(
                {**body.model_dump(), "receivedAt": state["sourceTime"]}
            )
            return await store.save(
                state, "message.acknowledged", {"serial": body.serial, "receiptId": body.receiptId}
            )

    @app.patch("/api/v1/own-forces/{pennant}", dependencies=[Depends(control)])
    async def patch(pennant: str, body: ForcePatch):
        changes = body.model_dump(exclude_unset=True)
        if not changes:
            raise ValueError("empty patch")
        async with store.lock:
            state = deepcopy(store.state)
            row = next((r for r in state["records"]["own-forces"] if r["pennant"] == pennant), None)
            if row is None:
                raise KeyError(pennant)
            if "formationRef" in changes and changes["formationRef"] not in {
                f["formationRef"] for f in state["records"]["formations"]
            }:
                raise ValueError("unknown formation")
            row.update(changes)
            return await store.save(
                state,
                "structure.changed" if "formationRef" in changes else "equipment.changed",
                {"pennant": pennant, "patch": changes},
            )


def create_app(path=None, *, tick_enabled=True, token=None, control_token=None):
    v5 = os.getenv("C4I_CONTRACT_VERSION") == "5"
    v4 = os.getenv("C4I_CONTRACT_VERSION") in ("4", "5")
    seed = json.loads(
        Path(__file__)
        .with_name(
            "native_seed_v5.json" if v5 else "native_seed_v4.json" if v4 else "native_seed.json"
        )
        .read_text(encoding="utf-8")
    )
    for doc in seed["records"].get("documents", []):
        doc["hash"] = content_hash(doc)
    baseline = deepcopy(seed)
    baseline["sourceTime"] = "2026-10-20T09:00:00Z"
    for key, time_field in (
        ("messages", "receivedAt"),
        ("delivery-events", "receivedAt"),
        ("contacts", "reportedAt"),
        ("tracks", "reportedAt"),
        ("associations", "knownAt"),
    ):
        baseline["records"][key] = [
            r for r in baseline["records"][key] if r[time_field] <= baseline["sourceTime"]
        ]
    store = MaritimeStore(
        path
        or os.getenv(
            "KNCCS_DB", "var/knccs-v5.db" if v5 else "var/knccs-v4.db" if v4 else "var/knccs-v3.db"
        ),
        "knccs",
        seed,
        stable,
        advance,
        baseline,
    )
    return mount_ui(
        create_ledger_app(
            store,
            install,
            tick_enabled=tick_enabled,
            token=os.getenv("KNCCS_READ_TOKEN", "") if token is None else token,
            control_token=os.getenv("KNCCS_CONTROL_TOKEN", "")
            if control_token is None
            else control_token,
        ),
        Path(__file__).parent / "web_static",
    )
