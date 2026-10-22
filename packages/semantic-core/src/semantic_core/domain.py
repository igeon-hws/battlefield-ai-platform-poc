"""V3 graph publication and read service; live values stay at native sources."""

import json
from collections import defaultdict
from datetime import UTC, datetime

from battlefield_ontology import digest
from battlefield_ontology.domain import DOMAIN_VERSION, build_domain, catalog_hash


def publish_domain(repo, sources, graph_version=None):
    """Publish an immutable validated build; READY reuse requires identical semantic inputs."""
    hashes = {
        s: digest(
            {
                k: v
                for k, v in data.items()
                if k not in ("snapshotId", "sequence", "sourceTime", "stableDataHash")
            }
        )
        for s, data in sources.items()
    }
    # Stable data + reviewed catalog identify meaning; position ticks do not force rebuilds.
    fingerprint = digest(
        {"hashes": hashes, "domain": DOMAIN_VERSION, "catalogHash": catalog_hash()}
    )
    version = graph_version or "domain-" + fingerprint[:24]
    inputs = {
        s: {
            k: data.get(k) for k in ("datasetId", "epochId", "snapshotId", "sequence", "sourceTime")
        }
        | {"stableDataHash": hashes[s]}
        for s, data in sources.items()
    }
    with repo.write_lock:
        try:
            existing = repo.build_info(version)
        except KeyError:
            existing = None
        if existing:
            if existing["inputFingerprint"] != fingerprint:
                raise ValueError("immutable graph version inputs")
            if existing["status"] == "READY":
                return existing
        repo.query(
            "MERGE (b:GraphBuild {graphVersion:$v}) SET b.status='BUILDING',b.inputFingerprint=$f,b.inputStableHashesJson=$h,b.inputSnapshotSetJson=$i,b.ontologyVersion=$o,b.mappingVersion=$o,b.resolutionRuleVersion=$o,b.domainCatalogHash=$c,b.builtAt=$t",
            v=version,
            f=fingerprint,
            h=json.dumps(hashes),
            i=json.dumps(inputs),
            o=DOMAIN_VERSION,
            c=catalog_hash(),
            t=datetime.now(UTC).isoformat(),
        )
        try:
            model = build_domain(sources)
            nodes, edges = defaultdict(list), defaultdict(list)
            for n in model["nodes"]:
                nodes[n["label"]].append(
                    {
                        "key": n["key"],
                        "props": {
                            "graphVersion": version,
                            "domainJson": json.dumps(n, ensure_ascii=False),
                        },
                    }
                )
            for e in model["edges"]:
                edges[e["kind"]].append(
                    {
                        "start": e["start"],
                        "end": e["end"],
                        "props": {
                            "assertionId": e["evidenceId"],
                            "domainJson": json.dumps(e, ensure_ascii=False),
                        },
                    }
                )
            with repo.driver.session(database=repo.database) as session:
                session.execute_write(repo._publish, version, nodes, edges, inputs)
        except Exception as exc:
            repo.query(
                "MATCH (b:GraphBuild {graphVersion:$v}) SET b.status='FAILED',b.diagnostic=$d",
                v=version,
                d=str(exc),
            )
            raise
    return repo.build_info(version)


class DomainService:
    def __init__(self, repo):
        self.repo = repo

    def model(self, version):
        info = self.repo.require_ready(version)
        if info["ontologyVersion"] != DOMAIN_VERSION:
            raise ValueError("not a v3 domain build")
        nodes = [
            json.loads(r["body"])
            for r in self.repo.query(
                "MATCH (n:SemanticNode {graphVersion:$v}) WHERE n.domainJson IS NOT NULL RETURN n.domainJson AS body",
                v=version,
            )
        ]
        edges = [
            json.loads(r["body"])
            for r in self.repo.query(
                "MATCH (:SemanticNode {graphVersion:$v})-[r]->(:SemanticNode {graphVersion:$v}) WHERE r.domainJson IS NOT NULL RETURN r.domainJson AS body",
                v=version,
            )
        ]
        return info, nodes, edges

    @staticmethod
    def response(info, **body):
        return {
            **{
                k: info[k]
                for k in (
                    "graphVersion",
                    "ontologyVersion",
                    "mappingVersion",
                    "resolutionRuleVersion",
                    "inputStableHashes",
                )
            },
            "completeness": "complete",
            **body,
        }

    def interpret_concept(self, version, term):
        info, nodes, _ = self.model(version)
        rules = [n["payload"] for n in nodes if n["label"] == "InterpretationRule"]
        supported = [
            "가용",
            "availability",
            "전차",
            "tank",
            "조직",
            "보고",
            "절차",
            "전력",
            "통합",
            "all",
        ]
        selected = rules if term in supported else [r for r in rules if r["ruleId"] == term]
        return self.response(
            info,
            status="resolved" if selected else "unresolved",
            rules=selected,
            supportedTerms=supported,
            evidenceRefs=[r["ruleId"] for r in selected],
        )

    def resolve_unit_scope(self, version, term, max_depth=8):
        if not 0 <= max_depth <= 8:
            raise ValueError("invalid depth")
        info, nodes, edges = self.model(version)
        units = [n for n in nodes if n["label"] == "Unit"]
        matches = [
            n
            for n in units
            if term
            in (
                n["key"],
                n["sourceRef"]["nativeId"],
                n["payload"].get("name"),
                n["payload"].get("previousName"),
                n["payload"].get("designation"),
            )
        ]
        if len(matches) != 1:
            return self.response(
                info,
                status="ambiguous" if matches else "unresolved",
                candidates=matches,
                unitIds=[],
                paths=[],
            )
        ids, paths = {matches[0]["key"]}, []
        for _ in range(max_depth):
            found = [
                e
                for e in edges
                if e["kind"] == "SUBORDINATE_TO" and e["end"] in ids and e["start"] not in ids
            ]
            if not found:
                break
            paths.extend(found)
            ids.update(e["start"] for e in found)
        complete = not any(
            e["kind"] == "SUBORDINATE_TO" and e["end"] in ids and e["start"] not in ids
            for e in edges
        )
        return self.response(
            info,
            status="resolved",
            unitIds=sorted(ids),
            paths=paths,
            completeness="complete" if complete else "partial",
        )

    def find_equipment_refs(self, version, unit_ids, kind=None, limit=100, cursor=0):
        # Live status is deliberately absent: source MCP supplies the run's state snapshot.
        if not 1 <= limit <= 100 or cursor < 0:
            raise ValueError("invalid pagination")
        info, nodes, edges = self.model(version)
        scope = set(unit_ids)
        rules = {
            n["payload"]["ruleId"]: n["payload"]
            for n in nodes
            if n["label"] == "InterpretationRule"
        }
        included = rules["FORCE-SCOPE-01"]["definition"]["includedRoles"]
        as_of = (
            min(
                datetime.fromisoformat(r["sourceTime"])
                for r in info["inputSnapshotSet"].values()
                if r.get("sourceTime")
            )
            if any(r.get("sourceTime") for r in info["inputSnapshotSet"].values())
            else None
        )
        eligible = [
            e
            for e in edges
            if e["kind"] == "ASSIGNED_TO"
            and e["end"] in scope
            and e.get("role") in included
            and (
                not as_of
                or (
                    not e.get("effectiveFrom")
                    or datetime.fromisoformat(e["effectiveFrom"]) <= as_of
                )
                and (not e.get("effectiveTo") or as_of < datetime.fromisoformat(e["effectiveTo"]))
            )
        ]
        items = []
        for n in nodes:
            assigned = [e for e in eligible if e["start"] == n["key"]]
            if n["label"] != "Equipment" or not assigned or kind and n["payload"]["kind"] != kind:
                continue
            observations = [
                e
                for e in edges
                if e["kind"] == "REFERS_TO"
                and e["end"] == n["key"]
                and e["start"].startswith("knccs:contact:")
            ]
            items.append(
                {
                    "canonicalId": n["key"],
                    "kind": n["payload"]["kind"],
                    "identityStatus": "resolved",
                    "sourceRefs": [n["sourceRef"]],
                    "observationRefs": [e["sourceRefs"] for e in observations],
                    "assignments": assigned,
                    "evidenceRefs": [e["evidenceId"] for e in assigned + observations],
                }
            )
        items.sort(key=lambda i: i["canonicalId"])
        return self.response(
            info,
            items=items[cursor : cursor + limit],
            matchedCount=len(items),
            nextCursor=cursor + limit if cursor + limit < len(items) else None,
            complete=cursor + limit >= len(items),
        )

    def resolve_entity(self, version, system, native_id):
        info, nodes, edges = self.model(version)
        direct = [
            n
            for n in nodes
            if n["label"] == "Equipment"
            and n["sourceRef"]["systemId"] == system
            and n["sourceRef"]["nativeId"] == native_id
        ]
        links = [
            e
            for e in edges
            if e["kind"] == "REFERS_TO" and e["start"] == f"{system}:contact:{native_id}"
        ]
        canonical = direct[0]["key"] if direct else links[0]["end"] if len(links) == 1 else None
        target = next((n for n in nodes if n["key"] == canonical), None)
        type_rule_id = (
            "ASSET-TYPE-01"
            if target and target["sourceRef"]["systemId"] == "atcis"
            else "ASSET-TYPE-NAVAL-01"
        )
        classification_rule = (
            next(
                (
                    n["payload"]
                    for n in nodes
                    if n["label"] == "InterpretationRule" and n["payload"]["ruleId"] == type_rule_id
                ),
                None,
            )
            if target
            else None
        )
        observations = [
            e
            for e in edges
            if e["kind"] == "REFERS_TO"
            and e["end"] == canonical
            and e["start"].startswith("knccs:contact:")
        ]
        return self.response(
            info,
            status="resolved" if canonical else "unresolved",
            canonicalId=canonical,
            sourceRefs=[n["sourceRef"] for n in nodes if n["key"] == canonical],
            evidenceRefs=[e["evidenceId"] for e in observations]
            + ([type_rule_id] if target else []),
            kind=target["payload"]["kind"] if target else None,
            classificationRule=classification_rule,
            observationRefs=[
                n["sourceRef"] for n in nodes if n["key"] in {e["start"] for e in observations}
            ],
        )

    def get_semantic_evidence(self, version, evidence_id):
        info, nodes, edges = self.model(version)
        found = [e for e in edges if e["evidenceId"] == evidence_id] + [
            n["payload"]
            for n in nodes
            if n["label"] == "InterpretationRule" and n["payload"]["ruleId"] == evidence_id
        ]
        if not found:
            raise KeyError(evidence_id)
        return self.response(info, assertion=found[0])

    def query_relations(self, version, subject, relation_types, depth=2, limit=100):
        allowed = {"SUBORDINATE_TO", "ASSIGNED_TO", "REFERS_TO", "DERIVED_FROM", "SUPERSEDES"}
        if not set(relation_types) <= allowed or not 0 <= depth <= 8 or not 1 <= limit <= 100:
            raise ValueError("invalid bounded relation query")
        info, nodes, edges = self.model(version)
        if subject not in {n["key"] for n in nodes}:
            raise KeyError(subject)
        visited, found = {subject}, {}
        for _ in range(depth):
            next_edges = [
                e
                for e in edges
                if e["kind"] in relation_types and (e["start"] in visited or e["end"] in visited)
            ]
            for e in next_edges:
                found[e["evidenceId"]] = e
                visited.update((e["start"], e["end"]))
        items = list(found.values())
        omitted = any(
            e["kind"] in relation_types
            and (e["start"] in visited or e["end"] in visited)
            and e["evidenceId"] not in found
            for e in edges
        )
        return self.response(
            info,
            items=items[:limit],
            matchedCount=len(items),
            completeness="partial" if omitted or len(items) > limit else "complete",
        )

    def get_procedure_definition(self, version, document_id):
        info, nodes, _ = self.model(version)
        rules = [
            n["payload"]
            for n in nodes
            if n["label"] == "InterpretationRule"
            and n["payload"]["ruleId"] == "ACTIVITY-STEP-01"
            and n["payload"]["documentId"] == document_id
        ]
        if not rules:
            raise KeyError(document_id)
        return self.response(
            info,
            rules=rules,
            nativeEvidenceSelectors={
                "atcis": ["activities", "reports"],
                "knccs": ["messages", "delivery-events"],
            },
        )
