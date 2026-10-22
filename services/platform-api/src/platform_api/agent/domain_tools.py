"""V3 run-scoped tools: discovery and arithmetic over returned evidence only."""

import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from battlefield_ontology import digest
from c4i_contracts import Model
from platform_api.agent.multi_tools import AggregateArgs, MultiToolRunner
from platform_api.mcp.schema import native_definition
from platform_contracts.models import strict_schema
from pydantic import Field

NATIVE_TOOLS = {
    "get_snapshot",
    "list_units",
    "list_equipment",
    "list_relations",
    "list_reports",
    "list_journal",
    "list_activities",
    "list_documents",
    "list_formations",
    "list_own_forces",
    "list_contacts",
    "list_tracks",
    "list_associations",
    "list_messages",
    "list_delivery_events",
}
SEMANTIC_TOOLS = {
    "interpret_concept",
    "resolve_unit_scope",
    "find_equipment_refs",
    "resolve_entity",
    "get_semantic_evidence",
    "query_relations",
    "get_procedure_definition",
}


def evaluate_condition(condition, record, depth=0):
    if depth > 8:
        raise ValueError("condition depth exceeded")
    op = condition["op"]
    if op in ("AND", "OR"):
        args = condition.get("args", [])
        if not args or len(args) > 20:
            raise ValueError("invalid condition arity")
        values = [evaluate_condition(c, record, depth + 1) for c in args]
        if op == "AND":
            return False if False in values else None if None in values else True
        return True if True in values else None if None in values else False
    if op not in ("EQ", "EXISTS", "BEFORE"):
        raise ValueError("unsupported condition operation")
    value = record.get(condition["field"])
    if op == "EXISTS":
        return True if value is not None else None
    if value is None:
        return None
    if op == "EQ":
        return value == condition["value"]
    return datetime.fromisoformat(value) < datetime.fromisoformat(condition["value"])


def classify(definition, row):
    if "typeField" in definition and "values" in definition:
        return definition["values"].get(row.get(definition["typeField"]), "unknown")
    for case in definition.get("cases", []):
        if evaluate_condition(case, row) is True:
            return case["result"]
    return definition.get("default", "unknown")


def rows(evidence):
    return evidence["data"].get("items", evidence["data"].get("payload", []))


def native_id(row):
    return row.get("equipmentId", row.get("pennant", row.get("activityId", digest(row))))


class EvaluateArgs(Model):
    evidence_ids: list[str] = Field(min_length=1, max_length=40)
    rule_evidence_id: str
    rule_id: str


class DomainAggregateArgs(AggregateArgs):
    group_by: str | None = Field(
        default=None,
        description="OFF: exact native field only. ON: kind, status, or kind,status from Semantic-proven classification; no native filters.",
    )
    evaluation_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    policy: str = "P1"


def definition(name, model, description):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": strict_schema(model.model_json_schema(by_alias=True)),
    }


class DomainToolRunner(MultiToolRunner):
    def __init__(self, clients, snapshots, mode, graph_info=None):
        super().__init__(clients, snapshots, mode, graph_info)
        self.snapshot["semanticPolicyVersion"] = "3-domain-native-off"
        self.definitions = [d for d in self.definitions if d["name"] == "read_evidence"]
        self.definitions.append(
            definition(
                "aggregate_evidence",
                DomainAggregateArgs,
                "Count complete current-run native equipment/own-force pages. OFF: raw native records only with optional native groupBy/filters. ON semantic count: identityEvidenceIds from find_equipment_refs, scopeEvidenceIds from resolve_unit_scope, conceptEvidenceIds containing FORCE-SCOPE/AGGREGATION-POLICY rules, evaluationEvidenceIds from evaluate_evidence for all registered source refs. Follow every source and semantic page first. Returns inclusion/exclusion, unique asset counts, unchanged status counts and selected P1/P2 policy. No hidden mapping or identity inference.",
            )
        )
        if mode == "on":
            self.definitions.append(
                definition(
                    "evaluate_evidence",
                    EvaluateArgs,
                    "Apply one returned Semantic rule to current-run native pages in evidenceIds. ruleEvidenceId must be an interpret_concept/get_procedure_definition evidenceId containing ruleId. State classification and procedure condition evaluation are distinct results. Include original reports with activities for procedure evidence. Missing inputs remain unknown. No arbitrary code or source access.",
                )
            )

    async def prepare(self):
        if self.prepared:
            return
        errors = [
            s + ": snapshot unavailable" for s in ("atcis", "knccs") if s not in self.snapshots
        ]
        async with asyncio.timeout(20):
            for system, client in self.clients.items():
                try:
                    definitions = await client.list_tools()
                    allowed = SEMANTIC_TOOLS if system == "semantic" else NATIVE_TOOLS
                    for item in definitions:
                        if item["name"] not in allowed:
                            continue
                        name = system + "__" + item["name"]
                        self.registry[name] = {
                            "serverId": system,
                            "originalName": item["name"],
                            "definition": item,
                        }
                        self.definitions.append(native_definition({**item, "name": name}))
                except Exception as exc:  # noqa: BLE001 - record discovery failure per server
                    errors.append(system + ": " + type(exc).__name__)
        missing = set(self.snapshots) - self.clients.keys()
        if missing:
            errors.append("MCP unavailable: " + ",".join(sorted(missing)))
        self.discovery_error = "; ".join(errors) or None
        self.registry_hash = digest(self.definitions)
        self.prepared = True

    def put(self, name, arguments, data):
        evidence = {
            "evidenceId": "ev-" + uuid4().hex[:16],
            "tool": name,
            "systemId": "computed",
            "originalTool": name,
            "arguments": arguments,
            "data": data,
        }
        self.evidence[evidence["evidenceId"]] = evidence
        return evidence

    async def execute(self, name, arguments):
        await self.prepare()
        if name == "evaluate_evidence":
            if self.mode == "off":
                raise ValueError("semantic evaluation forbidden in off mode")
            args = EvaluateArgs.model_validate(arguments)
            inputs = self.require_evidence(args.evidence_ids)
            rule_evidence = self.require_evidence([args.rule_evidence_id])[0]
            if rule_evidence["systemId"] != "semantic":
                raise ValueError("Semantic rule evidence required")
            rules = [
                r for r in rule_evidence["data"].get("rules", []) if r["ruleId"] == args.rule_id
            ]
            if len(rules) != 1:
                raise ValueError("rule not found in queried evidence")
            rule = rules[0]
            result = []
            report_ids = {
                r.get("reportId")
                for e in inputs
                if e["originalTool"] == "list_reports"
                for r in rows(e)
            }
            for evidence in inputs:
                if evidence["systemId"] != rule["systemId"]:
                    continue
                for row in rows(evidence):
                    if "cases" in rule["definition"] or "typeField" in rule["definition"]:
                        if evidence["originalTool"] not in ("list_equipment", "list_own_forces"):
                            continue
                        value = classify(rule["definition"], row)
                    elif "condition" in rule["definition"]:
                        if evidence["originalTool"] != "list_activities":
                            continue
                        outcome = evaluate_condition(rule["definition"]["condition"], row)
                        value = (
                            "met"
                            if outcome is True
                            else "not_met"
                            if outcome is False
                            else "unknown"
                        )
                        if value == "met" and row.get("evidenceReport") not in report_ids:
                            value = "unknown"
                    else:
                        raise ValueError("rule is not an evaluable condition/classification")
                    result.append(
                        {
                            "systemId": evidence["systemId"],
                            "nativeId": native_id(row),
                            "result": value,
                            "record": row,
                            "inputEvidenceIds": [evidence["evidenceId"]],
                        }
                    )
            return self.put(
                name,
                args.public(),
                {
                    "items": result,
                    "ruleId": rule["ruleId"],
                    "ruleEvidenceId": args.rule_evidence_id,
                    "documentRefs": rule["documentRefs"],
                    "inputEvidenceIds": args.evidence_ids + [args.rule_evidence_id],
                },
            )
        if name == "aggregate_evidence":
            aggregate_args = DomainAggregateArgs.model_validate(arguments)
            return self.put(name, aggregate_args.public(), self.aggregate_domain(aggregate_args))
        result = await super().execute(name, arguments)
        if result["systemId"] in self.snapshots:
            data = result["data"]
            header = data.get("header", {})
            if header and (
                header["snapshotRef"]
                != self.source_snapshot(result["systemId"], result["arguments"])["snapshotId"]
                or header["source"] != result["systemId"]
            ):
                self.evidence.pop(result["evidenceId"], None)
                raise ValueError("native envelope snapshot mismatch")
        return result

    def aggregate_domain(self, args):
        """Count only complete native pages covered by this run's scope/rule proofs."""
        semantic_ids = (
            args.identity_evidence_ids
            + args.scope_evidence_ids
            + args.concept_evidence_ids
            + args.evaluation_evidence_ids
        )
        if self.mode == "off" and (
            semantic_ids or args.unit_ids is not None or args.kind or args.policy != "P1"
        ):
            # Block semantic helpers here too: hiding MCP names alone is insufficient.
            raise ValueError("semantic aggregation forbidden in off mode")
        pages = self.require_evidence(args.evidence_ids)
        native: dict[tuple[str, str], dict] = {}
        groups: dict[tuple, list] = {}
        for e in pages:
            if e["systemId"] not in self.snapshots or e["originalTool"] not in (
                "list_equipment",
                "list_own_forces",
            ):
                raise ValueError("native registered asset list evidence required")
            key = (e["systemId"], e["originalTool"], e["arguments"].get("snapshotId"))
            group = groups.setdefault(key, [])
            group.append(e)
            for row in rows(e):
                rkey = (e["systemId"], native_id(row))
                if rkey in native and native[rkey] != row:
                    raise ValueError("inconsistent native records")
                native[rkey] = row
        for group in groups.values():
            unique = {native_id(r) for e in group for r in rows(e)}
            totals = {
                e["data"].get("total", e["data"].get("header", {}).get("total")) for e in group
            }
            if totals != {len(unique)} or not any(
                e["data"].get("nextOffset", e["data"].get("header", {}).get("continuation")) is None
                for e in group
            ):
                raise ValueError("incomplete native pages")
        if not semantic_ids:
            selected = [
                (s, n, r)
                for (s, n), r in native.items()
                if all(
                    f.system_id not in (None, s) or r.get(f.field) == f.value for f in args.filters
                )
            ]
            raw_counts = (
                Counter(s + ":" + str(r.get(args.group_by, "<missing>")) for s, n, r in selected)
                if args.group_by
                else Counter()
            )
            return {
                "interpretation": "native_records_only",
                "rawRecordCount": len(selected),
                "counts": dict(raw_counts),
                "items": [{"systemId": s, "nativeId": n, "record": r} for s, n, r in selected],
                "coverage": "complete",
                "inputEvidenceIds": args.evidence_ids,
            }
        if args.filters or args.group_by not in (None, "kind", "status", "kind,status"):
            raise ValueError("native filters cannot mix with semantic aggregation")
        identities = self.require_evidence(args.identity_evidence_ids)
        scopes = self.require_evidence(args.scope_evidence_ids)
        concepts = self.require_evidence(args.concept_evidence_ids)
        evaluations = self.require_evidence(args.evaluation_evidence_ids)
        if not identities or not scopes or not concepts or not evaluations:
            raise ValueError("scope, identity, concept and evaluation evidence required")
        if any(
            e["systemId"] != "semantic" or e["originalTool"] != "find_equipment_refs"
            for e in identities
        ) or any(
            e["systemId"] != "semantic"
            or e["originalTool"] != "resolve_unit_scope"
            or e["data"].get("completeness") != "complete"
            or e["data"].get("status") != "resolved"
            for e in scopes
        ):
            raise ValueError("complete semantic scope/reference evidence required")
        supported_units = {u for e in scopes for u in e["data"]["unitIds"]}
        if args.unit_ids is not None and set(args.unit_ids) - supported_units:
            raise ValueError("unsupported scope")
        policy_rules = [
            r
            for e in concepts
            if e["systemId"] == "semantic"
            for r in e["data"].get("rules", [])
            if r["ruleId"] == "AGGREGATION-POLICY-01"
        ]
        if not policy_rules or args.policy not in policy_rules[0]["definition"]:
            raise ValueError("queried aggregation policy required")
        canonical = {}
        reference_groups: dict[str, list] = {}
        required_units = set(args.unit_ids) if args.unit_ids is not None else supported_units
        queried_units = {u for e in identities for u in e["arguments"].get("unitIds", [])}
        if required_units - queried_units or queried_units - supported_units:
            raise ValueError("incomplete semantic scope coverage")
        if args.kind is None and any(e["arguments"].get("kind") for e in identities):
            raise ValueError("filtered kind query cannot prove complete unfiltered coverage")
        for e in identities:
            querykey = digest(
                {k: v for k, v in e["arguments"].items() if k not in ("limit", "cursor")}
            )
            reference_groups.setdefault(querykey, []).append(e)
            for item in e["data"]["items"]:
                cid = item["canonicalId"]
                if cid not in canonical:
                    canonical[cid] = deepcopy(item)
                else:
                    previous = canonical[cid]
                    if (
                        previous["kind"] != item["kind"]
                        or previous["sourceRefs"] != item["sourceRefs"]
                    ):
                        raise ValueError("inconsistent canonical reference evidence")
                    previous["assignments"] = list(
                        {
                            a["evidenceId"]: a
                            for a in previous["assignments"] + item["assignments"]
                        }.values()
                    )
                    previous["evidenceRefs"] = sorted(
                        set(previous["evidenceRefs"] + item["evidenceRefs"])
                    )
        for group in reference_groups.values():
            ids = {i["canonicalId"] for e in group for i in e["data"]["items"]}
            if any(e["data"]["matchedCount"] != len(ids) for e in group) or not any(
                e["data"]["nextCursor"] is None and e["data"].get("complete") is True for e in group
            ):
                raise ValueError("incomplete semantic reference pages")
        states: dict[tuple[str, str], set[str]] = {}
        for e in evaluations:
            if e["systemId"] != "computed" or e["originalTool"] != "evaluate_evidence":
                raise ValueError("current-run evaluated state evidence required")
            for item in e["data"]["items"]:
                if set(item["inputEvidenceIds"]) - set(args.evidence_ids):
                    raise ValueError("state evidence does not correspond to counted native pages")
                rkey = (item["systemId"], item["nativeId"])
                states.setdefault(rkey, set()).add(item["result"])
        counts: Counter[str] = Counter()
        types: Counter[str] = Counter()
        selected_items: list[dict] = []
        used = set()
        type_status: dict[str, Counter[str]] = {}
        for cid, item in canonical.items():
            if args.kind and item["kind"] != args.kind:
                continue
            effective_units = set(args.unit_ids) if args.unit_ids is not None else supported_units
            if not any(a["end"] in effective_units for a in item["assignments"]):
                raise ValueError("reference outside proven scope")
            refs = {(r["systemId"], r["nativeId"]) for r in item["sourceRefs"]}
            if not refs or refs - native.keys() or refs - states.keys():
                raise ValueError("missing native/state coverage")
            statuses = {s for r in refs for s in states[r]}
            if not statuses <= {"available", "limited", "unavailable", "unknown"}:
                raise ValueError("state classification required")
            state = next(iter(statuses)) if len(statuses) == 1 else "conflicting"
            counts[state] += 1
            types[item["kind"]] += 1
            type_status.setdefault(item["kind"], Counter())[state] += 1
            selected_items.append(
                {
                    "canonicalId": cid,
                    "kind": item["kind"],
                    "status": state,
                    "assignments": item["assignments"],
                    "sourceRefs": item["sourceRefs"],
                    "evidenceRefs": item["evidenceRefs"],
                }
            )
            used.update(refs)
        return {
            "interpretation": "semantic_evidence",
            "resolvedUniqueCount": len(selected_items),
            "counts": dict(counts),
            "typeCounts": dict(types),
            "typeStatusCounts": {kind: dict(counts) for kind, counts in type_status.items()},
            "policy": args.policy,
            "policyIncludedCount": sum(
                counts[s] for s in policy_rules[0]["definition"][args.policy]
            ),
            "unit": policy_rules[0]["definition"]["unit"],
            "items": selected_items,
            "excludedNativeIds": [{"systemId": s, "nativeId": n} for s, n in native.keys() - used],
            "coverage": "complete",
            "inputEvidenceIds": args.evidence_ids + semantic_ids,
        }
