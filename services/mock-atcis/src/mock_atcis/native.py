"""Standalone synthetic land C2. Native records only, no semantic imports."""

import json
import os
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from battlefield_source_runtime.ledger import Ledger, content_hash, create_ledger_app, mount_ui
from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict


class EquipmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    maintenanceCode: Literal["FMC", "PMC", "NMC", "UNK"] | None = None
    limitation: str | None = None
    ownerCode: str | None = None
    role: Literal["ORG", "ATT", "SUP", "CTRL"] | None = None


class ActivityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["DONE", "IN_PROGRESS", "NOT_STARTED", "UNKNOWN"]
    evidenceReport: str | None = None


class ReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reportId: str
    revision: int = 1
    incidentId: str
    unitCode: str
    text: str
    supersedes: str | None = None
    derivedFrom: str | None = None


class UnitPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    parentCode: str | None = None


class LandStore(Ledger):
    async def setup_native(self):
        await self.db.executescript("""
        CREATE TABLE IF NOT EXISTS land_equipment_master(equipment_id TEXT PRIMARY KEY, owner_code TEXT, class_code TEXT, role TEXT);
        CREATE TABLE IF NOT EXISTS land_equipment_state(equipment_id TEXT PRIMARY KEY, maintenance_code TEXT, limitation TEXT, position_json TEXT, vector_json TEXT, observed_at TEXT);
        CREATE TABLE IF NOT EXISTS land_units(unit_code TEXT PRIMARY KEY, name TEXT, parent_code TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS land_reports(report_id TEXT, revision INTEGER, known_at TEXT, body TEXT, PRIMARY KEY(report_id,revision));
        CREATE TABLE IF NOT EXISTS land_activities(activity_id TEXT PRIMARY KEY, step_code TEXT, state TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS land_journal(entry_id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS land_relations(relation_id TEXT PRIMARY KEY, body TEXT);
        CREATE TABLE IF NOT EXISTS land_documents(document_id TEXT, version TEXT, hash TEXT, body TEXT, PRIMARY KEY(document_id,version));
        """)

    async def persist_native(self, state):
        for table in (
            "land_equipment_master",
            "land_equipment_state",
            "land_units",
            "land_reports",
            "land_activities",
            "land_journal",
            "land_relations",
            "land_documents",
        ):
            await self.db.execute(f"DELETE FROM {table}")
        r = state["records"]
        for e in r["equipment"]:
            await self.db.execute(
                "INSERT INTO land_equipment_master VALUES(?,?,?,?)",
                (e["equipmentId"], e["ownerCode"], e["classCode"], e["role"]),
            )
            await self.db.execute(
                "INSERT INTO land_equipment_state VALUES(?,?,?,?,?,?)",
                (
                    e["equipmentId"],
                    e["maintenanceCode"],
                    e.get("limitation"),
                    json.dumps(e["position"]),
                    json.dumps(e["vector"]),
                    state["sourceTime"],
                ),
            )
        for u in r["units"]:
            await self.db.execute(
                "INSERT INTO land_units VALUES(?,?,?,?)",
                (u["unitCode"], u["name"], u["parentCode"], json.dumps(u)),
            )
        for report in r["reports"]:
            await self.db.execute(
                "INSERT INTO land_reports VALUES(?,?,?,?)",
                (report["reportId"], report["revision"], report["knownAt"], json.dumps(report)),
            )
        for activity in r["activities"]:
            await self.db.execute(
                "INSERT INTO land_activities VALUES(?,?,?,?)",
                (
                    activity["activityId"],
                    activity["stepCode"],
                    activity["state"],
                    json.dumps(activity),
                ),
            )
        for row in r["journal"]:
            await self.db.execute(
                "INSERT INTO land_journal VALUES(?,?)", (row["entryId"], json.dumps(row))
            )
        for row in r["relations"]:
            await self.db.execute(
                "INSERT INTO land_relations VALUES(?,?)", (row["id"], json.dumps(row))
            )
        for doc in r["documents"]:
            await self.db.execute(
                "INSERT INTO land_documents VALUES(?,?,?,?)",
                (doc["documentId"], doc["version"], doc["hash"], json.dumps(doc)),
            )


def stable(state):
    records = deepcopy(state["records"])
    for row in records["equipment"]:
        for key in ("position", "vector", "maintenanceCode", "limitation"):
            row.pop(key, None)
    for row in records["activities"]:
        row.pop("state", None)
        row.pop("evidenceReport", None)
        row.pop("knownAt", None)
    return {
        **{k: state[k] for k in ("systemId", "datasetId", "epochId", "sourceSchemaVersion")},
        "records": records,
    }


def advance(state):
    import math

    for row in state["records"]["equipment"]:
        pos, vector = row["position"], row["vector"]
        pos["y"] += vector["north"] / 111320
        pos["x"] += vector["east"] / (111320 * math.cos(math.radians(pos["y"])))


def install(app, store, read, control):
    def route(resource):
        async def listing(
            snapshotId: str,
            offset: int = Query(0, ge=0),
            limit: int = Query(100, ge=1, le=100),
            unitCode: str | None = None,
            equipmentId: str | None = None,
        ):
            snap = await store.snapshot(snapshotId)
            rows = snap["records"][resource]
            rows = [
                r
                for r in rows
                if (unitCode is None or r.get("ownerCode", r.get("unitCode")) == unitCode)
                and (equipmentId is None or r.get("equipmentId") == equipmentId)
            ]
            return {
                "systemId": "atcis",
                "snapshotId": snapshotId,
                "items": rows[offset : offset + limit],
                "total": len(rows),
                "nextOffset": offset + limit if offset + limit < len(rows) else None,
            }

        app.add_api_route(
            f"/api/v1/{resource}", listing, dependencies=[Depends(read)], name=f"land_{resource}"
        )

    for resource in store.seed["records"]:
        route(resource)

    @app.patch("/api/v1/units/{unit_code}", dependencies=[Depends(control)])
    async def unit_patch(unit_code: str, body: UnitPatch):
        changes = body.model_dump(exclude_unset=True)
        if not changes or "name" in changes and not changes["name"]:
            raise ValueError("empty native unit patch")
        async with store.lock:
            state = deepcopy(store.state)
            unit = next((u for u in state["records"]["units"] if u["unitCode"] == unit_code), None)
            if unit is None:
                raise KeyError(unit_code)
            if body.parentCode and body.parentCode not in {
                u["unitCode"] for u in state["records"]["units"]
            }:
                raise ValueError("unknown parent code")
            if body.name and body.name != unit["name"]:
                unit["previousName"] = unit["name"]
            unit.update(changes)
            if "parentCode" in changes:
                state["records"]["relations"] = [
                    r
                    for r in state["records"]["relations"]
                    if not (r["subject"] == unit_code and r["predicate"] == "PARENT")
                ]
                if body.parentCode:
                    state["records"]["relations"].append(
                        {
                            "id": "PARENT-" + unit_code,
                            "subject": unit_code,
                            "predicate": "PARENT",
                            "object": body.parentCode,
                            "validFrom": state["sourceTime"],
                            "validTo": None,
                        }
                    )
            return await store.save(
                state, "structure.changed", {"unitCode": unit_code, "patch": changes}
            )

    @app.patch("/api/v1/equipment/{equipment_id}", dependencies=[Depends(control)])
    async def patch(equipment_id: str, body: EquipmentPatch):
        changes = body.model_dump(exclude_unset=True)
        if not changes or any(v is None for k, v in changes.items() if k != "limitation"):
            raise ValueError("empty or null native field patch")
        async with store.lock:
            state = deepcopy(store.state)
            row = next(
                (r for r in state["records"]["equipment"] if r["equipmentId"] == equipment_id), None
            )
            if row is None:
                raise KeyError(equipment_id)
            if changes.get("ownerCode") and changes["ownerCode"] not in {
                u["unitCode"] for u in state["records"]["units"]
            }:
                raise ValueError("unknown unit code")
            row.update(changes)
            kind = (
                "structure.changed"
                if {"ownerCode", "role"} & changes.keys()
                else "equipment.changed"
            )
            return await store.save(state, kind, {"equipmentId": equipment_id, "patch": changes})

    @app.patch("/api/v1/activities/{activity_id}", dependencies=[Depends(control)])
    async def activity_patch(activity_id: str, body: ActivityPatch):
        async with store.lock:
            state = deepcopy(store.state)
            row = next(
                (r for r in state["records"]["activities"] if r["activityId"] == activity_id), None
            )
            if row is None:
                raise KeyError(activity_id)
            if body.evidenceReport and body.evidenceReport not in {
                r["reportId"] for r in state["records"]["reports"]
            }:
                raise ValueError("unknown original report")
            state["sourceTime"] = (
                datetime.fromisoformat(state["sourceTime"]) + timedelta(seconds=1)
            ).isoformat()
            row.update(body.model_dump(), knownAt=state["sourceTime"])
            return await store.save(state, "activity.changed", {"activityId": activity_id})

    @app.post("/api/v1/reports", dependencies=[Depends(control)], status_code=201)
    async def receive_report(body: ReportInput):
        async with store.lock:
            state = deepcopy(store.state)
            ids = {r["reportId"] for r in state["records"]["reports"]}
            if body.incidentId not in {r["incidentId"] for r in state["records"]["reports"]}:
                raise ValueError("unknown native incident")
            if not body.reportId or body.reportId in ids or body.revision < 1:
                raise ValueError("report record ID must be new; preserve earlier revision records")
            if body.unitCode not in {u["unitCode"] for u in state["records"]["units"]} or any(
                ref and ref not in ids for ref in (body.supersedes, body.derivedFrom)
            ):
                raise ValueError("unknown native reference")
            state["sourceTime"] = (
                datetime.fromisoformat(state["sourceTime"]) + timedelta(seconds=1)
            ).isoformat()
            state["records"]["reports"].append(
                {**body.model_dump(exclude_none=True), "knownAt": state["sourceTime"]}
            )
            return await store.save(state, "report.received", {"reportId": body.reportId})


def create_app(path=None, *, tick_enabled=True, token=None, control_token=None):
    seed = json.loads(Path(__file__).with_name("native_seed.json").read_text(encoding="utf-8"))
    for doc in seed["records"]["documents"]:
        doc["hash"] = content_hash(doc)
    baseline = deepcopy(seed)
    baseline["sourceTime"] = "2026-10-20T09:00:00Z"
    for key in ("reports", "journal", "activities"):
        baseline["records"][key] = [
            r for r in baseline["records"][key] if r["knownAt"] <= baseline["sourceTime"]
        ]
    store = LandStore(
        path or os.getenv("ATCIS_DB", "var/atcis-v3.db"), "atcis", seed, stable, advance, baseline
    )
    return mount_ui(
        create_ledger_app(
            store,
            install,
            tick_enabled=tick_enabled,
            token=os.getenv("ATCIS_READ_TOKEN", "") if token is None else token,
            control_token=os.getenv("ATCIS_CONTROL_TOKEN", "")
            if control_token is None
            else control_token,
        ),
        Path(__file__).parent / "web_static",
    )
