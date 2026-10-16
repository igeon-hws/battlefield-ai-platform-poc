import json
from pathlib import Path

import pytest
from battlefield_ontology import build_model, resolve_identity, unit_scope

FIXTURES = Path(__file__).parent / "fixtures" / "semantic-demo-v1"


def test_fixture_gold_is_independent_and_scope_uses_relations():
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
    model = build_model(sources)
    scope = unit_scope(model, "모의 1사단")
    assert set(scope["unitIds"]) == {"atcis:D1", "atcis:B11", "atcis:C111"}
    tanks = [
        e
        for e in model["equipment"]
        if e["kind"] == "tank" and any(a["unitId"] in scope["unitIds"] for a in e["assignments"])
    ]
    assert sorted(e["canonicalId"] for e in tanks) == expected["s1"]["allTankIds"]
    available = sorted(
        e["canonicalId"]
        for e in tanks
        if {o["availability"] for o in e["observations"]} == {"available"}
    )
    assert available == expected["s1"]["availableIds"]
    assert len(model["equipment"]) == 8  # Includes the out-of-scope T05.
    assert all(
        a["ruleId"] and a["sourceRefs"] for e in model["equipment"] for a in e["assignments"]
    )
    union = set(scope["unitIds"]) | set(unit_scope(model, "모의 1함대")["unitIds"])
    equipment = [
        e for e in model["equipment"] if any(a["unitId"] in union for a in e["assignments"])
    ]
    assert len(equipment) == expected["s2"]["uniqueCount"]
    assert sum(len(e["observations"]) for e in equipment) == expected["s2"]["rawCount"]
    assert (
        sum({o["availability"] for o in e["observations"]} == {"available"} for e in equipment)
        == expected["s2"]["availableCount"]
    )
    shared = next(e for e in equipment if e["canonicalId"] == "EX-U01")
    assert {o["availability"] for o in shared["observations"]} == {"available", "unavailable"}
    assert len(shared["assignments"]) == 2


def test_identity_requires_explicit_scoped_identifier_and_compatible_type():
    records = [
        {
            "systemId": "atcis",
            "datasetId": "d",
            "epochId": "e",
            "nativeId": "a",
            "kind": "uav",
            "exerciseAssetRef": "X",
        },
        {
            "systemId": "knccs",
            "datasetId": "d",
            "epochId": "e",
            "nativeId": "b",
            "kind": "uav",
            "exerciseAssetRef": "X",
        },
    ]
    assert resolve_identity(records)["status"] == "resolved"
    assert (
        resolve_identity([{**r, "exerciseAssetRef": None, "label": "same name"} for r in records])[
            "status"
        ]
        == "unresolved"
    )
    assert resolve_identity([records[0], {**records[1], "kind": "tank"}])["status"] == "conflict"
    assert (
        resolve_identity([records[0], {**records[1], "datasetId": "other"}])["status"] == "conflict"
    )
    assert (
        resolve_identity([records[0], {**records[1], "systemId": "atcis"}])["status"] == "conflict"
    )


def test_duplicate_names_require_clarification_and_cycles_are_rejected():
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    sources["atcis"]["units"].append({"unitId": "D9", "name": "모의 1사단", "parentId": None})
    assert unit_scope(build_model(sources), "모의 1사단")["status"] == "ambiguous"
    sources["atcis"]["units"][0]["parentId"] = "C111"
    with pytest.raises(ValueError, match="cycle"):
        build_model(sources)


def test_missing_parent_does_not_publish_a_fabricated_relationship():
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    sources["atcis"]["units"][1]["parentId"] = "NONEXISTENT"
    with pytest.raises(ValueError, match="missing"):
        build_model(sources)


def test_duplicate_native_record_keys_are_rejected_before_graph_generation():
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    sources["atcis"]["equipment"].append(
        {**sources["atcis"]["equipment"][0], "exerciseAssetRef": "OTHER"}
    )
    with pytest.raises(ValueError, match="duplicate"):
        build_model(sources)
