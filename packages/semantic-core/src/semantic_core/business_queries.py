"""v6 business queries: declared definitions over verified graph links + pinned source records.

The Graph supplies identity/scope/dependency links; live values come from the source
snapshot pinned to the same graph build. Rules and policies are read from the declaration
at query time, so a published definition change needs no code change.
"""

from datetime import datetime, timedelta


def _time(value):
    return datetime.fromisoformat(value)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _holds(condition, row):
    op = condition["op"]
    if op == "OR":
        return any(_holds(a, row) for a in condition["args"])
    if op == "AND":
        return all(_holds(a, row) for a in condition["args"])
    if op == "EXISTS":
        return row.get(condition["field"]) is not None
    if op == "EQ":
        return row.get(condition["field"]) == condition["value"]
    raise ValueError("unsupported rule operator: " + op)


def classify(rule, row):
    for case in rule["definition"]["cases"]:
        if _holds(case, row):
            return case["result"]
    return rule["definition"]["default"]


def stamps(info):
    """Graph identity the platform verifies on every Semantic response."""
    return {
        k: info[k]
        for k in (
            "graphVersion",
            "ontologyVersion",
            "mappingVersion",
            "resolutionRuleVersion",
            "inputStableHashes",
        )
    }


class Context:
    def __init__(self, info, nodes, edges, snapshots, declaration):
        self.info, self.nodes, self.edges, self.snapshots = info, nodes, edges, snapshots
        self.by_key = {n["key"]: n for n in nodes}
        if declaration is not None:
            self.rules = {r["ruleId"]: r for r in declaration["rules"]}
            self.queries = {q["queryId"]: q for q in declaration["businessQueries"]}
            self.version = f"{declaration['version']}-r{declaration['revision']}"
        else:
            self.rules = {
                n["payload"]["ruleId"]: n["payload"]
                for n in nodes
                if n["label"] == "InterpretationRule"
            }
            self.queries = {
                n["payload"]["queryId"]: n["payload"]
                for n in nodes
                if n["label"] == "BusinessQuery"
            }
            declared = next((n for n in nodes if n["label"] == "OntologyDeclaration"), None)
            if declared is None:
                raise ValueError("graph has no ontology declaration")
            self.version = declared["payload"]["declarationVersion"]
        times = [r["sourceTime"] for r in info["inputSnapshotSet"].values() if r.get("sourceTime")]
        self.as_of = min(_time(t) for t in times) if times else None
        self.used_edges: dict[str, dict] = {}
        self.records: dict[tuple, dict] = {}
        self.unknowns: list[str] = []

    def valid(self, edge):
        if not self.as_of:
            return True
        start = edge.get("effectiveFrom") or edge.get("validFrom")
        end = edge.get("effectiveTo") or edge.get("validTo")
        return (not start or _time(start) <= self.as_of) and (not end or self.as_of < _time(end))

    def links(self, kind, start=None, end=None):
        found = [
            e
            for e in self.edges
            if e["kind"] == kind
            and (start is None or e["start"] == start)
            and (end is None or e["end"] == end)
            and self.valid(e)
        ]
        for e in found:
            self.used_edges[e["evidenceId"]] = e
        return found

    def record(self, system, resource, field, native_id):
        rows = self.snapshots.get(system, {}).get("records", {}).get(resource, [])
        row = next((r for r in rows if r.get(field) == native_id), None)
        if row is not None:
            self.records[(system, resource, native_id)] = row
        return row

    def result(self, query, params, **body):
        return {
            **stamps(self.info),
            "queryId": query["queryId"],
            "title": query["title"],
            "declarationVersion": self.version,
            "knowledgeSetVersion": self.info.get("knowledgeSetVersion"),
            "params": params,
            "status": "resolved",
            **body,
            "appliedRules": [
                {
                    "ruleId": rule_id,
                    "title": self.rules[rule_id].get("title"),
                    "declarationVersion": self.version,
                    "definition": self.rules[rule_id]["definition"],
                }
                for rule_id in query["rules"]
                if rule_id in self.rules
            ],
            "graphEvidence": [
                {
                    k: e.get(k)
                    for k in ("evidenceId", "kind", "start", "end", "ruleId", "role")
                    if e.get(k) is not None
                }
                for e in self.used_edges.values()
            ],
            "sourceRecords": [
                {
                    "systemId": system,
                    "recordType": resource,
                    "nativeId": native_id,
                    "snapshotId": self.snapshots[system].get("snapshotId"),
                    "sourceTime": self.snapshots[system].get("sourceTime"),
                }
                for system, resource, native_id in self.records
            ],
            "unknowns": self.unknowns,
            "completeness": "partial" if self.unknowns else "complete",
        }


def _unit_matches(node, term):
    payload = node["payload"]
    return term in (
        node["key"],
        node["sourceRef"]["nativeId"],
        payload.get("name"),
        payload.get("previousName"),
        payload.get("designation"),
    )


def asset_status_summary(ctx, query, params):
    term = params.get("unit")
    if not term:
        raise ValueError("unit parameter required")
    units = [n for n in ctx.nodes if n["label"] == "Unit" and _unit_matches(n, term)]
    if len(units) != 1:
        return {
            **ctx.result(query, params),
            "status": "ambiguous" if units else "unresolved",
            "candidates": [u["key"] for u in units],
            "items": [],
            "counts": None,
        }
    scope = {units[0]["key"]}
    for _ in range(ctx.rules["FORCE-SCOPE-01"]["definition"]["maxDepth"]):
        children = {e["start"] for k in scope for e in ctx.links("SUBORDINATE_TO", end=k)} - scope
        if not children:
            break
        scope |= children
    definition = ctx.rules["FORCE-SCOPE-01"]["definition"]
    policy = ctx.rules["AGGREGATION-POLICY-01"]["definition"]
    included = policy[policy["defaultAvailablePolicy"]]
    items: dict[str, dict] = {}
    for unit in sorted(scope):
        for e in ctx.links("ASSIGNED_TO", end=unit):
            if e.get("role") not in definition["includedRoles"]:
                continue
            equipment = ctx.by_key[e["start"]]
            system = equipment["sourceRef"]["systemId"]
            native = equipment["sourceRef"]["nativeId"]
            item = items.setdefault(
                equipment["key"],
                {
                    "canonicalId": equipment["key"],
                    "systemId": system,
                    "nativeId": native,
                    "roles": [],
                },
            )
            item["roles"].append({"unit": unit, "role": e["role"]})
    result_items = []
    for key, item in sorted(items.items()):
        equipment = ctx.by_key[key]
        native_row = equipment["payload"]["native"]
        type_rule = ctx.rules[
            "ASSET-TYPE-01" if item["systemId"] == "atcis" else "ASSET-TYPE-NAVAL-01"
        ]
        kind = type_rule["definition"]["values"].get(
            native_row.get(type_rule["definition"]["typeField"]), "unknown"
        )
        if params.get("kind") and kind != params["kind"]:
            continue
        if item["systemId"] == "atcis":
            row = ctx.record("atcis", "equipment", "equipmentId", item["nativeId"])
            rule = ctx.rules["AVAIL-LAND-01"]
            native_status = (row or {}).get("maintenanceCode")
        else:
            row = ctx.record("knccs", "own-forces", "pennant", item["nativeId"])
            rule = ctx.rules["AVAIL-NAVAL-01"]
            native_status = {k: (row or {}).get(k) for k in ("engineering", "mission")}
        status = classify(rule, row) if row is not None else "unknown"
        if row is None:
            ctx.unknowns.append(f"{item['nativeId']} 원천 상태 기록 없음")
        elif status == "unknown":
            ctx.unknowns.append(f"{item['nativeId']} 상태 미상: {native_status}")
        result_items.append(
            {
                **item,
                "kind": kind,
                "nativeStatus": native_status,
                "status": status,
                "statusRule": rule["ruleId"],
                "support": all(r["role"] in definition["supportRoles"] for r in item["roles"]),
                "limitation": (row or {}).get("limitation"),
                "countedAsAvailable": status in included,
            }
        )
    by_status: dict[str, int] = {}
    by_kind: dict[str, dict[str, int]] = {}
    for item in result_items:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
        kinds = by_kind.setdefault(item["kind"], {})
        kinds[item["status"]] = kinds.get(item["status"], 0) + 1
    return ctx.result(
        query,
        params,
        scope={"unitIds": sorted(scope)},
        items=result_items,
        policy={
            "ruleId": "AGGREGATION-POLICY-01",
            "defaultAvailablePolicy": policy["defaultAvailablePolicy"],
            "includedStatuses": included,
            "unit": policy["unit"],
        },
        counts={
            "total": len(result_items),
            "available": sum(i["countedAsAvailable"] for i in result_items),
            "byStatus": by_status,
            "byKindStatus": by_kind,
        },
    )


def _allocation(ctx, work_id, requirement):
    part_id, required = requirement["partId"], requirement["quantity"]
    part_key = "logistics:part:" + part_id
    ctx.links("REQUIRES", start="logistics:work-order:" + work_id, end=part_key)
    on_hand, reservations = 0, []
    inventories = ctx.links("STOCK_OF", end=part_key)
    for stock in inventories:
        inventory_id = stock["start"].split(":", 2)[2]
        row = ctx.record("logistics", "inventory", "inventoryId", inventory_id)
        on_hand += (row or {}).get("onHand") or 0
        for reserve in ctx.links("RESERVES", end=stock["start"]):
            reservation_id = reserve["start"].split(":", 2)[2]
            res = ctx.record("logistics", "reservations", "reservationId", reservation_id)
            target = ctx.links("FOR_WORK", start=reserve["start"])
            reservations.append(
                {
                    "reservationId": reservation_id,
                    "workOrderId": target[0]["end"].split(":", 2)[2] if target else None,
                    "quantity": (res or {}).get("quantity", 0),
                }
            )
    reserved_here = sum(r["quantity"] for r in reservations if r["workOrderId"] == work_id)
    unreserved = on_hand - sum(r["quantity"] for r in reservations)
    incoming = []
    for request in ctx.links("FOR_WORK", end="logistics:work-order:" + work_id):
        if not request["start"].startswith("logistics:supply-request:"):
            continue
        request_id = request["start"].split(":", 2)[2]
        req = ctx.record("logistics", "supply-requests", "requestId", request_id)
        if not req or req.get("partId") != part_id:
            continue
        for fulfil in ctx.links("FULFILLED_BY", start=request["start"]):
            cargo_id = fulfil["end"].split(":", 2)[2]
            cargo = ctx.record("logistics", "cargo", "cargoId", cargo_id) or {}
            for carried in ctx.links("CARRIED_BY", start=fulfil["end"]):
                transport_id = carried["end"].split(":", 2)[2]
                transport = ctx.record("knccs", "transports", "transportId", transport_id) or {}
                incoming.append(
                    {
                        "requestId": request_id,
                        "cargoId": cargo_id,
                        "transportId": transport_id,
                        "quantity": cargo.get("quantity", req.get("quantity", 0)),
                        "deliveryAt": transport.get("deliveryAt"),
                        "status": transport.get("status"),
                    }
                )
    need = max(required - reserved_here, 0)
    from_unreserved = min(need, max(unreserved, 0))
    remaining = need - from_unreserved
    from_incoming = min(remaining, sum(i["quantity"] for i in incoming))
    shortfall = remaining - from_incoming
    if not inventories and not incoming:
        ctx.unknowns.append(f"{part_id} 재고·입고 기록 없음({work_id})")
    return {
        "partId": part_id,
        "required": required,
        "reservedForThisWork": reserved_here,
        "reservedForOtherWork": [r for r in reservations if r["workOrderId"] != work_id],
        "unreservedAvailable": max(unreserved, 0),
        "allocatedFromUnreserved": from_unreserved,
        "allocatedFromIncoming": from_incoming,
        "incoming": incoming,
        "shortfall": shortfall if inventories or incoming else None,
    }


def asset_dependency_chain(ctx, query, params):
    system, native = params.get("systemId"), params.get("nativeId")
    if system not in ("atcis", "knccs", "logistics") or not native:
        raise ValueError("systemId and nativeId parameters required")
    start = f"logistics:asset:{native}" if system == "logistics" else f"{system}:equipment:{native}"
    if start not in ctx.by_key:
        return {**ctx.result(query, params), "status": "unresolved", "workOrders": []}
    if system == "logistics":
        assets = [start]
        same = ctx.links("SAME_AS", start=start)
        equipment = same[0]["end"] if same else None
    else:
        assets = [e["start"] for e in ctx.links("SAME_AS", end=start)]
        equipment = start
    owner = None
    if equipment:
        scope = ctx.rules["FORCE-SCOPE-01"]["definition"]
        assigned = [
            e
            for e in ctx.links("ASSIGNED_TO", start=equipment)
            if e.get("role") in scope["includedRoles"]
            and e.get("role") not in scope["supportRoles"]
        ]
        if assigned:
            unit, ancestors = assigned[0]["end"], []
            current = unit
            while parents := ctx.links("SUBORDINATE_TO", start=current):
                current = parents[0]["end"]
                ancestors.append(current.split(":", 2)[2])
            owner = {
                "unitCode": unit.split(":", 2)[2],
                "role": assigned[0]["role"],
                "ancestors": ancestors,
            }
    native_state = None
    if equipment and equipment.startswith("atcis:"):
        row = ctx.record("atcis", "equipment", "equipmentId", equipment.split(":", 2)[2])
        native_state = (row or {}).get("maintenanceCode")
    work_orders = []
    for asset in assets:
        for maintains in ctx.links("MAINTAINS", end=asset):
            work_id = maintains["start"].split(":", 2)[2]
            work = ctx.record("logistics", "work-orders", "workOrderId", work_id) or {}
            parts = [_allocation(ctx, work_id, r) for r in work.get("requirements", [])]
            assumptions = ["예정대로 인도", "다른 미해결 고장 없음", "부품 확보 즉시 작업 시작"]
            earliest = None
            if work.get("otherFaults") is not False:
                ctx.unknowns.append(f"{work_id} 다른 미해결 고장 여부 미확인")
            elif parts and all(p["shortfall"] == 0 for p in parts):
                ready = [
                    _time(i["deliveryAt"])
                    for p in parts
                    if p["allocatedFromIncoming"]
                    for i in p["incoming"]
                    if i["deliveryAt"]
                ]
                base = max(ready) if ready else ctx.as_of
                if base is not None and work.get("laborHours") is not None:
                    earliest = _iso(base + timedelta(hours=work["laborHours"]))
            work_orders.append(
                {
                    "workOrderId": work_id,
                    "logisticsAssetId": asset.split(":", 2)[2],
                    "status": work.get("status"),
                    "laborHours": work.get("laborHours"),
                    "laborHoursMeaning": "작업 경과 시간(h)",
                    "otherFaults": work.get("otherFaults"),
                    "currentNativeState": native_state,
                    "parts": parts,
                    "conditionalForecast": {
                        "earliestCompletion": earliest,
                        "assumptions": assumptions,
                        "note": "조건부 전망이며 현재 상태나 복구 완료를 확정하지 않는다.",
                    },
                }
            )
    return ctx.result(
        query,
        params,
        identity={
            "equipment": equipment,
            "logisticsAssets": [a.split(":", 2)[2] for a in assets],
        },
        owner=owner,
        workOrders=work_orders,
    )


def part_supply_status(ctx, query, params):
    part_id = params.get("partId")
    if not part_id:
        raise ValueError("partId parameter required")
    part_key = "logistics:part:" + part_id
    if part_key not in ctx.by_key:
        return {**ctx.result(query, params), "status": "unresolved", "warehouses": []}
    warehouses = []
    for stock in ctx.links("STOCK_OF", end=part_key):
        inventory_id = stock["start"].split(":", 2)[2]
        row = ctx.record("logistics", "inventory", "inventoryId", inventory_id) or {}
        reservations = []
        for reserve in ctx.links("RESERVES", end=stock["start"]):
            reservation_id = reserve["start"].split(":", 2)[2]
            res = ctx.record("logistics", "reservations", "reservationId", reservation_id) or {}
            target = ctx.links("FOR_WORK", start=reserve["start"])
            reservations.append(
                {
                    "reservationId": reservation_id,
                    "workOrderId": target[0]["end"].split(":", 2)[2] if target else None,
                    "quantity": res.get("quantity", 0),
                }
            )
        reserved = sum(r["quantity"] for r in reservations)
        if row.get("reserved") is not None and row["reserved"] != reserved:
            ctx.unknowns.append(f"{inventory_id} 예약 합계와 예약 상세 불일치")
        warehouses.append(
            {
                "inventoryId": inventory_id,
                "warehouseId": row.get("warehouseId"),
                "onHand": row.get("onHand"),
                "reserved": reserved,
                "unreserved": (row.get("onHand") or 0) - reserved,
                "unit": row.get("unit"),
                "reservations": reservations,
            }
        )
    required = []
    for requires in ctx.links("REQUIRES", end=part_key):
        work_id = requires["start"].split(":", 2)[2]
        required.append({"workOrderId": work_id, "quantity": requires.get("quantity")})
    incoming = []
    for contains in ctx.links("CONTAINS_PART", end=part_key):
        cargo_id = contains["start"].split(":", 2)[2]
        cargo = ctx.record("logistics", "cargo", "cargoId", cargo_id) or {}
        for carried in ctx.links("CARRIED_BY", start=contains["start"]):
            transport_id = carried["end"].split(":", 2)[2]
            transport = ctx.record("knccs", "transports", "transportId", transport_id) or {}
            incoming.append(
                {
                    "cargoId": cargo_id,
                    "requestId": cargo.get("requestId"),
                    "transportId": transport_id,
                    "quantity": cargo.get("quantity"),
                    "deliveryAt": transport.get("deliveryAt"),
                    "status": transport.get("status"),
                }
            )
    return ctx.result(query, params, warehouses=warehouses, requiredBy=required, incoming=incoming)


OPERATORS = {
    "asset_status_summary": asset_status_summary,
    "asset_dependency_chain": asset_dependency_chain,
    "part_supply_status": part_supply_status,
}


def list_business_queries(nodes, declaration=None):
    queries = (
        declaration["businessQueries"]
        if declaration is not None
        else [n["payload"] for n in nodes if n["label"] == "BusinessQuery"]
    )
    return [
        {k: q[k] for k in ("queryId", "title", "description", "params", "rules", "relations")}
        for q in queries
    ]


def run_business_query(info, nodes, edges, snapshots, query_id, params, declaration=None):
    ctx = Context(info, nodes, edges, snapshots, declaration)
    query = ctx.queries.get(query_id)
    if query is None:
        raise KeyError(query_id)
    return OPERATORS[query["operator"]](ctx, query, params or {})
