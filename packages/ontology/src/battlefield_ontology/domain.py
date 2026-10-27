"""Reviewed v3 native adapters and assertions. Never imports source services."""

import json
from datetime import datetime
from pathlib import Path

from battlefield_ontology import digest

DOMAIN_VERSION = "3.0.0"
ADAPTER_VERSION = "3.0.2"


def catalog_hash(version=DOMAIN_VERSION):
    return digest(
        [
            version,
            "4.0.0" if version == "4.0.0" else ADAPTER_VERSION,
            json.loads(Path(__file__).with_name("domain_rules.json").read_text(encoding="utf-8")),
            json.loads(
                Path(__file__).with_name("domain_documents.json").read_text(encoding="utf-8")
            ),
        ]
    )


def build_domain(sources, knowledge_documents=None, knowledge_manifest=None):
    """Apply reviewed mappings to stable exports; never infer identity from proximity/text."""
    reviewed_documents = json.loads(
        Path(__file__).with_name("domain_documents.json").read_text(encoding="utf-8")
    )
    if set(sources) != {"atcis", "knccs"}:
        raise ValueError("complete native source set required")
    domain_version = "4.0.0" if knowledge_manifest else DOMAIN_VERSION
    if any(s.get("sourceSchemaVersion") != domain_version for s in sources.values()):
        raise ValueError("unsupported native schema")
    if {s["datasetId"] for s in sources.values()} != {
        "c2-domain-demo-v4" if knowledge_manifest else "c2-domain-demo-v3"
    }:
        raise ValueError("dataset mismatch")
    nodes, edges, documents = {}, [], {}
    for source in sources.values():
        if source.get("sourceTime"):
            as_of = datetime.fromisoformat(source["sourceTime"])
            for rows in source["records"].values():
                for record in rows:
                    known = record.get("knownAt", record.get("receivedAt"))
                    if known and datetime.fromisoformat(known) > as_of:
                        raise ValueError("future source record beyond snapshot boundary")

    def ref(system, resource, native_id):
        if resource == "document" and knowledge_manifest:
            return {
                "systemId": "fabric",
                "documentKey": system + ":" + native_id,
                "knowledgeSetVersion": knowledge_manifest["knowledgeSetVersion"],
                "datasetId": knowledge_manifest["knowledgeSetVersion"],
                "epochId": knowledge_manifest["knowledgeSetHash"],
                "recordType": "knowledge_document",
                "nativeId": native_id,
            }
        s = sources[system]
        return {
            "systemId": system,
            "datasetId": s["datasetId"],
            "epochId": s["epochId"],
            "recordType": resource,
            "nativeId": native_id,
        }

    def node(system, resource, native_id, label, payload):
        key = f"{system}:{resource}:{native_id}"
        if key in nodes:
            raise ValueError("duplicate native record")
        nodes[key] = {
            "key": key,
            "label": label,
            "sourceRef": ref(system, resource, native_id),
            "payload": payload,
        }
        return key

    for system, source in sources.items():
        for doc in (
            [d["document"] for d in knowledge_documents if d["namespace"] == system]
            if knowledge_documents is not None
            else source["records"]["documents"]
        ):
            if digest({k: v for k, v in doc.items() if k != "hash"}) != doc["hash"]:
                raise ValueError("document hash mismatch")
            if reviewed_documents.get(system, {}).get(doc["documentId"]) != {
                "version": doc["version"],
                "hash": doc["hash"],
            }:
                raise ValueError(
                    "unreviewed document revision; update reviewed mappings explicitly"
                )
            documents[(system, doc["documentId"])] = doc
            node(system, "document", doc["documentId"], "SourceDocument", doc)

    rules = json.loads(Path(__file__).with_name("domain_rules.json").read_text(encoding="utf-8"))
    for rule in rules:
        doc = documents[(rule["systemId"], rule["documentId"])]
        if rule["section"] != doc["section"]:
            raise ValueError("rule document section mismatch")
        rule["version"] = domain_version
        rule["documentRefs"] = [
            {
                **ref(rule["systemId"], "document", rule["documentId"]),
                "version": doc["version"],
                "hash": doc["hash"],
                "section": doc["section"],
            }
        ]
        if knowledge_manifest:
            supplement = next(
                d["document"] for d in knowledge_documents if d["documentKey"] == "fabric:POLICY-01"
            )
            rule["documentRefs"].append(
                {
                    **ref("fabric", "document", "POLICY-01"),
                    "version": supplement["version"],
                    "hash": supplement["hash"],
                    "section": supplement["section"],
                }
            )
        node(rule["systemId"], "rule", rule["ruleId"], "InterpretationRule", rule)
    if knowledge_manifest:
        node("fabric", "document", "POLICY-01", "SourceDocument", supplement)
    rule_map = {r["ruleId"]: r for r in rules}

    def edge(kind, start, end, system, resource, native_id, rule_id, **props):
        rule = rule_map[rule_id]
        body = {
            "kind": kind,
            "start": start,
            "end": end,
            "sourceRefs": [ref(system, resource, native_id)],
            "ruleId": rule_id,
            "ruleVersion": domain_version,
            "documentRefs": rule["documentRefs"],
            **props,
        }
        edges.append({**body, "evidenceId": "assert-" + digest(body)[:32]})

    land, sea = sources["atcis"]["records"], sources["knccs"]["records"]
    for u in land["units"]:
        node("atcis", "unit", u["unitCode"], "Unit", u)
    for u in sea["formations"]:
        node("knccs", "unit", u["formationRef"], "Unit", u)
    for u in land["units"]:
        if u.get("parentCode"):
            edge(
                "SUBORDINATE_TO",
                f"atcis:unit:{u['unitCode']}",
                f"atcis:unit:{u['parentCode']}",
                "atcis",
                "unit",
                u["unitCode"],
                "ORG-ROLE-01",
            )
    for u in sea["formations"]:
        if u.get("superior"):
            edge(
                "SUBORDINATE_TO",
                f"knccs:unit:{u['formationRef']}",
                f"knccs:unit:{u['superior']}",
                "knccs",
                "unit",
                u["formationRef"],
                "FORCE-SCOPE-01",
            )
    for system, rows, id_field, unit_field, type_rule in [
        ("atcis", land["equipment"], "equipmentId", "ownerCode", "ASSET-TYPE-01"),
        ("knccs", sea["own-forces"], "pennant", "formationRef", "ASSET-TYPE-NAVAL-01"),
    ]:
        mapping = rule_map[type_rule]["definition"]
        for row in rows:
            key = node(
                system,
                "equipment",
                row[id_field],
                "Equipment",
                {
                    "kind": mapping["values"].get(row.get(mapping["typeField"]), "unknown"),
                    "native": row,
                },
            )
            edge(
                "ASSIGNED_TO",
                key,
                f"{system}:unit:{row[unit_field]}",
                system,
                "equipment",
                row[id_field],
                "FORCE-SCOPE-01",
                role=row.get("role", "ASSIGNED"),
            )
    for contact in sea["contacts"]:
        native_id = contact["originator"] + "/" + contact["trackNo"]
        node("knccs", "contact", native_id, "ContactObservation", contact)
    for association in sea["associations"]:
        contact = f"knccs:contact:{association['originator']}/{association['trackNo']}"
        equipment = f"{association['refSystem']}:equipment:{association['refEquipment']}"
        if association["documentId"] != "EX-01" or contact not in nodes or equipment not in nodes:
            raise ValueError("invalid explicit association")
        existing = [e for e in edges if e["kind"] == "REFERS_TO" and e["start"] == contact]
        if existing and any(e["end"] != equipment for e in existing):
            raise ValueError("conflicting explicit association")
        edge(
            "REFERS_TO",
            contact,
            equipment,
            "knccs",
            "association",
            association["associationId"],
            "ENTITY-LINK-01",
            knownAt=association["knownAt"],
        )
    for relation in sea["relations"]:
        if relation["role"] == "SUPPORT":
            edge(
                "ASSIGNED_TO",
                relation["from"].replace("atcis:", "atcis:equipment:", 1),
                "knccs:unit:" + relation["to"],
                "knccs",
                "relation",
                relation["id"],
                "FORCE-SCOPE-01",
                role="SUPPORT",
                effectiveFrom=relation["since"],
                effectiveTo=relation["until"],
            )
    node("atcis", "incident", "INC-1", "Incident", {"synthetic": True})
    for system, rows, native_field in [
        ("atcis", land["reports"], "reportId"),
        ("knccs", sea["messages"], "serial"),
    ]:
        for r in rows:
            node(system, "report", r[native_field], "Report", r)
        for r in rows:
            key = f"{system}:report:{r[native_field]}"
            edge(
                "REFERS_TO",
                key,
                "atcis:incident:INC-1",
                system,
                "report",
                r[native_field],
                "REPORT-LINEAGE-01",
            )
            for field, kind in [
                ("derivedFrom", "DERIVED_FROM"),
                ("relayOf", "DERIVED_FROM"),
                ("supersedes", "SUPERSEDES"),
            ]:
                if r.get(field):
                    target = r[field] if ":" in r[field] else system + ":" + r[field]
                    owner, native = target.split(":", 1)
                    edge(
                        kind,
                        key,
                        f"{owner}:report:{native}",
                        system,
                        "report",
                        r[native_field],
                        "REPORT-REVISION-01" if kind == "SUPERSEDES" else "REPORT-LINEAGE-01",
                    )
    for activity in land["activities"]:
        key = node(
            "atcis",
            "activity",
            activity["activityId"],
            "Activity",
            {k: v for k, v in activity.items() if k not in ("state", "evidenceReport")},
        )
        edge(
            "REFERS_TO",
            key,
            "atcis:incident:INC-1",
            "atcis",
            "activity",
            activity["activityId"],
            "ACTIVITY-STEP-01",
        )
    for system in sources:
        node(system, "system", system, "System", {"systemId": system, "synthetic": True})
    for rule in rules:
        if "typeField" in rule["definition"]:
            for kind in sorted(set(rule["definition"]["values"].values())):
                key = "type:" + kind
                if key not in nodes:
                    nodes[key] = {
                        "key": key,
                        "label": "EquipmentType",
                        "payload": {
                            "kind": kind,
                            "ruleId": rule["ruleId"],
                            "documentRefs": rule["documentRefs"],
                        },
                    }
        if "cases" in rule["definition"]:
            for state in {c["result"] for c in rule["definition"]["cases"]} | {
                rule["definition"]["default"]
            }:
                key = "concept:availability:" + state
                nodes.setdefault(
                    key,
                    {
                        "key": key,
                        "label": "ConceptDefinition",
                        "payload": {
                            "concept": "availability",
                            "value": state,
                            "documentRefs": rule["documentRefs"],
                        },
                    },
                )
        if "steps" in rule["definition"]:
            procedure_key = "procedure:" + rule["documentId"]
            nodes[procedure_key] = {"key": procedure_key, "label": "Procedure", "payload": rule}
            for step in rule["definition"]["steps"]:
                key = procedure_key + ":" + step
                nodes[key] = {
                    "key": key,
                    "label": "StepDefinition",
                    "payload": {
                        "stepCode": step,
                        "condition": rule["definition"]["condition"],
                        "documentRefs": rule["documentRefs"],
                    },
                }

    # Source records and assertions are explicit graph objects, distinct from sensors.
    for original in list(nodes.values()):
        if original["label"] not in {
            "Unit",
            "Equipment",
            "ContactObservation",
            "Report",
            "Activity",
            "SourceDocument",
        }:
            continue
        source_ref = original["sourceRef"]
        key = "source-record:" + digest(source_ref)
        nodes[key] = {
            "key": key,
            "label": "SourceRecord",
            "sourceRef": source_ref,
            "payload": {"sourceRef": source_ref, "revision": original["payload"].get("revision")},
        }
        # Mechanical origin mapping is not a doctrine/interpretation assertion.
        body = {
            "kind": "REFERS_TO",
            "start": key,
            "end": original["key"],
            "sourceRefs": [source_ref],
            "provenanceKind": "native_record_reference",
            "adapterVersion": "4.0.0" if knowledge_manifest else ADAPTER_VERSION,
        }
        edges.append({**body, "evidenceId": "assert-" + digest(body)[:32]})
    for assertion in edges:
        key = "assertion:" + assertion["evidenceId"]
        nodes[key] = {"key": key, "label": "Observation", "payload": assertion}
    for e in edges:
        if e["start"] not in nodes or e["end"] not in nodes:
            raise ValueError("missing relation endpoint")
    parents = {e["start"]: e["end"] for e in edges if e["kind"] == "SUBORDINATE_TO"}
    for initial in list(parents):
        key = initial
        seen = set()
        while key in parents:
            if key in seen:
                raise ValueError("organization cycle")
            seen.add(key)
            key = parents[key]
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "rules": rules,
        "ontologyVersion": DOMAIN_VERSION,
    }
