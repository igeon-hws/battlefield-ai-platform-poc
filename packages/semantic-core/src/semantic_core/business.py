"""Deterministic C business view; never used to enrich A/B Agent inputs."""

from datetime import UTC, datetime


def business_summary(records, metadata, system, kind, native_id):
    def rows(source):
        return [item["record"] for item in records if item["systemId"] == source]

    land = rows("atcis")
    log = rows("logistics")
    sea = rows("knccs")
    selected: dict = next(
        (
            r
            for r in rows(system)
            if native_id in (r.get("equipmentId"), r.get("pennant"), r.get("assetId"))
        ),
        {},
    )
    asset_ids = {
        r["assetId"]
        for r in log
        if r.get("externalSystem") == system and r.get("externalId") == native_id
    }
    if system == "logistics":
        asset_ids.add(native_id)
    work = [
        r
        for r in log
        if r.get("workOrderId") and r.get("assetId") in asset_ids and "requirements" in r
    ]
    parts = {q["partId"] for r in work for q in r["requirements"]}
    requests = [
        r
        for r in log
        if r.get("requestId") and r.get("workOrderId") in {w["workOrderId"] for w in work}
    ]
    cargo = [
        r
        for r in log
        if r.get("cargoId") in {q.get("cargoId") for q in requests} and "transportId" in r
    ]
    transports = [r for r in sea if r.get("transportId") in {c["transportId"] for c in cargo}]
    owner = selected.get("ownerCode", selected.get("formationRef"))
    unit = next(
        (
            r.get("name", r.get("designation"))
            for r in land + sea
            if r.get("unitCode", r.get("formationRef")) == owner
            and ("name" in r or "designation" in r)
        ),
        None,
    )
    status = (
        metadata.value("atcis", "equipment", "maintenanceCode", selected.get("maintenanceCode"))
        if system == "atcis"
        else " / ".join(
            metadata.value("knccs", "own-forces", k, selected.get(k))
            for k in ("engineering", "mission")
        )
        if system == "knccs" and selected.get("pennant")
        else "원천 기록 확인"
    )
    return {
        "asset": {
            "name": metadata.value("atcis", "equipment", "classCode", selected.get("classCode"))
            if system == "atcis"
            else "함정"
            if selected.get("pennant")
            else "선택 객체",
            "status": status,
            "unit": unit or owner or "정보 없음",
            "limitation": selected.get("limitation"),
        },
        "maintenance": [
            {
                "id": w["workOrderId"],
                "status": metadata.value("logistics", "work-orders", "status", w.get("status")),
                "durationHours": w.get("laborHours"),
                "durationUnit": "h",
                "requirements": w["requirements"],
                "otherFaults": metadata.value(
                    "logistics", "work-orders", "otherFaults", w.get("otherFaults")
                ),
            }
            for w in work
        ],
        "inventory": [
            {
                "partId": r["partId"],
                "warehouse": r.get("warehouseId"),
                "onHand": r.get("onHand"),
                "reserved": r.get("reserved"),
                "unit": r.get("unit"),
            }
            for r in log
            if r.get("partId") in parts and "inventoryId" in r and "onHand" in r
        ],
        "transport": [
            {
                "id": r["transportId"],
                "status": metadata.value("knccs", "transports", "status", r.get("status")),
                "arrivalAt": r.get("arrivalAt"),
                "deliveryAt": r.get("deliveryAt"),
            }
            for r in transports
        ],
        "sourceTimes": [
            {
                "source": r["systemId"],
                "nativeId": r.get("nativeId"),
                "recordType": r.get("recordType"),
                "sourceTime": r.get("sourceTime"),
                "recordUpdatedAt": r.get("recordUpdatedAt"),
                "lastReceivedAt": r.get("lastReceivedAt"),
            }
            for r in records
        ],
        "queriedAt": datetime.now(UTC).isoformat(),
    }
