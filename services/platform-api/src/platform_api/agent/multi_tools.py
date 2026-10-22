"""Run-scoped capability registry. Knowledge is read only through discovered MCP."""

import asyncio
from copy import deepcopy
from typing import Literal
from uuid import uuid4

from battlefield_geo import measure
from battlefield_ontology import SnapshotRef, digest
from c4i_contracts import Model, Position
from platform_api.agent.calculation import ID_FIELDS, native_count, records_from, semantic_count
from platform_api.agent.tools import LOCAL_TOOL_DEFINITIONS, EvidenceArgs, GeoArgs
from platform_api.mcp.schema import native_definition, normalize_arguments
from platform_contracts.models import strict_schema
from pydantic import Field

SOURCE_TOOLS = frozenset(
    {
        "get_snapshot",
        "list_equipment",
        "get_equipment",
        "summarize_equipment",
        "get_changes",
        "list_events",
        "list_equipment_history",
        "list_units",
        "list_unit_relations",
        "list_assignments",
        "list_identity_records",
    }
)
SEMANTIC_TOOLS = frozenset(
    {
        "interpret_concept",
        "resolve_unit_scope",
        "find_equipment_refs",
        "resolve_entity",
        "get_semantic_evidence",
    }
)


class NativeFilter(Model):
    system_id: Literal["atcis", "knccs"] | None = None
    field: str
    value: str


class AggregateArgs(Model):
    evidence_ids: list[str] = Field(min_length=1, max_length=40)
    identity_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    scope_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    unit_ids: list[str] | None = None
    kind: str | None = None
    concept_evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    group_by: str | None = None
    filters: list[NativeFilter] = Field(default_factory=list, max_length=20)


AGGREGATE_TOOL = {
    "type": "function",
    "name": "aggregate_evidence",
    "description": "Count complete current-run list_equipment evidence. NATIVE calculation (both modes): evidenceIds plus optional groupBy native field and filters [{systemId,field,value}], yielding rawRecordCount/counts only; no common state, hierarchy or identity interpretation. OFF cannot use semantic arguments. SEMANTIC calculation (ON only): identityEvidenceIds from semantic find_equipment_refs/resolve_entity, conceptEvidenceIds from semantic interpret_concept (sourceMappings), scopeEvidenceIds from semantic resolve_unit_scope with optional unitIds and kind. Reads live source observations for EVERY returned sourceRef; follows all pages. Only Semantic evidence supplies canonical groups and code interpretation. Raw identity records are not resolved identity proofs. Never mix native filters/groupBy with semantic aggregation.",
    "strict": True,
    "parameters": strict_schema(AggregateArgs.model_json_schema(by_alias=True)),
}


class MultiToolRunner:
    def __init__(self, clients, snapshots, mode, graph_info=None):
        if mode not in ("off", "on"):
            raise ValueError("invalid semantic mode")
        if not snapshots or set(snapshots) - {"atcis", "knccs"}:
            raise ValueError("source snapshots required")
        self.snapshots = {s: SnapshotRef.model_validate(r).public() for s, r in snapshots.items()}
        self.mode, self.graph_info = mode, graph_info
        self.historical_snapshots: dict[str, dict] = {}
        if mode == "on" and (
            not graph_info
            or graph_info.get("status") != "READY"
            or graph_info.get("inputStableHashes")
            != {s: r["stableDataHash"] for s, r in self.snapshots.items()}
        ):
            raise ValueError("graph does not correspond to source snapshots")
        allowed = set(self.snapshots) | ({"semantic"} if mode == "on" else set())
        self.clients = {s: c for s, c in clients.items() if s in allowed}
        self.snapshot = {
            "semanticMode": mode,
            "semanticPolicyVersion": "2-native-off",
            "calculationBoundary": "native source fields only; no shared semantic interpretation"
            if mode == "off"
            else "interpretation requires Semantic MCP evidence",
            "sourceSnapshotSet": self.snapshots,
            "graphVersion": graph_info["graphVersion"] if mode == "on" else None,
        }
        self.evidence: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.registry: dict[str, dict] = {}
        self.definitions = deepcopy(LOCAL_TOOL_DEFINITIONS) + [deepcopy(AGGREGATE_TOOL)]
        self.definitions[0]["description"] = (
            "Reread an evidenceId already returned by a successful tool in THIS run. Prerequisite: existing evidence. Cannot fetch C4I records or create evidence. Never invent an ID or use snapshotId as evidenceId. If no evidence exists, use an appropriate source MCP query. Returns the original evidence unchanged."
        )
        self.definitions[1]["description"] = (
            "Measure WGS84 distanceMeters and bearingDegrees between two native equipment IDs in the SAME current-run list_equipment evidence. Requires evidenceId, firstEntityId, secondEntityId and valid native coordinates. Does not infer equipment type, state, organization or identity."
        )
        self.discovery_error = None
        self.prepared = False

    async def prepare(self):
        if self.prepared:
            return
        errors = [
            s + ": snapshot unavailable" for s in ("atcis", "knccs") if s not in self.snapshots
        ]
        try:
            async with asyncio.timeout(10):
                for system, client in self.clients.items():
                    try:
                        async with asyncio.timeout(5):
                            definitions = await client.list_tools()
                        allowed = SEMANTIC_TOOLS if system == "semantic" else SOURCE_TOOLS
                        names, registry, native = set(), {}, []
                        for definition in definitions:
                            original = definition["name"]
                            if original not in allowed:
                                continue
                            if original in names:
                                raise ValueError("duplicate MCP definition")
                            names.add(original)
                            name = system + "__" + original
                            transformed = {**definition, "name": name}
                            native.append(native_definition(transformed))
                            registry[name] = {
                                "serverId": system,
                                "originalName": original,
                                "definition": definition,
                            }
                        self.registry.update(registry)
                        self.definitions.extend(native)
                    except Exception as exc:  # noqa: BLE001 - capability discovery boundary
                        errors.append(f"{system}: {type(exc).__name__}")
        except TimeoutError:
            errors.append("total discovery deadline exceeded")
        self.discovery_error = "; ".join(errors) or None
        self.registry_hash = digest(self.definitions)
        self.prepared = True

    def require_evidence(self, ids):
        if any(eid not in self.evidence for eid in ids):
            raise ValueError(
                "evidence_not_found; snapshotId is not evidenceId; availableCurrentRunEvidenceIds="
                + str(list(self.evidence))
                + "; obtain source tool evidence before rereading"
            )
        return [self.evidence[eid] for eid in ids]

    def source_snapshot(self, system, arguments):
        current = self.snapshots[system]
        requested = arguments.get("snapshotId")
        historical = getattr(self, "historical_snapshots", {}).get(system)
        if historical and requested == historical["snapshotId"]:
            return historical
        if requested not in (None, current["snapshotId"]):
            raise ValueError("snapshot_mismatch")
        return current

    async def execute(self, name, arguments):
        await self.prepare()
        args: EvidenceArgs | GeoArgs | AggregateArgs
        if name == "read_evidence":
            args = EvidenceArgs.model_validate(arguments)
            return self.require_evidence([args.evidence_id])[0]
        if name == "aggregate_evidence":
            args = AggregateArgs.model_validate(arguments)
            data = self.aggregate(args)
            system, args_dict = "computed", args.public()
        elif name == "geo_measure":
            args = GeoArgs.model_validate(arguments)
            evidence = self.require_evidence([args.evidence_id])[0]
            if (
                evidence.get("systemId") not in self.snapshots
                or evidence.get("originalTool") != "list_equipment"
            ):
                raise ValueError("source equipment list evidence required")
            positions = {}
            for row in evidence["data"]["items"]:
                pos = row.get("pos") if evidence["systemId"] == "atcis" else row.get("geo")
                if pos:
                    coordinates = (
                        {"latitude": pos["lat"], "longitude": pos["lon"]}
                        if evidence["systemId"] == "atcis"
                        else pos
                    )
                    positions[row[ID_FIELDS[evidence["systemId"]]]] = Position.model_validate(
                        coordinates
                    )
            if args.first_entity_id not in positions or args.second_entity_id not in positions:
                raise ValueError("objects must be in the same list evidence")
            data = measure(positions[args.first_entity_id], positions[args.second_entity_id]) | {
                "inputEvidenceIds": [args.evidence_id],
                "snapshotId": evidence["data"]["snapshotId"],
            }
            system, args_dict = "computed", args.public()
        else:
            if name not in self.registry:
                raise ValueError("tool_not_allowed")
            binding = self.registry[name]
            system, original = binding["serverId"], binding["originalName"]
            raw = dict(arguments)
            properties = binding["definition"]["inputSchema"].get("properties", {})
            if system == "semantic":
                version = self.graph_info["graphVersion"]
                if raw.get("graphVersion") not in (None, version):
                    raise ValueError("graph_version_mismatch")
                raw["graphVersion"] = version
            else:
                snapshot = self.source_snapshot(system, raw)
                for field in ("snapshotId", "toSnapshotId"):
                    if field in properties:
                        if raw.get(field) not in (None, snapshot["snapshotId"]):
                            raise ValueError("snapshot_mismatch")
                        raw[field] = snapshot["snapshotId"]
                if "epochId" in properties:
                    if raw.get("epochId") not in (None, snapshot["epochId"]):
                        raise ValueError("epoch_mismatch")
                    raw["epochId"] = snapshot["epochId"]
                if "throughSequence" in properties:
                    if (
                        raw.get("throughSequence") is not None
                        and raw["throughSequence"] > snapshot["sequence"]
                    ):
                        raise ValueError("sequence_mismatch")
                    if raw.get("throughSequence") is None:
                        raw["throughSequence"] = snapshot["sequence"]
            args_dict = normalize_arguments(binding["definition"]["inputSchema"], raw)
            data = await self.clients[system].call(original, args_dict)
            if system == "semantic":
                if (
                    data.get("graphVersion") != self.graph_info["graphVersion"]
                    or data.get("inputStableHashes") != self.graph_info["inputStableHashes"]
                ):
                    raise ValueError("response_graph_mismatch")
                for key in ("ontologyVersion", "mappingVersion", "resolutionRuleVersion"):
                    if data.get(key) != self.graph_info.get(key):
                        raise ValueError("response_rule_version_mismatch")
            else:
                snapshot = self.source_snapshot(system, args_dict)
                if (
                    data.get("snapshotId", data.get("toSnapshotId", snapshot["snapshotId"]))
                    != snapshot["snapshotId"]
                    or data.get("epochId", snapshot["epochId"]) != snapshot["epochId"]
                    or data.get("systemId", system) != system
                ):
                    raise ValueError("response_snapshot_mismatch")
                if original in ("list_events", "list_equipment_history") and any(
                    item.get("epochId") != snapshot["epochId"]
                    or item.get("sequence", 0) > args_dict["throughSequence"]
                    for item in data.get("items", [])
                ):
                    raise ValueError("future_event_in_response")
        eid = "ev-" + uuid4().hex[:16]
        evidence = {
            "evidenceId": eid,
            "tool": name,
            "systemId": system,
            "originalTool": self.registry[name]["originalName"] if name in self.registry else name,
            "arguments": args_dict,
            "data": data,
        }
        self.evidence[eid] = evidence
        return evidence

    def aggregate(self, args):
        semantic_inputs = (
            args.identity_evidence_ids + args.scope_evidence_ids + args.concept_evidence_ids
        )
        if self.mode == "off" and (semantic_inputs or args.unit_ids is not None or args.kind):
            raise ValueError("semantic interpretation unavailable in off mode")
        records = records_from(self.require_evidence(args.evidence_ids))
        if not semantic_inputs:
            data = native_count(records, args)
        else:
            if args.filters or args.group_by:
                raise ValueError("native filters cannot be mixed with semantic aggregation")
            data = semantic_count(
                records,
                args,
                self.require_evidence(args.identity_evidence_ids),
                self.require_evidence(args.scope_evidence_ids),
                self.require_evidence(args.concept_evidence_ids),
            )
        return {**data, "inputEvidenceIds": args.evidence_ids + semantic_inputs}
