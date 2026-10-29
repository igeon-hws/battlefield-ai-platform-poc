"""v6 business queries: declared definitions executed over verified graph links and pinned
source records. Expected values are written independently from tests/fixtures seeds."""

import json
from pathlib import Path

import pytest
from test_logistics_v5 import exports_v5


@pytest.fixture
def model(monkeypatch, tmp_path):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    monkeypatch.setenv("C4I_ONTOLOGY_PROFILE", "6")
    monkeypatch.setenv("FABRIC_KNOWLEDGE_STORE", str(tmp_path / "store"))
    from battlefield_ontology.domain import build_domain
    from semantic_core.knowledge import KnowledgeCatalog

    catalog = KnowledgeCatalog()
    built = build_domain(exports_v5(), catalog.documents, catalog.manifest())
    exports = exports_v5()
    info = {
        "graphVersion": "test",
        "ontologyVersion": "5.0.0",
        "mappingVersion": "5.0.0",
        "resolutionRuleVersion": "5.0.0",
        "inputStableHashes": {},
        "inputSnapshotSet": {
            s: {"snapshotId": exports[s]["snapshotId"], "sourceTime": exports[s]["sourceTime"]}
            for s in exports
        },
        "knowledgeSetVersion": catalog.version,
    }
    snapshots = {}
    for system in ("atcis", "knccs", "logistics"):
        seed = json.loads(
            Path(f"tests/fixtures/c2-logistics-demo-v5/{system}.json").read_text(encoding="utf-8")
        )
        snapshots[system] = {
            **seed,
            "systemId": system,
            "snapshotId": exports[system]["snapshotId"],
        }
    return info, built["nodes"], built["edges"], snapshots


def run(model, query_id, params, declaration=None):
    from semantic_core.business_queries import run_business_query

    info, nodes, edges, snapshots = model
    return run_business_query(info, nodes, edges, snapshots, query_id, params, declaration)


def test_availability_summary_applies_declared_policy_and_keeps_status(model):
    result = run(model, "asset-availability-summary", {"unit": "D1", "kind": "tank"})
    items = {i["nativeId"]: i for i in result["items"]}
    assert set(items) == {"L-T01", "L-T02"}
    assert items["L-T01"]["status"] == "available"
    assert items["L-T02"]["status"] == "limited"
    assert items["L-T02"]["limitation"]
    assert result["policy"]["defaultAvailablePolicy"] == "P1"
    assert result["counts"]["available"] == 1
    assert result["counts"]["byStatus"] == {"available": 1, "limited": 1}
    assert result["declarationVersion"] == "6.0.0-r1"
    assert {r["ruleId"] for r in result["appliedRules"]} >= {
        "FORCE-SCOPE-01",
        "AVAIL-LAND-01",
        "AGGREGATION-POLICY-01",
    }
    assert result["graphEvidence"] and all(e["evidenceId"] for e in result["graphEvidence"])
    assert {r["nativeId"] for r in result["sourceRecords"]} >= {"L-T01", "L-T02"}
    assert result["completeness"] == "complete"
    info = model[0]
    # The platform rejects Semantic responses without the run's graph stamps.
    for key in ("graphVersion", "inputStableHashes", "ontologyVersion", "mappingVersion"):
        assert result[key] == info[key]
    assert result["resolutionRuleVersion"] == info["resolutionRuleVersion"]


def test_published_policy_change_moves_only_the_available_count(model):
    from battlefield_ontology.declaration import apply_edits, load_base

    changed = apply_edits(
        load_base(), {"rules.AGGREGATION-POLICY-01.definition.defaultAvailablePolicy": "P2"}
    )
    result = run(model, "asset-availability-summary", {"unit": "D1", "kind": "tank"}, changed)
    assert result["counts"]["available"] == 2
    assert result["counts"]["byStatus"] == {"available": 1, "limited": 1}
    assert result["declarationVersion"] == "6.0.0-r2"


def test_joint_support_counted_once_and_unknown_preserved(model):
    division = run(model, "asset-availability-summary", {"unit": "모의 1사단"})
    assert {i["nativeId"] for i in division["items"]} == {
        "L-T01",
        "L-T02",
        "L-V01",
        "L-C01",
        "L-U01",
    }
    support = next(i for i in division["items"] if i["nativeId"] == "L-U01")
    assert support["support"] is True
    fleet = run(model, "asset-availability-summary", {"unit": "F1"})
    statuses = {i["nativeId"]: i["status"] for i in fleet["items"]}
    assert statuses == {"N-S01": "available", "N-S02": "unknown", "L-U01": "available"}
    assert fleet["counts"]["byStatus"]["unknown"] == 1
    assert fleet["unknowns"]


def test_unknown_unit_is_unresolved_not_zero(model):
    result = run(model, "asset-availability-summary", {"unit": "없는 부대"})
    assert result["status"] == "unresolved"
    assert result["counts"] is None


def test_maintenance_chain_from_land_equipment(model):
    result = run(model, "asset-maintenance-chain", {"systemId": "atcis", "nativeId": "L-T02"})
    assert result["identity"]["logisticsAssets"] == ["EQ-781"]
    assert result["owner"]["unitCode"] == "C111"
    assert result["owner"]["ancestors"] == ["B11", "D1"]
    work = {w["workOrderId"]: w for w in result["workOrders"]}
    assert set(work) == {"M-17"}
    part = work["M-17"]["parts"][0]
    assert part["partId"] == "P-08" and part["required"] == 2
    assert part["reservedForThisWork"] == 0
    assert part["unreservedAvailable"] == 1
    assert part["incoming"] == [
        {
            "requestId": "REQ-01",
            "cargoId": "C-12",
            "transportId": "N-21",
            "quantity": 1,
            "deliveryAt": "2026-10-21T11:00:00Z",
            "status": "EN_ROUTE",
        }
    ]
    assert part["reservedForOtherWork"] == [
        {"reservationId": "RES-01", "workOrderId": "M-18", "quantity": 1}
    ]
    forecast = work["M-17"]["conditionalForecast"]
    assert forecast["earliestCompletion"] == "2026-10-21T15:00:00Z"
    assert forecast["assumptions"]
    assert work["M-17"]["currentNativeState"] == "PMC"
    assert any(e["kind"] == "SAME_AS" for e in result["graphEvidence"])
    assert any(r["ruleId"] == "LOG-LINK-01" for r in result["appliedRules"])


def test_chain_with_missing_part_record_is_not_forecast(model):
    result = run(model, "asset-maintenance-chain", {"systemId": "logistics", "nativeId": "EQ-782"})
    work = {w["workOrderId"]: w for w in result["workOrders"]}
    assert work["M-18"]["conditionalForecast"]["earliestCompletion"] is None
    assert any("P-09" in u for u in result["unknowns"])


def test_part_supply_status_separates_reserved_unreserved_and_incoming(model):
    result = run(model, "part-supply-status", {"partId": "P-08"})
    stock = result["warehouses"][0]
    assert (stock["warehouseId"], stock["onHand"], stock["reserved"], stock["unreserved"]) == (
        "WH-1",
        2,
        1,
        1,
    )
    assert stock["reservations"] == [
        {"reservationId": "RES-01", "workOrderId": "M-18", "quantity": 1}
    ]
    assert {(r["workOrderId"], r["quantity"]) for r in result["requiredBy"]} == {
        ("M-17", 2),
        ("M-18", 1),
    }
    assert [i["cargoId"] for i in result["incoming"]] == ["C-12"]


def test_unknown_query_and_missing_params_are_rejected(model):
    with pytest.raises(KeyError):
        run(model, "no-such-query", {})
    with pytest.raises(ValueError, match="unit"):
        run(model, "asset-availability-summary", {})


def test_claim_citing_business_query_verifies_rule_refs(model):
    # A claim citing only this evidence previously lost AGGREGATION-POLICY-01 and the whole
    # answer was downgraded to partial; the query result now carries structured rule ids.
    from platform_api.agent.provenance import rule_ids

    result = run(model, "asset-availability-summary", {"unit": "D1", "kind": "tank"})
    assert {"FORCE-SCOPE-01", "AVAIL-LAND-01", "AGGREGATION-POLICY-01"} <= rule_ids(result)


def test_availability_explains_steps_exclusions_and_graph(model):
    # The analysis view renders these deterministically; the model writes none of it.
    result = run(model, "asset-availability-summary", {"unit": "D1", "kind": "tank"})
    steps = result["steps"]
    assert [s["title"] for s in steps] == [
        "범위 정하기",
        "장비 모으기",
        "유형 거르기",
        "상태 판정",
        "가용 집계",
    ]
    assert [s["count"] for s in steps] == [3, 5, 2, 2, 1]
    assert steps[0]["ruleIds"] == ["FORCE-SCOPE-01"]
    assert set(steps[0]["nodeKeys"]) == {"atcis:unit:D1", "atcis:unit:B11", "atcis:unit:C111"}
    assert "모의 1사단" in steps[0]["detail"]
    assert "L-T02 PMC → 제한" in steps[3]["detail"]
    assert "P1" in steps[4]["detail"] and "1대" in steps[4]["detail"]
    excluded = {e["nativeId"]: e for e in result["excluded"]}
    assert set(excluded) == {"L-V01", "L-C01", "L-U01"}
    assert all(e["ruleId"] == "ASSET-TYPE-01" and e["step"] == 3 for e in excluded.values())
    assert "전차 아님" in excluded["L-V01"]["reason"]
    nodes = {n["key"]: n for n in result["graphNodes"]}
    assert nodes["atcis:unit:D1"]["name"] == "모의 1사단"
    assert nodes["atcis:unit:D1"]["concept"] == "부대"
    assert nodes["atcis:equipment:L-T01"]["state"] == "available"
    assert nodes["atcis:equipment:L-T02"]["state"] == "limited"
    assert nodes["atcis:equipment:L-V01"]["state"] == "excluded"
    # Every edge endpoint has a display node; labels come from the declaration.
    assert {k for e in result["graphEvidence"] for k in (e["start"], e["end"])} <= set(nodes)
    assert result["relationLabels"]["SUBORDINATE_TO"] == "예하"
    assert result["roleLabels"]["ATT"] == "배속"


def test_availability_steps_follow_published_policy(model):
    from battlefield_ontology.declaration import apply_edits, load_base

    changed = apply_edits(
        load_base(), {"rules.AGGREGATION-POLICY-01.definition.defaultAvailablePolicy": "P2"}
    )
    result = run(model, "asset-availability-summary", {"unit": "D1", "kind": "tank"}, changed)
    last = result["steps"][-1]
    assert last["count"] == 2 and "P2" in last["detail"] and "2대" in last["detail"]


def test_maintenance_chain_explains_allocation_and_forecast(model):
    result = run(model, "asset-maintenance-chain", {"systemId": "atcis", "nativeId": "L-T02"})
    titles = [s["title"] for s in result["steps"]]
    assert titles == ["동일 장비 연결", "소속 확인", "정비 작업", "부품 확보", "완료 전망"]
    assert "EQ-781" in result["steps"][0]["detail"]
    assert "15:00" in result["steps"][4]["detail"]
    reserved = next(e for e in result["excluded"] if e["nativeId"] == "RES-01")
    assert "M-18" in reserved["reason"] and reserved["step"] == 4
    nodes = {n["key"] for n in result["graphNodes"]}
    assert {k for e in result["graphEvidence"] for k in (e["start"], e["end"])} <= nodes


def test_part_supply_explains_steps(model):
    result = run(model, "part-supply-status", {"partId": "P-08"})
    assert [s["title"] for s in result["steps"]] == ["창고 재고", "작업 수요", "입고 예정"]
    assert "WH-1" in result["steps"][0]["detail"]
    assert result["excluded"] == []
