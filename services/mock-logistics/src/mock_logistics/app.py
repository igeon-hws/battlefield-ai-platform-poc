"""Source-owned logistics facts. No ontology, platform or graph dependency."""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Literal

import uvicorn
from battlefield_source_runtime.ledger import Ledger, create_ledger_app, mount_ui
from dotenv import load_dotenv
from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict

IDS = {
    "assets": "assetId",
    "work-orders": "workOrderId",
    "parts": "partId",
    "inventory": "inventoryId",
    "reservations": "reservationId",
    "supply-requests": "requestId",
    "cargo": "cargoId",
}


class LogisticsStore(Ledger):
    async def setup_native(self):
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS logistics_records(resource TEXT,id TEXT,body TEXT,PRIMARY KEY(resource,id))"
        )

    async def persist_native(self, state):
        await self.db.execute("DELETE FROM logistics_records")
        for resource, records in state["records"].items():
            for row in records:
                await self.db.execute(
                    "INSERT INTO logistics_records VALUES(?,?,?)",
                    (resource, row[IDS[resource]], json.dumps(row)),
                )


def stable(state):
    records = deepcopy(state["records"])
    for resource, keys in {
        "work-orders": ("status", "updatedAt", "otherFaults"),
        "inventory": ("onHand", "reserved", "updatedAt"),
        "cargo": ("status", "updatedAt"),
    }.items():
        for row in records[resource]:
            for key in keys:
                row.pop(key, None)
    return {
        **{k: state[k] for k in ("systemId", "datasetId", "epochId", "sourceSchemaVersion")},
        "records": records,
    }


class WorkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["WAIT_PART", "IN_PROGRESS", "DONE", "UNKNOWN"]


def install(app, store, read, control):
    def resource_route(resource):
        async def listing(
            snapshotId: str,
            offset: int = Query(0, ge=0),
            limit: int = Query(100, ge=1, le=100),
            id: str | None = None,
        ):
            raw = await store.snapshot(snapshotId)
            rows = [r for r in raw["records"][resource] if id is None or r[IDS[resource]] == id]
            return {
                "items": rows[offset : offset + limit],
                "total": len(rows),
                "nextOffset": offset + limit if offset + limit < len(rows) else None,
                "snapshotId": snapshotId,
            }

        app.add_api_route("/api/v1/" + resource, listing, dependencies=[Depends(read)])

    for resource in IDS:
        resource_route(resource)

    @app.patch("/api/v1/work-orders/{work_id}", dependencies=[Depends(control)])
    async def patch(work_id: str, body: WorkPatch):
        async with store.lock:
            state = deepcopy(store.state)
            row = next(
                (r for r in state["records"]["work-orders"] if r["workOrderId"] == work_id), None
            )
            if row is None:
                raise KeyError(work_id)
            row.update(body.model_dump(), updatedAt=state["sourceTime"])
            return await store.save(state, "work.changed", {"workOrderId": work_id})


def create_app(path=None, *, tick_enabled=True):
    load_dotenv()
    seed = json.loads(Path(__file__).with_name("seed.json").read_text(encoding="utf-8"))
    store = LogisticsStore(
        path or os.getenv("LOGISTICS_DB", "var/logistics-v5.db"),
        "logistics",
        seed,
        stable,
        lambda state: None,
    )
    return mount_ui(
        create_ledger_app(
            store,
            install,
            tick_enabled=tick_enabled,
            token=os.getenv("LOGISTICS_READ_TOKEN", ""),
            control_token=os.getenv("LOGISTICS_CONTROL_TOKEN", ""),
        ),
        Path(__file__).parent / "web_static",
    )


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.getenv("LOGISTICS_PORT", "4120")))
