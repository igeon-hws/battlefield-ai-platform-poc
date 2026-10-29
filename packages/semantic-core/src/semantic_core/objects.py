"""Deterministic object context, reusable without a model or Agent runtime."""

import asyncio
from datetime import datetime

RESOURCE_FIELDS = {
    "equipment": ("equipment", "equipmentId"),
    "unit": ("units", "unitCode"),
    "asset": ("assets", "assetId"),
    "work-order": ("work-orders", "workOrderId"),
    "part": ("parts", "partId"),
    "inventory": ("inventory", "inventoryId"),
    "reservation": ("reservations", "reservationId"),
    "supply-request": ("supply-requests", "requestId"),
    "cargo": ("cargo", "cargoId"),
    "transport": ("transports", "transportId"),
    "own-force": ("own-forces", "pennant"),
    "contact": ("contacts", "originator/trackNo"),
}


def record_id(row, field):
    return (
        "/".join(str(row.get(k, "")) for k in field.split("/")) if "/" in field else row.get(field)
    )


def active_registration(edge, as_of):
    moment = datetime.fromisoformat(as_of)
    return (not edge.get("validFrom") or datetime.fromisoformat(edge["validFrom"]) <= moment) and (
        not edge.get("validTo") or moment < datetime.fromisoformat(edge["validTo"])
    )


def resolve_identity(nodes, edges, system, kind, native_id, as_of):
    if kind == "own-force":
        kind = "equipment"
    key = f"{system}:{kind}:{native_id}"
    if key not in {n["key"] for n in nodes}:
        return {"status": "unresolved", "canonicalId": None, "evidenceRefs": [], "sourceRefs": []}
    relevant = [
        e
        for e in edges
        if e["kind"] in ({"SAME_AS", "REFERS_TO"} if kind == "contact" else {"SAME_AS"})
        and key in (e["start"], e["end"])
        and active_registration(e, as_of)
    ]
    candidates = {e["end"] for e in relevant}
    if system != "logistics" and any(n["key"] == key and n["label"] == "Equipment" for n in nodes):
        candidates.add(key)
    status = (
        "resolved" if len(candidates) == 1 else "ambiguous" if len(candidates) > 1 else "unresolved"
    )
    canonical = next(iter(candidates)) if status == "resolved" else None
    for registration in relevant:
        targets = {
            e["end"]
            for e in edges
            if e["kind"] == "SAME_AS"
            and e["start"] == registration["start"]
            and active_registration(e, as_of)
        }
        if len(targets) > 1:
            status = "ambiguous" if system == "logistics" else "conflict"
            canonical = None
    identities = {key, canonical} | {e["start"] for e in relevant if e["end"] == canonical}
    return {
        "status": status,
        "canonicalId": canonical,
        "evidenceRefs": [e["evidenceId"] for e in relevant],
        "sourceRefs": [
            n["sourceRef"] for n in nodes if n["key"] in identities and n.get("sourceRef")
        ],
    }


class ObjectService:
    def __init__(self, fabric, semantic):
        self.fabric, self.semantic = fabric, semantic

    async def detail(self, system, kind, native_id, graph_version=None, pins=None):
        if system not in self.fabric.sources or kind not in RESOURCE_FIELDS:
            raise ValueError("unknown source/record type")
        snapshots = await self.fabric.capture(pins, allow_partial=True)
        if system not in snapshots:
            raise ValueError("selected source unavailable")
        info = None
        if not graph_version:
            if set(snapshots) != set(self.fabric.sources):
                raise ValueError(
                    "Graph preparation needs complete sources; supply a previous graphVersion for partial live reads"
                )
            refs = {
                s: {
                    k: r[k]
                    for k in (
                        "datasetId",
                        "epochId",
                        "snapshotId",
                        "sequence",
                        "sourceTime",
                        "stableDataHash",
                    )
                }
                for s, r in snapshots.items()
            }
            from semantic_core.knowledge import KnowledgeCatalog

            info = await self.fabric.ensure_graph(refs, KnowledgeCatalog().version)
            graph_version = info["graphVersion"]
        info, nodes, edges = await asyncio.to_thread(self.semantic.model, graph_version)
        selected_key = f"{system}:{'equipment' if kind == 'own-force' else kind}:{native_id}"
        resource, idfield = RESOURCE_FIELDS[kind]
        base = next(
            (
                r
                for r in snapshots[system]["records"].get(resource, [])
                if record_id(r, idfield) == native_id
            ),
            None,
        )
        if base is None:
            raise KeyError(native_id)
        coverage = {s: "complete" if s in snapshots else "unavailable" for s in self.fabric.sources}
        stale = any(
            s not in info["inputSnapshotSet"]
            or any(raw[k] != info["inputSnapshotSet"][s][k] for k in ("datasetId", "epochId"))
            or raw["stableDataHash"] != info["inputStableHashes"][s]
            for s, raw in snapshots.items()
        )
        identity = resolve_identity(
            nodes, edges, system, kind, native_id, snapshots[system]["sourceTime"]
        )
        selected = {selected_key}
        links = []
        truncated = False
        if not stale and identity["status"] == "resolved":
            if identity["canonicalId"]:
                selected.add(identity["canonicalId"])
            frontier = set(selected)
            for depth in range(7):
                following = set()
                for edge in edges:
                    outward = (
                        edge["kind"]
                        in {
                            "SAME_AS",
                            "REFERS_TO",
                            "REQUIRES",
                            "ASSIGNED_TO",
                            "SUBORDINATE_TO",
                            "FULFILLED_BY",
                            "RESERVES",
                            "CARRIED_BY",
                            "CONTAINS_PART",
                        }
                        and edge["start"] in frontier
                    )
                    inward = (
                        edge["kind"]
                        in {"SAME_AS", "REFERS_TO", "MAINTAINS", "STOCK_OF", "FOR_WORK"}
                        and edge["end"] in frontier
                    )
                    if edge["kind"] == "REFERS_TO" and not edge["start"].startswith(
                        "knccs:contact:"
                    ):
                        continue
                    if edge["kind"] == "SAME_AS" and not active_registration(
                        edge, snapshots[system]["sourceTime"]
                    ):
                        continue
                    if outward or inward:
                        target = edge["end"] if outward else edge["start"]
                        if edge not in links:
                            links.append(edge)
                        if target not in selected:
                            following.add(target)
                capacity = 200 - len(selected)
                if len(following) > capacity:
                    following = set(sorted(following)[:capacity])
                    truncated = True
                selected.update(following)
                frontier = following
                if depth == 6 and frontier:
                    truncated = True
                if not frontier or len(selected) >= 200:
                    break
        valid_links = [e for e in links if e["start"] in selected and e["end"] in selected]
        if len(valid_links) > 300:
            truncated = True
        links = valid_links[:300]
        records = []
        for n in nodes:
            if n["key"] not in selected or not n.get("sourceRef"):
                continue
            ref = n["sourceRef"]
            s = ref["systemId"]
            record_type = ref["recordType"]
            if s not in snapshots or record_type not in RESOURCE_FIELDS:
                continue
            resource, idfield = (
                ("own-forces", "pennant")
                if s == "knccs" and record_type == "equipment"
                else ("formations", "formationRef")
                if s == "knccs" and record_type == "unit"
                else RESOURCE_FIELDS[record_type]
            )
            row = next(
                (
                    r
                    for r in snapshots[s]["records"].get(resource, [])
                    if record_id(r, idfield) == ref["nativeId"]
                ),
                None,
            )
            if row is None:
                continue
            records.append(
                {
                    "systemId": s,
                    "recordType": record_type,
                    "nativeId": ref["nativeId"],
                    "sourceRef": {
                        **ref,
                        "datasetId": snapshots[s]["datasetId"],
                        "epochId": snapshots[s]["epochId"],
                    },
                    "record": row,
                    "sourceTime": snapshots[s]["sourceTime"],
                    "recordUpdatedAt": row.get("updatedAt"),
                    "lastReceivedAt": getattr(self.fabric, "received", {}).get(s),
                    "snapshotId": snapshots[s]["snapshotId"],
                }
            )
        if not records:
            records = [
                {
                    "systemId": system,
                    "recordType": kind,
                    "nativeId": native_id,
                    "record": base,
                    "sourceTime": snapshots[system]["sourceTime"],
                    "lastReceivedAt": getattr(self.fabric, "received", {}).get(system),
                    "snapshotId": snapshots[system]["snapshotId"],
                }
            ]
        result = {
            "identityStatus": "stale" if stale else identity["status"],
            "canonicalId": None if stale else identity["canonicalId"],
            "graphVersion": graph_version,
            "stale": stale,
            "sourceSnapshotSet": {
                s: {
                    k: r[k]
                    for k in (
                        "datasetId",
                        "epochId",
                        "snapshotId",
                        "sequence",
                        "sourceTime",
                        "stableDataHash",
                    )
                    if k in r
                }
                for s, r in snapshots.items()
            },
            "knowledgeSetVersion": info.get("knowledgeSetVersion"),
            "knowledgeSetHash": info.get("knowledgeSetHash"),
            "adapterVersion": info.get("mappingVersion"),
            "records": records,
            "links": [] if stale else links,
            "coverage": coverage,
            "partial": truncated or any(v != "complete" for v in coverage.values()),
            "graphCompleteness": "partial" if truncated else "complete",
            "limits": {"nodes": 200, "links": 300, "depth": 7},
            "displayOnly": True,
        }

        try:
            from semantic_core.business import business_summary
            from semantic_core.metadata import MetadataCatalog

            metadata = MetadataCatalog(info["knowledgeSetVersion"])
            result["metadata"] = metadata.public()
            result["business"] = (
                business_summary(records, metadata, system, kind, native_id)
                if not stale and identity["status"] == "resolved"
                else None
            )
        except KeyError:
            result["metadata"] = {"available": False, "fields": []}
            result["business"] = None
        return result
