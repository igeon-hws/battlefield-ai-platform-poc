"""Bounded, version-pinned reads for the Fabric graph explorer.

Legacy semantic queries keep their contracts; this path never loads DomainService.model.
"""

import base64
import json
from hashlib import sha256

NODE_TYPES = {
    "LogisticsAsset",
    "WorkOrder",
    "Part",
    "Inventory",
    "Reservation",
    "SupplyRequest",
    "Cargo",
    "Transport",
    "System",
    "SourceRecord",
    "Unit",
    "Equipment",
    "EquipmentType",
    "ContactObservation",
    "Observation",
    "Report",
    "Incident",
    "Activity",
    "SourceDocument",
    "InterpretationRule",
    "ConceptDefinition",
    "Procedure",
    "StepDefinition",
}
RELATIONS = {
    "SUBORDINATE_TO",
    "ASSIGNED_TO",
    "REFERS_TO",
    "DERIVED_FROM",
    "SUPERSEDES",
    "FROM_SYSTEM",
    "OBSERVES",
    "SAME_AS",
    "MAINTAINS",
    "REQUIRES",
    "STOCK_OF",
    "RESERVES",
    "FOR_WORK",
    "FULFILLED_BY",
    "CARRIED_BY",
    "CONTAINS_PART",
}


def page_offset(cursor, scope):
    signature = sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
    if not cursor:
        return 0, signature
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor))
        if value["scope"] != signature or type(value["offset"]) is not int or value["offset"] < 0:
            raise ValueError()
        return value["offset"], signature
    except Exception as exc:
        raise ValueError("cursor does not match version and filters") from exc


def next_cursor(offset, signature):
    return base64.urlsafe_b64encode(
        json.dumps({"offset": offset, "scope": signature}).encode()
    ).decode()


def node_summary(node):
    payload = node.get("payload", {})
    return {k: node[k] for k in ("key", "label")} | {
        "name": payload.get("name")
        or payload.get("title")
        or payload.get("nativeId")
        or node["key"],
    }


class GraphExplorer:
    def __init__(self, repo):
        self.repo = repo

    def ready(self, version):
        info = self.repo.require_ready(version)
        if info["ontologyVersion"] not in ("3.0.0", "4.0.0", "5.0.0"):
            raise ValueError("Only READY v3/v4 graphs can be explored")
        return info

    def builds(self, q="", dataset="", date="", cursor="", limit=20):
        offset, signature = page_offset(cursor, ["builds", q, dataset, date])
        after = None
        if cursor:
            after = json.loads(base64.urlsafe_b64decode(cursor)).get("after")
            if (
                not isinstance(after, list)
                or len(after) != 2
                or not all(isinstance(v, str) for v in after)
            ):
                raise ValueError("invalid build cursor")
        rows = self.repo.query(
            "MATCH (b:GraphBuild) WHERE b.status='READY' AND b.ontologyVersion IN ['3.0.0','4.0.0','5.0.0'] "
            "AND toLower(b.graphVersion + coalesce(b.inputSnapshotSetJson,'') + coalesce(b.builtAt,'')) CONTAINS toLower($q) "
            "AND coalesce(b.inputSnapshotSetJson,'') CONTAINS $dataset "
            "AND coalesce(b.builtAt,'') STARTS WITH $date "
            "AND ($afterTime IS NULL OR coalesce(b.builtAt,'') < $afterTime OR (coalesce(b.builtAt,'') = $afterTime AND b.graphVersion > $afterVersion)) "
            "RETURN b.graphVersion AS v, coalesce(b.builtAt,'') AS builtAt ORDER BY builtAt DESC, b.graphVersion LIMIT $limit",
            q=q,
            dataset=dataset,
            date=date,
            afterTime=after[0] if after else None,
            afterVersion=after[1] if after else None,
            limit=limit + 1,
        )
        active = self.repo.active_version()
        items = [
            self.repo.build_info(r["v"]) | {"isActive": r["v"] == active} for r in rows[:limit]
        ]
        return {
            "items": items,
            "activeGraphVersion": active,
            "nextCursor": base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "offset": offset + limit,
                        "scope": signature,
                        "after": [rows[limit - 1]["builtAt"], rows[limit - 1]["v"]],
                    }
                ).encode()
            ).decode()
            if len(rows) > limit
            else None,
        }

    def summary(self, version):
        info = self.ready(version)
        nodes = self.repo.query(
            "MATCH (n:SemanticNode {graphVersion:$v}) WHERE n.domainJson IS NOT NULL "
            "RETURN [label IN labels(n) WHERE label <> 'SemanticNode'][0] AS kind, count(*) AS count",
            v=version,
        )
        edges = self.repo.query(
            "MATCH (:SemanticNode {graphVersion:$v})-[r]->(:SemanticNode {graphVersion:$v}) "
            "WHERE r.domainJson IS NOT NULL RETURN type(r) AS kind, count(*) AS count",
            v=version,
        )
        return {
            "graphVersion": version,
            "build": info,
            "nodeCounts": {r["kind"]: r["count"] for r in nodes},
            "edgeCounts": {r["kind"]: r["count"] for r in edges},
        }

    def nodes(self, version, q="", system="", kind="", cursor="", limit=30):
        self.ready(version)
        if kind and kind not in NODE_TYPES or system not in ("", "atcis", "knccs"):
            raise ValueError("unknown node type or source system")
        offset, signature = page_offset(cursor, [version, q, system, kind])
        # domainJson already exists on immutable historical builds. Filter in Neo4j;
        # only one bounded page is decoded in Python, without mutating old builds.
        rows = self.repo.query(
            "MATCH (n:SemanticNode {graphVersion:$v}) WHERE n.domainJson IS NOT NULL "
            "AND ($kind='' OR $kind IN labels(n)) "
            "AND ($system='' OR n.nodeKey STARTS WITH $system + ':' OR n.domainJson CONTAINS '\"systemId\": \"' + $system + '\"') "
            "AND toLower(n.nodeKey + n.domainJson) CONTAINS toLower($q) "
            "RETURN n.domainJson AS body ORDER BY n.nodeKey SKIP $offset LIMIT $limit",
            v=version,
            q=q,
            system=system,
            kind=kind,
            offset=offset,
            limit=limit + 1,
        )
        return {
            "graphVersion": version,
            "items": [node_summary(json.loads(r["body"])) for r in rows[:limit]],
            "nextCursor": next_cursor(offset + limit, signature) if len(rows) > limit else None,
        }

    def node(self, version, key):
        self.ready(version)
        rows = self.repo.query(
            "MATCH (n:SemanticNode {graphVersion:$v,nodeKey:$key}) WHERE n.domainJson IS NOT NULL RETURN n.domainJson AS body LIMIT 1",
            v=version,
            key=key,
        )
        if not rows:
            raise KeyError(key)
        return {"graphVersion": version, "item": json.loads(rows[0]["body"])}

    def neighborhood(self, version, subject, kinds, depth=1, node_limit=100, edge_limit=150):
        selected = set(kinds.split(","))
        if not selected <= RELATIONS or not selected:
            raise ValueError("unknown relation type")
        root = self.node(version, subject)["item"]
        nodes = {subject: root}
        edges: dict[str, dict] = {}
        frontier = [subject]
        reasons = set()
        for _ in range(depth):
            if not frontier:
                break
            following = set()
            for key in frontier:
                rows = self.repo.query(
                    "MATCH (a:SemanticNode {graphVersion:$v})-[r]-(b:SemanticNode {graphVersion:$v}) "
                    "WHERE a.nodeKey=$key AND type(r) IN $kinds AND r.domainJson IS NOT NULL "
                    "RETURN DISTINCT r.domainJson AS edge, b.domainJson AS node "
                    "ORDER BY edge LIMIT $limit",
                    v=version,
                    key=key,
                    kinds=sorted(selected),
                    limit=edge_limit + 1,
                )
                if len(rows) > edge_limit:
                    reasons.add("edgeLimit")
                for row in rows[:edge_limit]:
                    edge = json.loads(row["edge"])
                    other = json.loads(row["node"])
                    eid = edge["evidenceId"]
                    if eid in edges:
                        continue
                    if len(edges) >= edge_limit:
                        reasons.add("edgeLimit")
                        continue
                    if other["key"] not in nodes and len(nodes) >= node_limit:
                        reasons.add("nodeLimit")
                        continue
                    if other["key"] not in nodes:
                        following.add(other["key"])
                    nodes[other["key"]] = other
                    edges[eid] = edge
            frontier = sorted(following)
        # Detect continuing paths at the depth boundary rather than claiming the
        # returned neighborhood is the complete connected component.
        if frontier:
            more = self.repo.query(
                "MATCH (a:SemanticNode {graphVersion:$v})-[r]-(b:SemanticNode {graphVersion:$v}) "
                "WHERE a.nodeKey IN $keys AND type(r) IN $kinds AND r.domainJson IS NOT NULL "
                "AND NOT r.assertionId IN $seen RETURN 1 AS found LIMIT 1",
                v=version,
                keys=frontier,
                kinds=sorted(selected),
                seen=list(edges),
            )
            if more:
                reasons.add("depth")
        return {
            "graphVersion": version,
            "nodes": [node_summary(n) for n in nodes.values()],
            "edges": list(edges.values()),
            "completeness": "partial" if reasons else "complete",
            "omittedReasons": sorted(reasons),
        }
