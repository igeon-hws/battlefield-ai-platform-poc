import json
from copy import deepcopy
from pathlib import Path

import pytest


def exports():
    result = {}
    for system in ("atcis", "knccs"):
        from importlib import import_module

        native = import_module(f"mock_{system}.native")
        seed = json.loads(
            (Path(__file__).parent / "fixtures/c2-domain-demo-v3" / f"{system}.json").read_text(
                encoding="utf-8"
            )
        )
        for doc in seed["records"]["documents"]:
            doc["hash"] = native.content_hash(doc)
        state = {
            **seed,
            "systemId": system,
            "epochId": "test-epoch",
            "snapshotId": "test-snapshot",
            "sequence": 1,
        }
        result[system] = native.stable(state)
        result[system]["sourceTime"] = state["sourceTime"]
    return result


def test_domain_model_preserves_contacts_and_verified_links_with_proof():
    from battlefield_ontology.domain import build_domain

    model = build_domain(exports())
    assert {
        "System",
        "SourceRecord",
        "Observation",
        "EquipmentType",
        "ConceptDefinition",
        "Procedure",
        "StepDefinition",
    } <= {n["label"] for n in model["nodes"]}
    assert len([n for n in model["nodes"] if n["label"] == "Equipment"]) == 7
    assert len([n for n in model["nodes"] if n["label"] == "Unit"]) == 5
    assert len([n for n in model["nodes"] if n["label"] == "ContactObservation"]) == 3
    links = [
        r
        for r in model["edges"]
        if r["kind"] == "REFERS_TO" and r["start"].startswith("knccs:contact:")
    ]
    assert {r["end"] for r in links} == {"atcis:equipment:L-U01", "atcis:equipment:L-V01"}
    assert all(r["ruleId"] and r["sourceRefs"] and r["documentRefs"] for r in links)
    serialized = json.dumps([n for n in model["nodes"] if n["label"] in ("Equipment", "Activity")])
    assert "maintenanceCode" not in serialized and '"engineering"' not in serialized


def test_entity_link_requires_explicit_mapping_and_correct_schema():
    from battlefield_ontology.domain import build_domain

    sources = exports()
    sources["knccs"]["records"]["associations"] = []
    assert not [
        e
        for e in build_domain(sources)["edges"]
        if e["kind"] == "REFERS_TO" and e["start"].startswith("knccs:contact:")
    ]
    bad = deepcopy(sources)
    bad["atcis"]["sourceSchemaVersion"] = "future"
    with pytest.raises(ValueError, match="schema"):
        build_domain(bad)


def test_rules_reference_exact_document_versions_and_no_live_values():
    from battlefield_ontology.domain import build_domain

    model = build_domain(exports())
    assert {"AVAIL-LAND-01", "AVAIL-NAVAL-01", "AGGREGATION-POLICY-01", "ACTIVITY-STEP-01"} <= {
        r["ruleId"] for r in model["rules"]
    }
    assert all(r["documentRefs"][0]["hash"] for r in model["rules"])
    bad = exports()
    bad["atcis"]["records"]["documents"][0]["hash"] = "tampered"
    with pytest.raises(ValueError, match="document hash"):
        build_domain(bad)


def test_future_reports_are_not_materialized_into_an_earlier_graph():
    from battlefield_ontology.domain import build_domain

    sources = exports()
    sources["atcis"]["records"]["reports"][-1]["knownAt"] = "2026-10-20T09:11:00Z"
    with pytest.raises(ValueError, match="future"):
        build_domain(sources)


def test_native_record_provenance_does_not_claim_unrelated_domain_rules():
    from battlefield_ontology.domain import build_domain

    model = build_domain(exports())
    origins = [e for e in model["edges"] if e["start"].startswith("source-record:")]
    assert origins
    assert all(e.get("provenanceKind") == "native_record_reference" for e in origins)
    assert all(e.get("adapterVersion") and e["sourceRefs"] for e in origins)
    assert not any(e.get("ruleId") for e in origins)
