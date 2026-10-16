import json
import threading
from datetime import UTC, datetime

from battlefield_ontology import (
    MAPPING_VERSION,
    ONTOLOGY_VERSION,
    RESOLUTION_VERSION,
    Observation,
    SourceRef,
    build_model,
    digest,
    stable_hash,
    stable_payload,
)
from neo4j import GraphDatabase


class GraphRepository:
    def __init__(self, uri, user, password, database="neo4j"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.write_lock = threading.Lock()

    def close(self):
        self.driver.close()

    def verify(self):
        self.driver.verify_connectivity()

    def query(self, text, **params):
        return [
            r.data()
            for r in self.driver.execute_query(
                text, parameters_=params, database_=self.database
            ).records
        ]

    def ensure_schema(self):
        self.query(
            "CREATE CONSTRAINT semantic_node_key IF NOT EXISTS FOR (n:SemanticNode) REQUIRE (n.graphVersion,n.nodeKey) IS UNIQUE"
        )
        self.query(
            "CREATE CONSTRAINT graph_build_key IF NOT EXISTS FOR (b:GraphBuild) REQUIRE b.graphVersion IS UNIQUE"
        )
        self.query(
            "CREATE CONSTRAINT graph_state_key IF NOT EXISTS FOR (s:GraphState) REQUIRE s.id IS UNIQUE"
        )

    def build_info(self, version):
        rows = self.query(
            "MATCH (b:GraphBuild {graphVersion:$v}) RETURN properties(b) AS b", v=version
        )
        if not rows:
            raise KeyError(version)
        b = rows[0]["b"]
        return {
            **b,
            "inputStableHashes": json.loads(b["inputStableHashesJson"]),
            "inputSnapshotSet": json.loads(b["inputSnapshotSetJson"]),
        }

    def active_version(self):
        rows = self.query("MATCH (s:GraphState {id:'active'}) RETURN s.graphVersion AS v")
        return rows[0]["v"] if rows else None

    def require_ready(self, version):
        info = self.build_info(version)
        if info["status"] != "READY":
            raise ValueError("graph build is not READY")
        return info

    def build(self, sources, graph_version=None):
        stable = {system: stable_payload(data) for system, data in sources.items()}
        hashes = {system: stable_hash(data) for system, data in stable.items()}
        fingerprint = digest(
            {
                "hashes": hashes,
                "ontology": ONTOLOGY_VERSION,
                "mapping": MAPPING_VERSION,
                "resolution": RESOLUTION_VERSION,
            }
        )
        version = graph_version or "graph-" + fingerprint[:24]
        inputs = {
            system: {
                k: data.get(k)
                for k in ("datasetId", "epochId", "snapshotId", "sequence", "sourceTime")
            }
            for system, data in sources.items()
        }
        for system, ref in inputs.items():
            ref["stableDataHash"] = hashes[system]
        with self.write_lock:
            try:
                existing = self.build_info(version)
            except KeyError:
                existing = None
            if existing:
                if existing["inputFingerprint"] != fingerprint:
                    raise ValueError("immutable graph version inputs")
                if existing["status"] == "READY":
                    return existing
            self.query(
                "MERGE (b:GraphBuild {graphVersion:$v}) SET b.status='BUILDING',b.inputFingerprint=$f,b.inputStableHashesJson=$h,b.inputSnapshotSetJson=$i,b.ontologyVersion=$o,b.mappingVersion=$m,b.resolutionRuleVersion=$r,b.builtAt=$t",
                v=version,
                f=fingerprint,
                h=json.dumps(hashes),
                i=json.dumps(inputs),
                o=ONTOLOGY_VERSION,
                m=MAPPING_VERSION,
                r=RESOLUTION_VERSION,
                t=datetime.now(UTC).isoformat(),
            )
            try:
                model = build_model(stable)
                nodes, edges = self._materialize(version, stable, model)
                with self.driver.session(database=self.database) as session:
                    session.execute_write(self._publish, version, nodes, edges, inputs)
            except Exception as exc:
                self.query(
                    "MATCH (b:GraphBuild {graphVersion:$v}) SET b.status='FAILED',b.diagnostic=$d",
                    v=version,
                    d=str(exc),
                )
                raise
            return self.build_info(version)

    @staticmethod
    def _materialize(version, sources, model):
        nodes: dict[str, list[dict]] = {
            label: [] for label in ("System", "Unit", "Equipment", "SourceRecord", "Observation")
        }
        edges: dict[str, list[dict]] = {
            kind: []
            for kind in ("FROM_SYSTEM", "REFERS_TO", "OBSERVES", "ASSIGNED_TO", "SUBORDINATE_TO")
        }

        def node(label, key, **props):
            nodes[label].append({"key": key, "props": {**props, "graphVersion": version}})

        def assertion(kind, start, end, ref, rule, payload):
            aid = "evidence-" + digest([version, kind, start, end, ref])[:32]
            props = {
                "assertionId": aid,
                "ruleId": rule,
                "ruleVersion": RESOLUTION_VERSION if rule.startswith("ER-") else MAPPING_VERSION,
                "sourceRefsJson": json.dumps([ref]),
                "evidenceIds": [aid],
                "payloadJson": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                "payloadHash": digest(payload),
            }
            Observation.model_validate(
                {
                    "observationId": aid,
                    "assertionType": kind,
                    "sourceRefs": [ref],
                    "ruleId": rule,
                    "ruleVersion": props["ruleVersion"],
                    "payloadHash": props["payloadHash"],
                }
            )
            node("Observation", "observation:" + aid, evidenceId=aid, **props)
            edges[kind].append({"start": start, "end": end, "props": props})
            edges["OBSERVES"].append(
                {
                    "start": "observation:" + aid,
                    "end": "source:" + SourceRef.model_validate(ref).key,
                    "props": {"ruleId": rule, "evidenceIds": [aid]},
                }
            )
            return aid

        for system in sources:
            node("System", "system:" + system, systemId=system, synthetic=True)
        for unit in model["units"]:
            ref = unit["sourceRef"]
            source_key = "source:" + SourceRef.model_validate(ref).key
            key = "unit:" + unit["canonicalId"]
            node(
                "Unit",
                key,
                canonicalId=unit["canonicalId"],
                nativeId=unit["unitId"],
                name=unit["name"],
                sourceRefJson=json.dumps(ref),
            )
            node(
                "SourceRecord",
                source_key,
                sourceRefJson=json.dumps(ref),
                nativeId=ref["nativeId"],
                systemId=ref["systemId"],
                recordType="unit",
            )
            edges["FROM_SYSTEM"].append(
                {
                    "start": source_key,
                    "end": "system:" + ref["systemId"],
                    "props": {"ruleId": "SOURCE-SYSTEM"},
                }
            )
            assertion("REFERS_TO", source_key, key, ref, "MAP-NATIVE-UNIT", unit)
            if unit["parentId"]:
                assertion(
                    "SUBORDINATE_TO", key, "unit:" + unit["parentId"], ref, "MAP-PARENT-UNIT", unit
                )
        for equipment in model["equipment"]:
            key = "equipment:" + equipment["canonicalId"]
            node(
                "Equipment",
                key,
                canonicalId=equipment["canonicalId"],
                kind=equipment["kind"],
                identityStatus=equipment["identity"]["status"],
            )
            for record in equipment["observations"]:
                ref = SourceRef.model_validate(
                    {
                        k: record[k]
                        for k in ("systemId", "datasetId", "epochId", "recordType", "nativeId")
                    }
                ).public()
                source_key = "source:" + record["sourceRecordKey"]
                node(
                    "SourceRecord",
                    source_key,
                    sourceRefJson=json.dumps(ref),
                    nativeId=record["nativeId"],
                    systemId=record["systemId"],
                    recordType="equipment",
                )
                edges["FROM_SYSTEM"].append(
                    {
                        "start": source_key,
                        "end": "system:" + record["systemId"],
                        "props": {"ruleId": "SOURCE-SYSTEM"},
                    }
                )
                assertion(
                    "REFERS_TO",
                    source_key,
                    key,
                    ref,
                    equipment["identity"].get("ruleId") or "MAP-NATIVE-EQUIPMENT",
                    record,
                )
                if record.get("unitId"):
                    assertion(
                        "ASSIGNED_TO",
                        key,
                        "unit:" + record["systemId"] + ":" + record["unitId"],
                        ref,
                        "MAP-OWNER-UNIT",
                        record,
                    )
                    edges["ASSIGNED_TO"][-1]["props"]["assignmentRole"] = record.get(
                        "assignmentRole", "assigned"
                    )
        return nodes, edges

    @staticmethod
    def _publish(tx, version, nodes, edges, inputs):
        for label, items in nodes.items():
            tx.run(
                f"UNWIND $items AS item MERGE (n:SemanticNode {{graphVersion:$v,nodeKey:item.key}}) SET n:{label} SET n += item.props",
                v=version,
                items=items,
            ).consume()
        for kind, items in edges.items():
            tx.run(
                f"UNWIND $items AS item MATCH (a:SemanticNode {{graphVersion:$v,nodeKey:item.start}}),(b:SemanticNode {{graphVersion:$v,nodeKey:item.end}}) MERGE (a)-[r:{kind} {{assertionKey:coalesce(item.props.assertionId,item.start+'>'+item.end)}}]->(b) SET r += item.props",
                v=version,
                items=items,
            ).consume()
        tx.run(
            "MATCH (b:GraphBuild {graphVersion:$v}) SET b.status='READY',b.publishedCursorsJson=$c MERGE (s:GraphState {id:'active'}) SET s.graphVersion=$v",
            v=version,
            c=json.dumps(inputs),
        ).consume()

    def model(self, version):
        self.require_ready(version)
        units = self.query(
            "MATCH (u:Unit {graphVersion:$v}) RETURN u.canonicalId AS canonicalId,u.name AS name",
            v=version,
        )
        equipment = self.query(
            "MATCH (e:Equipment {graphVersion:$v}) RETURN e.canonicalId AS canonicalId,e.kind AS kind,e.identityStatus AS identityStatus",
            v=version,
        )
        return {"units": units, "equipment": equipment}

    def unit_scope(self, version, term, max_depth=8):
        self.require_ready(version)
        if not 0 <= max_depth <= 8:
            raise ValueError("invalid maximum depth")
        candidates = self.query(
            "MATCH (u:Unit {graphVersion:$v}) WHERE u.name=$term OR u.canonicalId=$term OR u.nativeId=$term RETURN u.canonicalId AS canonicalId,u.name AS name",
            v=version,
            term=term,
        )
        if len(candidates) != 1:
            return {
                "status": "ambiguous" if candidates else "unresolved",
                "candidates": candidates,
                "unitIds": [],
                "paths": [],
                "complete": True,
            }
        root = candidates[0]["canonicalId"]
        rows = self.query(
            f"MATCH p=(u:Unit {{graphVersion:$v}})-[:SUBORDINATE_TO*0..{int(max_depth)}]->(root:Unit {{graphVersion:$v,canonicalId:$root}}) RETURN u.canonicalId AS id,[r IN relationships(p) | r.assertionId] AS evidenceRefs,[n IN nodes(p) | n.canonicalId] AS path",
            v=version,
            root=root,
        )
        ids = sorted({r["id"] for r in rows})
        omitted = self.query(
            "MATCH (child:Unit {graphVersion:$v})-[:SUBORDINATE_TO]->(p:Unit {graphVersion:$v}) WHERE p.canonicalId IN $ids AND NOT child.canonicalId IN $ids RETURN count(child) AS n",
            v=version,
            ids=ids,
        )[0]["n"]
        return {"status": "resolved", "unitIds": ids, "paths": rows, "complete": omitted == 0}

    def equipment_refs(self, version, unit_ids, kind=None, limit=100, cursor=0):
        self.require_ready(version)
        if not 1 <= limit <= 100 or cursor < 0:
            raise ValueError("invalid pagination")
        rows = self.query(
            "MATCH (e:Equipment {graphVersion:$v})-[a:ASSIGNED_TO]->(u:Unit {graphVersion:$v}) WHERE u.canonicalId IN $ids AND ($kind IS NULL OR e.kind=$kind) WITH DISTINCT e MATCH (s:SourceRecord {graphVersion:$v})-[r:REFERS_TO]->(e) RETURN e.canonicalId AS canonicalId,e.kind AS kind,e.identityStatus AS identityStatus,collect(DISTINCT s.sourceRefJson) AS sourceRefs,collect(DISTINCT r.assertionId) AS evidenceRefs ORDER BY canonicalId",
            v=version,
            ids=unit_ids,
            kind=kind,
        )
        for row in rows:
            row["sourceRefs"] = [json.loads(r) for r in row["sourceRefs"]]
            assignments = self.query(
                "MATCH (e:Equipment {graphVersion:$v,canonicalId:$id})-[a:ASSIGNED_TO]->(u:Unit {graphVersion:$v}) RETURN u.canonicalId AS unitId,a.assertionId AS evidenceRef,a.assignmentRole AS assignmentRole",
                v=version,
                id=row["canonicalId"],
            )
            row["assignments"] = assignments
            row["evidenceRefs"] += [a["evidenceRef"] for a in assignments]
        return {
            "items": rows[cursor : cursor + limit],
            "matchedCount": len(rows),
            "nextCursor": cursor + limit if cursor + limit < len(rows) else None,
            "complete": cursor + limit >= len(rows),
        }

    def evidence(self, version, evidence_id):
        info = self.require_ready(version)
        rows = self.query(
            "MATCH (o:Observation {graphVersion:$v,evidenceId:$id}) RETURN properties(o) AS o",
            v=version,
            id=evidence_id,
        )
        if not rows:
            raise KeyError(evidence_id)
        item = rows[0]["o"]
        refs = json.loads(item["sourceRefsJson"])
        return {
            **item,
            "sourceRefs": refs,
            "sourceSnapshotRefs": {
                ref["systemId"]: info["inputSnapshotSet"][ref["systemId"]] for ref in refs
            },
        }

    def resolve_entity(self, version, system, native_id):
        self.require_ready(version)
        rows = self.query(
            "MATCH (s:SourceRecord {graphVersion:$v,systemId:$sys,nativeId:$id,recordType:'equipment'})-[r:REFERS_TO]->(e:Equipment {graphVersion:$v}) MATCH (other:SourceRecord {graphVersion:$v})-[rr:REFERS_TO]->(e) RETURN e.canonicalId AS canonicalId,e.identityStatus AS status,collect(other.sourceRefJson) AS sourceRefs,collect(rr.assertionId) AS evidenceRefs",
            v=version,
            sys=system,
            id=native_id,
        )
        if not rows:
            return {
                "status": "unresolved",
                "canonicalId": None,
                "sourceRefs": [],
                "evidenceRefs": [],
            }
        row = rows[0]
        row["sourceRefs"] = [json.loads(s) for s in row["sourceRefs"]]
        if row["status"] != "resolved":
            row["canonicalId"] = None
        return row

    def remove_test_build(self, version):
        if not version.startswith("test-"):
            raise ValueError("only test-scoped builds may be removed")
        self.query("MATCH (n:SemanticNode {graphVersion:$v}) DETACH DELETE n", v=version)
        self.query("MATCH (b:GraphBuild {graphVersion:$v}) DELETE b", v=version)
        self.query("MATCH (s:GraphState {id:'active',graphVersion:$v}) DELETE s", v=version)
