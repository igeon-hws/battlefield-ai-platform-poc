"""Business views preserve source facts, units and knowledge boundaries."""

import json
from pathlib import Path

import pytest


def test_metadata_is_the_same_reviewed_document_available_to_b(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    from semantic_core.knowledge import KnowledgeCatalog
    from semantic_core.metadata import MetadataCatalog

    knowledge = KnowledgeCatalog()
    metadata = MetadataCatalog(knowledge.version)
    body = knowledge.document(knowledge.version, "fabric:DISPLAY-01")
    assert metadata.public()["fields"] == json.loads(body["document"]["text"])["fields"]
    duration = metadata.field("logistics", "work-orders", "laborHours")
    assert duration["unit"] == "h" and duration["quantityKind"] == "elapsed_time"
    assert duration["displayName"] == "정비 소요 시간"
    assert duration["sourceSchemaVersion"] == "5.0.0"
    assert duration["validFrom"] == "2026-10-20T00:00:00Z"
    assert duration["validTo"] is None
    assert metadata.value("atcis", "equipment", "maintenanceCode", "PMC") == "운용 제한"
    assert metadata.value("atcis", "equipment", "maintenanceCode", "NEW") == "미확인"


def test_business_summary_groups_work_and_supply_without_changing_facts(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    from semantic_core.business import business_summary
    from semantic_core.knowledge import KnowledgeCatalog
    from semantic_core.metadata import MetadataCatalog

    records = []
    for system in ("atcis", "logistics", "knccs"):
        raw = json.loads(
            Path(f"tests/fixtures/c2-logistics-demo-v5/{system}.json").read_text(encoding="utf-8")
        )
        for resource, rows in raw["records"].items():
            for r in rows:
                records.append(
                    {
                        "systemId": system,
                        "recordType": {
                            "work-orders": "work-order",
                            "assets": "asset",
                            "parts": "part",
                            "transports": "transport",
                        }.get(resource, resource),
                        "record": r,
                        "sourceTime": raw["sourceTime"],
                        "lastReceivedAt": "2026-10-28T00:00:00Z",
                    }
                )
    summary = business_summary(
        records, MetadataCatalog(KnowledgeCatalog().version), "atcis", "equipment", "L-T02"
    )
    assert summary["asset"]["status"] == "운용 제한"
    assert summary["maintenance"][0]["status"] == "부품 대기"
    assert summary["maintenance"][0]["durationUnit"] == "h"
    assert summary["maintenance"][0]["durationHours"] == 4
    assert summary["transport"][0]["id"] == "N-21"
    assert len(summary["maintenance"]) == 1
    assert summary["sourceTimes"] and summary["queriedAt"]


def test_unrecognized_review_revision_is_not_silently_used(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    import semantic_core.metadata as module
    from semantic_core.knowledge import KnowledgeCatalog

    catalog = KnowledgeCatalog()
    doc = catalog.document(catalog.version, "fabric:DISPLAY-01")
    payload = json.loads(doc["document"]["text"])
    payload["reviewRevision"] = "unreviewed"
    doc["document"]["text"] = json.dumps(payload)
    monkeypatch.setattr(catalog, "document", lambda *_: doc)
    monkeypatch.setattr(module, "KnowledgeCatalog", lambda *_: catalog)
    with pytest.raises(ValueError, match="review revision"):
        module.MetadataCatalog(catalog.version)
