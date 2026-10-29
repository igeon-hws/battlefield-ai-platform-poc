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


def _clock(value):
    return value[5:16].replace("T", " ") if value else "시각 미상"


# Display words for the analysis view only; judgments stay in the declaration rules.
STATUS_LABELS = {"available": "가용", "limited": "제한", "unavailable": "불가", "unknown": "미상"}
ROLE_LABELS = {
    "ORG": "편제",
    "ATT": "배속",
    "SUP": "지원",
    "ASSIGNED": "배정",
    "SUPPORT": "지원",
    "CTRL": "통제",
    "RECEIVER": "수신",
}
KIND_LABELS = {
    "tank": "전차",
    "armored_vehicle": "장갑차",
    "support_vehicle": "지원 차량",
    "uav": "무인기",
    "naval_vessel": "함정",
    "unknown": "유형 미상",
}


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
            labels = declaration
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
            labels = declared["payload"]
        self.concepts = {c["id"]: c["label"] for c in labels.get("concepts", [])}
        self.relation_labels = {r["id"]: r["label"] for r in labels.get("relationTypes", [])}
        times = [r["sourceTime"] for r in info["inputSnapshotSet"].values() if r.get("sourceTime")]
        self.as_of = min(_time(t) for t in times) if times else None
        self.used_edges: dict[str, dict] = {}
        self.records: dict[tuple, dict] = {}
        self.unknowns: list[str] = []
        self.steps: list[dict] = []
        self.excluded: dict[str, dict] = {}
        self.states: dict[str, str] = {}

    def name(self, key):
        node = self.by_key.get(key)
        if node is None:
            return key.rsplit(":", 1)[-1]
        return node["payload"].get("name") or node.get("sourceRef", {}).get("nativeId") or key

    def step(self, title, detail, rule_ids, count, node_keys):
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "title": title,
                "detail": detail,
                "ruleIds": list(rule_ids),
                "count": count,
                "nodeKeys": list(dict.fromkeys(node_keys)),
            }
        )

    def exclude(self, key, reason, rule_id, step):
        self.excluded.setdefault(
            key,
            {
                "key": key,
                "nativeId": key.rsplit(":", 1)[-1],
                "name": self.name(key),
                "reason": reason,
                "ruleId": rule_id,
                "step": step,
            },
        )
        self.states[key] = "excluded"

    def mark(self):
        return len(self.used_edges)

    def touched(self, mark):
        edges = list(self.used_edges.values())[mark:]
        return [k for e in edges for k in (e["start"], e["end"])]

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
            "steps": self.steps,
            "excluded": list(self.excluded.values()),
            "graphNodes": self._graph_nodes(),
            "relationLabels": {
                kind: self.relation_labels.get(kind, kind)
                for kind in dict.fromkeys(e["kind"] for e in self.used_edges.values())
            },
            "roleLabels": {
                role: ROLE_LABELS.get(role, role)
                for role in dict.fromkeys(
                    e["role"] for e in self.used_edges.values() if e.get("role")
                )
            },
        }

    def _graph_nodes(self):
        keys = [k for e in self.used_edges.values() for k in (e["start"], e["end"])]
        keys += [k for s in self.steps for k in s["nodeKeys"]] + list(self.excluded)
        nodes = []
        for key in dict.fromkeys(keys):
            node = self.by_key.get(key)
            label = node["label"] if node else None
            nodes.append(
                {
                    "key": key,
                    "name": self.name(key),
                    "concept": self.concepts.get(label, label),
                    "state": self.states.get(key),
                }
            )
        return nodes


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
    unit_node = units[0]
    ctx.step(
        "범위 정하기",
        f"{ctx.name(unit_node['key'])}({unit_node['sourceRef']['nativeId']}) 기준, 예하 부대 "
        f"{len(scope) - 1}개 포함",
        ["FORCE-SCOPE-01"],
        len(scope),
        sorted(scope),
    )
    definition = ctx.rules["FORCE-SCOPE-01"]["definition"]
    policy = ctx.rules["AGGREGATION-POLICY-01"]["definition"]
    included = policy[policy["defaultAvailablePolicy"]]
    items: dict[str, dict] = {}
    role_excluded: dict[str, str] = {}
    for unit in sorted(scope):
        for e in ctx.links("ASSIGNED_TO", end=unit):
            if e.get("role") not in definition["includedRoles"]:
                role_excluded.setdefault(e["start"], e.get("role") or "역할 없음")
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
    for key, role in role_excluded.items():
        if key not in items:
            ctx.exclude(
                key, f"{ROLE_LABELS.get(role, role)} 배정은 전력 범위에서 제외", "FORCE-SCOPE-01", 2
            )
    roles = sorted({r["role"] for i in items.values() for r in i["roles"]})
    ctx.step(
        "장비 모으기",
        f"{'·'.join(ROLE_LABELS.get(r, r) for r in roles) or '해당'} 배정 장비 {len(items)}대"
        + (f", 역할로 제외 {len(ctx.excluded)}대" if ctx.excluded else ""),
        ["FORCE-SCOPE-01", "ORG-ROLE-01"],
        len(items),
        [*items, *sorted(scope)],
    )
    wanted = params.get("kind")
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
        if wanted and kind != wanted:
            ctx.exclude(
                key,
                f"{KIND_LABELS.get(kind, kind)}, {KIND_LABELS.get(wanted, wanted)} 아님",
                type_rule["ruleId"],
                3,
            )
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
        ctx.states[key] = status
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
    kept = [i["canonicalId"] for i in result_items]
    if wanted:
        type_rules = sorted({e["ruleId"] for e in ctx.excluded.values() if e["step"] == 3})
        ctx.step(
            "유형 거르기",
            f"{KIND_LABELS.get(wanted, wanted)}만 남김: {len(items)} → {len(result_items)}대",
            type_rules or ["ASSET-TYPE-01"],
            len(result_items),
            kept,
        )

    def shown(value):
        if isinstance(value, dict):
            return "/".join(f"{k}={v}" for k, v in value.items())
        return value or "기록 없음"

    ctx.step(
        "상태 판정",
        ", ".join(
            f"{i['nativeId']} {shown(i['nativeStatus'])} → {STATUS_LABELS.get(i['status'])}"
            for i in result_items
        )
        + (f" (원천 기준 {_clock(_iso(ctx.as_of))})" if ctx.as_of else ""),
        sorted({i["statusRule"] for i in result_items}),
        len(result_items),
        kept,
    )
    available = [i for i in result_items if i["countedAsAvailable"]]
    ctx.step(
        "가용 집계",
        f"기본 가용 기준 {policy['defaultAvailablePolicy']}: "
        f"{'·'.join(STATUS_LABELS.get(s, s) for s in included)}만 셈 → "
        f"가용 {len(available)}대 / 전체 {len(result_items)}대",
        ["AGGREGATION-POLICY-01"],
        len(available),
        [i["canonicalId"] for i in available],
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
            "available": len(available),
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
            owner_work = target[0]["end"].split(":", 2)[2] if target else None
            if owner_work != work_id:
                ctx.exclude(
                    reserve["start"],
                    f"다른 작업({owner_work or '미상'}) 전용 예약이라 이 작업에 쓰지 않음",
                    "LOG-LINK-01",
                    4,
                )
            reservations.append(
                {
                    "reservationId": reservation_id,
                    "workOrderId": owner_work,
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
    ctx.step(
        "동일 장비 연결",
        f"{ctx.name(equipment)} = 군수 자산 {', '.join(a.split(':', 2)[2] for a in assets)} "
        "(등록 동일성)"
        if equipment and assets
        else "검증된 동일 장비 연결 없음",
        ["LOG-LINK-01"],
        len(assets),
        ([equipment] if equipment else []) + assets,
    )
    owner = None
    owner_keys: list[str] = []
    if equipment:
        scope = ctx.rules["FORCE-SCOPE-01"]["definition"]
        assigned = []
        for e in ctx.links("ASSIGNED_TO", start=equipment):
            role = e.get("role")
            if role in scope["includedRoles"] and role not in scope["supportRoles"]:
                assigned.append(e)
            else:
                ctx.exclude(
                    e["end"],
                    f"{ROLE_LABELS.get(role, role)} 배정은 소속 판단에서 제외",
                    "FORCE-SCOPE-01",
                    2,
                )
        if assigned:
            unit, ancestors = assigned[0]["end"], []
            current = unit
            owner_keys.append(unit)
            while parents := ctx.links("SUBORDINATE_TO", start=current):
                current = parents[0]["end"]
                owner_keys.append(current)
                ancestors.append(current.split(":", 2)[2])
            owner = {
                "unitCode": unit.split(":", 2)[2],
                "role": assigned[0]["role"],
                "ancestors": ancestors,
            }
    ctx.step(
        "소속 확인",
        f"{owner['unitCode']} {ROLE_LABELS.get(owner['role'], owner['role'])} 배정"
        + (f" · 상위 {' > '.join(owner['ancestors'])}" if owner["ancestors"] else "")
        if owner
        else "소속 배정 없음",
        ["FORCE-SCOPE-01"],
        len(owner_keys),
        owner_keys,
    )
    native_state = None
    if equipment and equipment.startswith("atcis:"):
        row = ctx.record("atcis", "equipment", "equipmentId", equipment.split(":", 2)[2])
        native_state = (row or {}).get("maintenanceCode")
    work_orders = []
    part_keys: list[str] = []
    work_keys: list[str] = []
    forecasts: list[str] = []
    for asset in assets:
        for maintains in ctx.links("MAINTAINS", end=asset):
            work_id = maintains["start"].split(":", 2)[2]
            work_keys.append(maintains["start"])
            work = ctx.record("logistics", "work-orders", "workOrderId", work_id) or {}
            mark = ctx.mark()
            parts = [_allocation(ctx, work_id, r) for r in work.get("requirements", [])]
            part_keys += ctx.touched(mark)
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
                    forecasts.append(
                        f"{work_id}: 부품 확보 {_clock(_iso(base))} + 작업 {work['laborHours']}h "
                        f"→ {_clock(earliest)} (조건부)"
                    )
            if earliest is None:
                reason = (
                    "다른 고장 여부 미확인"
                    if work.get("otherFaults") is not False
                    else "부품 부족 또는 기록 없음"
                )
                forecasts.append(f"{work_id}: {reason}으로 계산하지 않음")
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
    ctx.step(
        "정비 작업",
        ", ".join(
            f"{w['workOrderId']}(상태 {w['status']}, 작업 {w['laborHours']}h)" for w in work_orders
        )
        or "정비 작업 없음",
        ["LOG-LINK-01"],
        len(work_orders),
        work_keys,
    )

    def allocation(work_id, p):
        incoming = ", ".join(
            f"{i['transportId']} {_clock(i['deliveryAt'])} 도착" for i in p["incoming"]
        )
        shortfall = "기록 없음" if p["shortfall"] is None else p["shortfall"]
        return (
            f"{work_id} {p['partId']} 필요 {p['required']} = 이 작업 예약 "
            f"{p['reservedForThisWork']} + 미예약 재고 {p['allocatedFromUnreserved']} + 입고 "
            f"{p['allocatedFromIncoming']}"
            + (f"({incoming})" if incoming else "")
            + f" → 부족 {shortfall}"
        )

    ctx.step(
        "부품 확보",
        "; ".join(allocation(w["workOrderId"], p) for w in work_orders for p in w["parts"])
        or "필요 부품 없음",
        ["LOG-LINK-01"],
        sum(len(w["parts"]) for w in work_orders),
        part_keys,
    )
    ctx.step(
        "완료 전망",
        "; ".join(forecasts) or "정비 작업 없음",
        ["LOG-LINK-01"],
        sum(w["conditionalForecast"]["earliestCompletion"] is not None for w in work_orders),
        work_keys,
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
    mark = ctx.mark()
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
    ctx.step(
        "창고 재고",
        ", ".join(
            f"{w['warehouseId']}: 보유 {w['onHand']} · 예약 {w['reserved']} · 미예약 "
            f"{w['unreserved']}"
            for w in warehouses
        )
        or "재고 기록 없음",
        ["LOG-LINK-01"],
        len(warehouses),
        ctx.touched(mark),
    )
    mark = ctx.mark()
    required = []
    for requires in ctx.links("REQUIRES", end=part_key):
        work_id = requires["start"].split(":", 2)[2]
        required.append({"workOrderId": work_id, "quantity": requires.get("quantity")})
    ctx.step(
        "작업 수요",
        ", ".join(f"{r['workOrderId']} {r['quantity']}개" for r in required) or "수요 없음",
        ["LOG-LINK-01"],
        len(required),
        ctx.touched(mark),
    )
    mark = ctx.mark()
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
    ctx.step(
        "입고 예정",
        ", ".join(
            f"{i['cargoId']} {i['quantity']}개({i['transportId']} {_clock(i['deliveryAt'])} 도착, "
            f"{i['status']})"
            for i in incoming
        )
        or "입고 예정 없음",
        ["LOG-LINK-01"],
        len(incoming),
        ctx.touched(mark),
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
