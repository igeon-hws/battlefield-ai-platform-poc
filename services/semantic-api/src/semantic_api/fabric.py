"""Fabric core: native access, catalog, display and reproducible context capture."""

import asyncio
import json
import math
import os
import time
from datetime import UTC, datetime

import httpx
from battlefield_geo import decorate
from c4i_contracts import Entity
from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

REF_FIELDS = ("datasetId", "epochId", "snapshotId", "sequence", "sourceTime", "stableDataHash")


def display(system, snapshot):
    entities = []
    if system == "atcis":
        for r in snapshot["records"]["equipment"]:
            entities.append(
                {
                    "entityId": r["equipmentId"],
                    "label": r["equipmentId"],
                    "kind": {
                        "TK": "tank",
                        "AAV": "armored_vehicle",
                        "LOG": "support_vehicle",
                        "UAS": "uav",
                    }.get(r["classCode"], "unknown"),
                    "availability": "unknown",
                    "affiliation": "friendly"
                    if r["side"] == "F"
                    else "hostile"
                    if r["side"] == "H"
                    else "unknown",
                    "unitId": r["ownerCode"],
                    "position": {"longitude": r["position"]["x"], "latitude": r["position"]["y"]},
                    "velocity": {"eastMps": r["vector"]["east"], "northMps": r["vector"]["north"]},
                    "nativeStatus": r["maintenanceCode"],
                }
            )
    else:
        for resource in ("own-forces", "contacts"):
            for r in snapshot["records"][resource]:
                speed, angle = (
                    r["motion"]["knots"] * 1852 / 3600,
                    math.radians(r["motion"]["course"]),
                )
                native_id = (
                    r["pennant"]
                    if resource == "own-forces"
                    else r["originator"] + "/" + r["trackNo"]
                )
                entities.append(
                    {
                        "entityId": native_id,
                        "label": native_id,
                        "kind": "naval_vessel" if resource == "own-forces" else "unknown",
                        "availability": "unknown",
                        "affiliation": "friendly"
                        if r["identity"] == "FRIEND"
                        else "hostile"
                        if r["identity"] == "HOSTILE"
                        else "unknown",
                        "unitId": r.get("formationRef"),
                        "position": r["geo"],
                        "velocity": {
                            "eastMps": speed * math.sin(angle),
                            "northMps": speed * math.cos(angle),
                        },
                        "nativeStatus": {k: r.get(k) for k in ("engineering", "mission", "domain")},
                    }
                )
    for e in entities:
        e.update(
            source=system,
            observedAt=snapshot["sourceTime"],
            updatedAt=snapshot["sourceTime"],
            revision=snapshot["sequence"],
        )
        e.update(
            decorate(Entity.model_validate({k: v for k, v in e.items() if k != "nativeStatus"}))
        )
    return {
        **{k: snapshot[k] for k in REF_FIELDS},
        "systemId": system,
        "running": snapshot["running"],
        "entities": entities,
    }


class Fabric:
    def __init__(self, sources=None, ensure_graph=None):
        self.sources = sources or {
            s: {
                "url": os.getenv(s.upper() + "_BASE_URL", f"http://127.0.0.1:{port}"),
                "token": os.getenv(s.upper() + "_READ_TOKEN", ""),
            }
            for s, port in (("atcis", 4100), ("knccs", 4110))
        }
        self.ensure_graph = ensure_graph

    async def get(self, system, path, params=None):
        config = self.sources[system]
        async with httpx.AsyncClient(
            base_url=config["url"],
            headers={"Authorization": "Bearer " + config["token"]} if config.get("token") else {},
            timeout=10,
        ) as client:
            r = await client.get("/api/v1" + path, params=params)
            r.raise_for_status()
            return r.json()

    async def capture(self, pins=None, allow_partial=False):
        if pins is not None and (
            set(pins) - set(self.sources) or not allow_partial and set(pins) != set(self.sources)
        ):
            raise ValueError("complete source snapshot set required")

        async def one(system):
            pin = pins[system] if pins else None
            raw = await self.get(system, "/snapshots/" + pin["snapshotId"] if pin else "/snapshot")
            ref = {k: raw[k] for k in REF_FIELDS}
            if (
                raw.get("sourceSchemaVersion") not in ("3.0.0", "4.0.0")
                or raw.get("systemId") != system
                or pin
                and pin != ref
            ):
                raise ValueError("native schema/source snapshot mismatch")
            return system, raw

        results = await asyncio.gather(
            *(one(s) for s in (pins if pins is not None else self.sources)),
            return_exceptions=allow_partial,
        )
        snapshots = {}
        for result in results:
            if isinstance(result, httpx.HTTPError) and allow_partial:
                continue
            if isinstance(result, BaseException):
                raise result
            system, raw = result
            snapshots[system] = raw
        if not snapshots:
            raise ValueError("no source snapshots available")
        return snapshots

    async def prepare(self, mode, pins=None, allow_partial=False):
        """OFF prepares native context without requiring a Graph; ON pins a READY build."""
        if mode not in ("off", "on"):
            raise ValueError("invalid semantic mode")
        if mode == "on" and allow_partial:
            raise ValueError("ON requires complete source coverage")
        started = time.monotonic()
        snapshots = await self.capture(pins, allow_partial)
        capture_span = time.monotonic() - started
        documents = [
            {"systemId": s, **d}
            for s, raw in snapshots.items()
            for d in raw["records"].get("documents", [])
        ]
        refs = {s: {k: raw[k] for k in REF_FIELDS} for s, raw in snapshots.items()}
        baseline_refs = {}
        for system, raw in snapshots.items():
            if raw.get("baselineSnapshotId"):
                baseline = await self.get(system, "/snapshots/" + raw["baselineSnapshotId"])
                baseline_refs[system] = {k: baseline[k] for k in REF_FIELDS}
        info = None
        if mode == "on":
            if self.ensure_graph is None:
                raise ValueError("Semantic graph preparation unavailable")
            info = await self.ensure_graph(refs)
        return {
            "semanticMode": mode,
            "semanticPolicyVersion": "3-domain-native-off",
            "sourceToolContractVersion": "3",
            "sourceSnapshotSet": refs,
            "baselineSourceSnapshotSet": baseline_refs,
            "documents": documents,
            "graphInfo": info,
            "capturedAt": datetime.now(UTC).isoformat(),
            "preparationSeconds": time.monotonic() - started,
            "captureSpanSeconds": capture_span,
            "sourceRunning": {s: raw["running"] for s, raw in snapshots.items()},
            "coverage": {s: "complete" if s in snapshots else "unavailable" for s in self.sources},
        }

    async def situation(self):
        # Geometry is a display projection; native codes stay available for independent analysis.
        results = await asyncio.gather(
            *(self.get(s, "/snapshot") for s in self.sources), return_exceptions=True
        )
        sources, coverage = {}, {}
        for system, raw in zip(self.sources, results, strict=True):
            if isinstance(raw, BaseException):
                coverage[system] = {"status": "unavailable", "error": type(raw).__name__}
            else:
                sources[system] = display(system, raw)
                coverage[system] = {"status": "complete"}
        return {"sources": sources, "coverage": coverage, "displayOnly": True}


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semanticMode: str | None = None
    knowledgeMode: str | None = None
    knowledgeSetVersion: str | None = None
    sourceSnapshotSet: dict | None = None
    allowPartial: bool = False


def install_fabric(app, read, ensure_graph=None):
    fabric = Fabric(ensure_graph=ensure_graph)
    app.state.fabric = fabric

    @app.get("/v1/sources", dependencies=[Depends(read)])
    async def sources():
        situation = await fabric.situation()
        return {
            "items": [
                {
                    "systemId": s,
                    "sourceSchemaVersion": "4.0.0"
                    if os.getenv("C4I_CONTRACT_VERSION") == "4"
                    else "3.0.0",
                    **situation["coverage"][s],
                }
                for s in fabric.sources
            ]
        }

    @app.get("/v1/catalog", dependencies=[Depends(read)])
    async def catalog():
        return {
            "datasetId": "c2-domain-demo-v4"
            if os.getenv("C4I_CONTRACT_VERSION") == "4"
            else "c2-domain-demo-v3",
            "sourceSchemaVersion": "4.0.0" if os.getenv("C4I_CONTRACT_VERSION") == "4" else "3.0.0",
            "layers": [
                "format",
                "entity",
                "organization",
                "status_and_aggregation",
                "lineage",
                "procedure",
                "composite",
            ],
            "entries": {
                "sources": "/v1/sources",
                "situation": "/v1/situation",
                "contexts": "/v1/analysis-contexts",
                "semanticRules": "/v1/concepts",
                "relations": "/v1/relations",
            },
        }

    @app.get("/v1/situation", dependencies=[Depends(read)])
    async def situation():
        return await fabric.situation()

    @app.get("/v1/source-projections/{system}", dependencies=[Depends(read)])
    async def source_projection(system: str, snapshotId: str | None = None):
        if system not in fabric.sources:
            raise HTTPException(422, "untrusted source")
        return display(
            system,
            await fabric.get(system, "/snapshots/" + snapshotId if snapshotId else "/snapshot"),
        )

    @app.post("/v1/analysis-contexts", dependencies=[Depends(read)])
    async def prepare(body: ContextRequest):
        if os.getenv("C4I_CONTRACT_VERSION") != "4":
            return await fabric.prepare(
                body.semanticMode or "off", body.sourceSnapshotSet, body.allowPartial
            )
        if body.semanticMode is not None or body.knowledgeMode not in (
            "native",
            "documents",
            "structured",
        ):
            raise ValueError("v4 requires explicit knowledgeMode, not semanticMode")
        result = await fabric.prepare("off", body.sourceSnapshotSet, body.allowPartial)
        result.update(
            knowledgeMode=body.knowledgeMode,
            semanticPolicyVersion="4-knowledge-abc",
            sourceToolContractVersion="4",
        )
        result.pop("semanticMode", None)
        result.pop("documents", None)
        if body.knowledgeMode != "native":
            from semantic_core.knowledge import KnowledgeCatalog

            catalog = KnowledgeCatalog()
            version = body.knowledgeSetVersion or catalog.version
            catalog = KnowledgeCatalog(version)
            for source in result["sourceSnapshotSet"].values():
                for item in catalog.documents:
                    known = item["document"].get("knownAt")
                    if known and datetime.fromisoformat(known) > datetime.fromisoformat(
                        source["sourceTime"]
                    ):
                        raise ValueError("knowledge knownAt beyond source snapshot")
            result.update(knowledgeSetVersion=version, knowledgeSetHash=catalog.hash)
            if body.knowledgeMode == "structured":
                if set(result["sourceSnapshotSet"]) != {"atcis", "knccs"} or body.allowPartial:
                    raise ValueError("structured requires complete sources")
                result["graphInfo"] = await ensure_graph(result["sourceSnapshotSet"], version)
                if result["graphInfo"].get("knowledgeSetHash") != catalog.hash:
                    raise ValueError("graph knowledge mismatch")
        return result

    @app.get("/v1/events", dependencies=[Depends(read)])
    async def events(request: Request, systemId: str, epochId: str, after: int = 0):
        if systemId not in fabric.sources:
            raise HTTPException(422, "untrusted source")

        async def generate():
            cursor = after
            while not await request.is_disconnected():
                raw = await fabric.get(systemId, "/snapshot")
                if raw["epochId"] != epochId:
                    yield 'event: reset\ndata: {"reloadRequired":true}\n\n'
                    return
                page = await fabric.get(
                    systemId,
                    "/events",
                    {"epochId": epochId, "after": cursor, "throughSequence": raw["sequence"]},
                )
                for event in page["items"]:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if not page["items"]:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(0.2)

        return StreamingResponse(generate(), media_type="text/event-stream")
