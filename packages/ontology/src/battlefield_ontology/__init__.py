"""Explicit synthetic domain contracts; no service, graph or LLM dependencies."""

import hashlib
import json
import math
from collections import defaultdict
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

ONTOLOGY_VERSION = "2.0.0"
MAPPING_VERSION = "2.0.0"
RESOLUTION_VERSION = "1.0.0"


class Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False
    )

    def public(self):
        return self.model_dump(mode="json", by_alias=True)


class SourceRef(Model):
    system_id: Literal["atcis", "knccs", "logistics"]
    dataset_id: str = Field(min_length=1)
    epoch_id: str = Field(min_length=1)
    record_type: Literal["unit", "equipment"]
    native_id: str = Field(min_length=1)

    @property
    def key(self):
        # JSON tuple encoding avoids collisions when source IDs contain delimiters.
        return json.dumps(
            [self.system_id, self.dataset_id, self.epoch_id, self.record_type, self.native_id],
            ensure_ascii=False,
            separators=(",", ":"),
        )


class RelationType(StrEnum):
    SUBORDINATE_TO = "SUBORDINATE_TO"
    ASSIGNED_TO = "ASSIGNED_TO"
    REFERS_TO = "REFERS_TO"
    FROM_SYSTEM = "FROM_SYSTEM"
    OBSERVES = "OBSERVES"


class System(Model):
    system_id: Literal["atcis", "knccs", "logistics"]
    name: str = Field(min_length=1)
    synthetic: Literal[True] = True


class Unit(Model):
    canonical_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source_ref: SourceRef
    parent_id: str | None = None


class Observation(Model):
    observation_id: str = Field(min_length=1)
    assertion_type: RelationType
    source_refs: list[SourceRef] = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    payload_hash: str = Field(min_length=1)


class SnapshotRef(Model):
    dataset_id: str = Field(min_length=1)
    epoch_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    source_time: str
    stable_data_hash: str = Field(min_length=1)


class SourceSnapshotSet(Model):
    atcis: SnapshotRef
    knccs: SnapshotRef


class SourceSnapshotSetV5(SourceSnapshotSet):
    logistics: SnapshotRef


class Equipment(Model):
    native_id: str = Field(min_length=1)
    unit_id: str | None = None
    assignment_role: Literal["assigned", "shared_support"] = "assigned"
    kind: Literal[
        "tank", "armored_vehicle", "support_vehicle", "uav", "naval_vessel", "unknown"
    ] = "unknown"
    availability: Literal["available", "unavailable", "unknown"] = "unknown"
    affiliation: Literal["friendly", "hostile", "unknown"] = "unknown"
    exercise_asset_ref: str | None = None
    position: dict[str, float] | None = None
    velocity: dict[str, float] = Field(default_factory=lambda: {"eastMps": 0.0, "northMps": 0.0})
    observed_at: str | None = None
    warnings: list[str] = Field(default_factory=list)


def normalize_equipment(system_id: str, raw: dict) -> Equipment:
    warnings = []
    if system_id == "atcis":
        native_id, unit_id = raw["trackKey"], raw.get("ownerUnitCode")
        kind = {
            "TANK": "tank",
            "APC": "armored_vehicle",
            "SUPPORT": "support_vehicle",
            "UAV": "uav",
        }.get(raw.get("classCode", ""), "unknown")
        availability = {"R": "available", "N": "unavailable", "U": "unknown"}.get(
            raw.get("readyCode", ""), "unknown"
        )
        affiliation = {"F": "friendly", "H": "hostile", "X": "unknown"}.get(
            raw.get("sideCode", ""), "unknown"
        )
        pos = raw.get("pos")
        if pos is not None and (not isinstance(pos, dict) or set(pos) != {"lon", "lat"}):
            raise ValueError("invalid position fields")
        position = {"longitude": pos["lon"], "latitude": pos["lat"]} if pos else None
        velocity = raw.get("velocity", {"eastMps": 0, "northMps": 0})
        observed_at = raw.get("observedAt")
    elif system_id == "knccs":
        native_id, unit_id = raw["contactNo"], raw.get("orgRef")
        kind = "naval_vessel" if raw.get("platformCategory") == "SURFACE" else "unknown"
        if raw.get("platformCategory") == "AIR" and raw.get("aircraftType") == "UNMANNED":
            kind = "uav"
        availability = {
            "READY": "available",
            "NOT_READY": "unavailable",
            "UNCONFIRMED": "unknown",
        }.get(raw.get("serviceability", ""), "unknown")
        affiliation = {"FRIEND": "friendly", "HOSTILE": "hostile", "UNKNOWN": "unknown"}.get(
            raw.get("identity", ""), "unknown"
        )
        position = raw.get("geo")
        motion = raw.get("motion", {"courseDeg": 0, "speedKnots": 0})
        speed, course = float(motion["speedKnots"]) * 1852 / 3600, float(motion["courseDeg"])
        if (
            not math.isfinite(speed)
            or speed < 0
            or not math.isfinite(course)
            or not 0 <= course < 360
        ):
            raise ValueError("invalid motion")
        angle = math.radians(course)
        velocity = {"eastMps": speed * math.sin(angle), "northMps": speed * math.cos(angle)}
        observed_at = raw.get("reportTime")
    else:
        raise ValueError("untrusted source system")
    if position is not None and (
        not isinstance(position, dict) or set(position) != {"longitude", "latitude"}
    ):
        raise ValueError("invalid position fields")
    if position:
        lon, lat = float(position["longitude"]), float(position["latitude"])
        if (
            not math.isfinite(lon)
            or not math.isfinite(lat)
            or not (-180 <= lon <= 180 and -85 <= lat <= 85)
        ):
            raise ValueError("invalid position")
        position = {"longitude": lon, "latitude": lat}
    if not isinstance(velocity, dict) or set(velocity) != {"eastMps", "northMps"}:
        raise ValueError("invalid velocity fields")
    if any(not math.isfinite(float(v)) or abs(float(v)) > 200 for v in velocity.values()):
        raise ValueError("invalid velocity")
    if kind == "unknown":
        warnings.append("unmapped equipment type")
    return Equipment.model_validate(
        {
            "nativeId": native_id,
            "unitId": unit_id,
            "assignmentRole": raw.get("assignmentRole", "assigned"),
            "kind": kind,
            "availability": availability,
            "affiliation": affiliation,
            "exerciseAssetRef": raw.get("exerciseAssetRef"),
            "position": position,
            "velocity": velocity,
            "observedAt": observed_at,
            "warnings": warnings,
        }
    )


def stable_payload(export: dict) -> dict:
    """Whitelist stable fields, never hash observation time or live movement/state."""
    if export.get("sourceSchemaVersion") in ("3.0.0", "4.0.0", "5.0.0"):
        return {
            k: export[k]
            for k in ("systemId", "datasetId", "epochId", "sourceSchemaVersion", "records")
        }
    units = [{k: u.get(k) for k in ("unitId", "name", "parentId")} for u in export["units"]]
    equipment = [
        {k: e.get(k) for k in ("nativeId", "unitId", "kind", "exerciseAssetRef")}
        | ({"assignmentRole": e["assignmentRole"]} if e.get("assignmentRole") is not None else {})
        for e in export["equipment"]
    ]
    return {
        "systemId": export["systemId"],
        "datasetId": export["datasetId"],
        "epochId": export["epochId"],
        "units": sorted(units, key=lambda u: u["unitId"]),
        "equipment": sorted(equipment, key=lambda e: e["nativeId"]),
    }


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def stable_hash(export: dict) -> str:
    return digest(stable_payload(export))


def resolve_identity(records: list[dict]) -> dict:
    refs = [
        {k: r.get(k) for k in ("systemId", "datasetId", "epochId", "nativeId")} for r in records
    ]
    result = {
        "status": "unresolved",
        "canonicalId": None,
        "sourceRefs": refs,
        "ruleId": None,
        "ruleVersion": RESOLUTION_VERSION,
    }
    if not records or any(not r.get("exerciseAssetRef") for r in records):
        return result
    identities = {(r["datasetId"], r["exerciseAssetRef"]) for r in records}
    if (
        len(identities) != 1
        or len({r["kind"] for r in records}) != 1
        or records[0]["kind"] == "unknown"
        or len({r["systemId"] for r in records}) != len(records)
    ):
        return {**result, "status": "conflict"}
    return {
        **result,
        "status": "resolved",
        "canonicalId": records[0]["exerciseAssetRef"],
        "ruleId": "ER-EXERCISE-ID",
    }


def build_model(sources: dict) -> dict:
    """Validated in-memory model. Transient observations are NOT graph properties."""
    units, groups = {}, defaultdict(list)
    seen_records = set()
    if len({s["datasetId"] for s in sources.values()}) != 1:
        raise ValueError("dataset mismatch")
    for system, source in sources.items():
        System.model_validate({"systemId": system, "name": f"Mock {system.upper()}"})
        for unit in source["units"]:
            uid = f"{system}:{unit['unitId']}"
            if uid in units:
                raise ValueError("duplicate unit")
            units[uid] = {
                **unit,
                "canonicalId": uid,
                "parentId": f"{system}:{unit['parentId']}" if unit.get("parentId") else None,
                "sourceRef": SourceRef(
                    system_id=system,
                    dataset_id=source["datasetId"],
                    epoch_id=source["epochId"],
                    record_type="unit",
                    native_id=unit["unitId"],
                ).public(),
            }
            Unit.model_validate(
                {k: units[uid][k] for k in ("canonicalId", "name", "sourceRef", "parentId")}
            )
        for equipment in source["equipment"]:
            ref = SourceRef(
                system_id=system,
                dataset_id=source["datasetId"],
                epoch_id=source["epochId"],
                record_type="equipment",
                native_id=equipment["nativeId"],
            )
            if ref.key in seen_records:
                raise ValueError("duplicate native equipment record")
            seen_records.add(ref.key)
            record = {**equipment, **ref.public(), "sourceRecordKey": ref.key}
            group = equipment.get("exerciseAssetRef") or f"source:{ref.key}"
            groups[group].append(record)
    for uid in units:
        visited = set()
        current = uid
        while current:
            if current in visited:
                raise ValueError("organization cycle")
            if current not in units:
                raise ValueError("missing parent unit")
            visited.add(current)
            current = units[current]["parentId"]
    resolved = []
    for group, records in sorted(groups.items()):
        identity = resolve_identity(records)
        # A conflicting identifier is not a canonical merge. Preserve separate records.
        batches = [records] if identity["status"] == "resolved" else [[r] for r in records]
        for batch in batches:
            assignments = []
            for record in batch:
                if record.get("unitId"):
                    unit_id = f"{record['systemId']}:{record['unitId']}"
                    if unit_id not in units:
                        raise ValueError("missing assigned unit")
                    assignments.append(
                        {
                            "unitId": unit_id,
                            "ruleId": "MAP-OWNER-UNIT",
                            "ruleVersion": MAPPING_VERSION,
                            "assignmentRole": record.get("assignmentRole", "assigned"),
                            "sourceRefs": [record["sourceRecordKey"]],
                        }
                    )
            canonical_id = (
                group
                if identity["status"] == "resolved"
                else f"source:{batch[0]['sourceRecordKey']}"
            )
            resolved.append(
                {
                    "canonicalId": canonical_id,
                    "kind": batch[0]["kind"],
                    "identity": identity,
                    "assignments": assignments,
                    "observations": batch,
                }
            )
    return {
        "units": list(units.values()),
        "equipment": resolved,
        "ontologyVersion": ONTOLOGY_VERSION,
        "mappingVersion": MAPPING_VERSION,
        "resolutionRuleVersion": RESOLUTION_VERSION,
    }


def unit_scope(model: dict, term: str, max_depth: int = 8) -> dict:
    candidates = [u for u in model["units"] if term in (u["canonicalId"], u["name"], u["unitId"])]
    if len(candidates) != 1:
        return {
            "status": "ambiguous" if candidates else "unresolved",
            "candidates": candidates,
            "unitIds": [],
        }
    selected = {candidates[0]["canonicalId"]}
    paths: list[dict] = []
    frontier = set(selected)
    for _ in range(max_depth):
        children = [u for u in model["units"] if u["parentId"] in frontier]
        frontier = {u["canonicalId"] for u in children}
        if not frontier:
            break
        selected.update(frontier)
        paths.extend(
            {
                "child": u["canonicalId"],
                "parent": u["parentId"],
                "sourceRef": u["sourceRef"],
                "ruleId": "MAP-PARENT-UNIT",
                "ruleVersion": MAPPING_VERSION,
            }
            for u in children
        )
    complete = not any(u["parentId"] in frontier for u in model["units"])
    return {"status": "resolved", "unitIds": sorted(selected), "paths": paths, "complete": complete}
