"""Reviewed explicit logistics mappings; never inferred from labels/coordinates."""

import json
from pathlib import Path

from battlefield_ontology import digest

RESOURCE_IDS = {
    "assets": ("asset", "assetId", "LogisticsAsset"),
    "work-orders": ("work-order", "workOrderId", "WorkOrder"),
    "parts": ("part", "partId", "Part"),
    "inventory": ("inventory", "inventoryId", "Inventory"),
    "reservations": ("reservation", "reservationId", "Reservation"),
    "supply-requests": ("supply-request", "requestId", "SupplyRequest"),
    "cargo": ("cargo", "cargoId", "Cargo"),
}


def extend_logistics(sources, documents, manifest, nodes, edges, node, ref):
    doc = next(d for d in documents if d["documentKey"] == "logistics:LOG-01")
    reviewed = json.loads(
        Path(__file__).with_name("logistics_document.json").read_text(encoding="utf-8")
    )
    if doc != reviewed:
        raise ValueError("unreviewed logistics document")
    docref = {
        "systemId": "fabric",
        "documentKey": "logistics:LOG-01",
        "knowledgeSetVersion": manifest["knowledgeSetVersion"],
        "hash": doc["document"]["hash"],
    }
    node("logistics", "document", "LOG-01", "SourceDocument", doc["document"])
    for resource, (kind, idfield, label) in RESOURCE_IDS.items():
        for row in sources["logistics"]["records"][resource]:
            node("logistics", kind, row[idfield], label, row)
    for row in sources["knccs"]["records"]["transports"]:
        node("knccs", "transport", row["transportId"], "Transport", row)

    def link(kind, start, end, source, resource, id, **props):
        if start not in nodes or end not in nodes:
            raise ValueError("missing logistics relation endpoint")
        body = {
            "kind": kind,
            "start": start,
            "end": end,
            "sourceRefs": [ref(source, resource, id)],
            "ruleId": "LOG-LINK-01",
            "ruleVersion": "5.0.0",
            "adapterVersion": "5.0.0",
            "documentRefs": [docref],
            **props,
        }
        edges.append({**body, "evidenceId": "assert-" + digest(body)[:32]})

    records = sources["logistics"]["records"]
    for row in records["assets"]:
        if row["externalSystem"] != "atcis":
            raise ValueError("unsupported asset registration source")
        start = "logistics:asset:" + row["assetId"]
        end = "atcis:equipment:" + row["externalId"]
        if row.get("validTo") and row["validTo"] <= row["validFrom"]:
            raise ValueError("invalid identity period")
        link(
            "SAME_AS",
            start,
            end,
            "logistics",
            "asset",
            row["assetId"],
            validFrom=row["validFrom"],
            validTo=row.get("validTo"),
            registrationId=row["registrationId"],
        )
    for row in records["work-orders"]:
        start = "logistics:work-order:" + row["workOrderId"]
        link(
            "MAINTAINS",
            start,
            "logistics:asset:" + row["assetId"],
            "logistics",
            "work-order",
            row["workOrderId"],
        )
        for req in row["requirements"]:
            if req["quantity"] <= 0 or req["unit"] != "EA":
                raise ValueError("invalid required quantity/unit")
            part = next(p for p in records["parts"] if p["partId"] == req["partId"])
            if row["assetId"] not in part["applicableAssets"]:
                raise ValueError("incompatible part")
            link(
                "REQUIRES",
                start,
                "logistics:part:" + req["partId"],
                "logistics",
                "work-order",
                row["workOrderId"],
                quantity=req["quantity"],
                unit=req["unit"],
            )
    for row in records["inventory"]:
        link(
            "STOCK_OF",
            "logistics:inventory:" + row["inventoryId"],
            "logistics:part:" + row["partId"],
            "logistics",
            "inventory",
            row["inventoryId"],
        )
    for row in records["reservations"]:
        start = "logistics:reservation:" + row["reservationId"]
        link(
            "RESERVES",
            start,
            "logistics:inventory:" + row["inventoryId"],
            "logistics",
            "reservation",
            row["reservationId"],
        )
        link(
            "FOR_WORK",
            start,
            "logistics:work-order:" + row["workOrderId"],
            "logistics",
            "reservation",
            row["reservationId"],
        )
    for row in records["supply-requests"]:
        start = "logistics:supply-request:" + row["requestId"]
        link(
            "FOR_WORK",
            start,
            "logistics:work-order:" + row["workOrderId"],
            "logistics",
            "supply-request",
            row["requestId"],
        )
        link(
            "FULFILLED_BY",
            start,
            "logistics:cargo:" + row["cargoId"],
            "logistics",
            "supply-request",
            row["requestId"],
        )
    for row in records["cargo"]:
        start = "logistics:cargo:" + row["cargoId"]
        link(
            "CARRIED_BY",
            start,
            "knccs:transport:" + row["transportId"],
            "logistics",
            "cargo",
            row["cargoId"],
        )
        link(
            "CONTAINS_PART",
            start,
            "logistics:part:" + row["partId"],
            "logistics",
            "cargo",
            row["cargoId"],
        )
