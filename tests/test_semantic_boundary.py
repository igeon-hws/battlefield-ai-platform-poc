"""Behavior checks for the S8 execution boundary, not import-string assertions."""

import json
from pathlib import Path

import httpx
import pytest
from platform_api.agent.multi_tools import MultiToolRunner
from test_semantic_agent import Source, snapshots


def forbidden(*args, **kwargs):
    raise AssertionError("Semantic interpretation executed in OFF")


async def test_off_raw_count_and_geometry_never_interpret_equipment(monkeypatch):
    import platform_api.agent.multi_tools as module

    monkeypatch.setattr(module, "normalize_equipment", forbidden, raising=False)
    monkeypatch.setattr(module, "resolve_identity", forbidden, raising=False)
    runner = MultiToolRunner({s: Source(s) for s in ("atcis", "knccs")}, snapshots(), "off")
    a = await runner.execute("atcis__list_equipment", {})
    k = await runner.execute("knccs__list_equipment", {})
    result = await runner.execute(
        "aggregate_evidence", {"evidenceIds": [a["evidenceId"], k["evidenceId"]]}
    )
    assert result["data"]["rawRecordCount"] == 9
    assert result["data"]["interpretation"] == "native_records_only"
    assert "resolvedUniqueCount" not in result["data"]
    assert "confirmedAvailable" not in result["data"]
    for raw in a["data"]["items"]:
        raw["pos"] = {"lon": 127.0, "lat": 37.0}
    distance = await runner.execute(
        "geo_measure",
        {"evidenceId": a["evidenceId"], "firstEntityId": "T-A01", "secondEntityId": "T-A02"},
    )
    assert distance["data"]
    with pytest.raises(ValueError, match="semantic.*off"):
        await runner.execute(
            "aggregate_evidence",
            {"evidenceIds": [a["evidenceId"]], "identityEvidenceIds": [a["evidenceId"]]},
        )


async def test_native_source_query_does_not_execute_semantic_mapping(tmp_path, monkeypatch):
    import battlefield_source_runtime.app as module
    from mock_atcis.app import create_app

    monkeypatch.setenv("ATCIS_DB", str(tmp_path / "a.db"))
    app = create_app(tick_enabled=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        snap = (await client.get("/api/v1/snapshot")).json()
        from copy import deepcopy

        legacy = deepcopy(snap)
        legacy["datasetId"] = "semantic-demo-v1"
        for raw in legacy["tracks"]:
            raw.pop("assignmentRole", None)
        assert all(
            "assignmentRole" not in row for row in app.state.store.export(legacy)["equipment"]
        )
        monkeypatch.setattr(module, "normalize_equipment", forbidden)
        response = await client.get(
            "/api/v1/equipment",
            params={"snapshotId": snap["snapshotId"], "typeCode": "TANK", "statusCode": "R"},
        )
        assert response.status_code == 200
        assert {r["trackKey"] for r in response.json()["items"]} == {"T-A01", "T-A02", "T-A05"}
        summary = await client.get(
            "/api/v1/equipment-summary", params={"snapshotId": snap["snapshotId"]}
        )
        assert summary.status_code == 200
        assert "TANK" in summary.json()["counts"]


def test_v2_default_shared_equipment_is_consistent():
    root = Path(__file__).resolve().parents[1]
    a, k = [
        json.loads(
            (root / f"services/mock-{s}/src/mock_{s}/scenario.json").read_text(encoding="utf-8")
        )
        for s in ("atcis", "knccs")
    ]
    assert a["datasetId"] == k["datasetId"] == "semantic-demo-v2"
    u = next(r for r in a["tracks"] if r["trackKey"] == "U-A01")
    v = next(r for r in k["contacts"] if r["contactNo"] == "C-K77")
    assert u["readyCode"] == "R" and v["serviceability"] == "READY"
    assert u["assignmentRole"] == v["assignmentRole"] == "shared_support"
    from battlefield_ontology import normalize_equipment

    ground, sea = normalize_equipment("atcis", u), normalize_equipment("knccs", v)
    assert ground.position == sea.position
    assert ground.kind == sea.kind and ground.affiliation == sea.affiliation
    assert ground.velocity["eastMps"] == pytest.approx(sea.velocity["eastMps"])
    assert ground.velocity["northMps"] == pytest.approx(sea.velocity["northMps"])


def test_semantic_concept_supplies_versioned_source_interpretation():
    from semantic_core.service import SemanticService

    class Repo:
        def require_ready(self, version):
            return {
                "ontologyVersion": "2.0.0",
                "mappingVersion": "2.0.0",
                "resolutionRuleVersion": "1.0.0",
                "inputStableHashes": {},
            }

    result = SemanticService(Repo()).interpret_concept("g", "가용")
    assert result["sourceMappings"]["atcis"]["availabilityValues"]["R"] == "available"
    assert result["sourceMappings"]["knccs"]["availabilityValues"]["READY"] == "available"
    assert result["mappingRule"]["ruleId"] == "SOURCE-CODE-INTERPRETATION"
    unknown = SemanticService(Repo()).interpret_concept("g", "not-a-concept")
    assert unknown["status"] == "unresolved" and "availability" in unknown["supportedTerms"]
    assert SemanticService(Repo()).interpret_concept("g", "availability")["status"] == "resolved"


async def test_old_policy_conversation_cannot_seed_new_off_context(tmp_path):
    from platform_api.multi_repository import MultiRepository

    repo = MultiRepository(tmp_path / "platform.db")
    await repo.open()
    try:
        old = await repo.enqueue("previous", "off")
        await repo.update_run(old["runId"], {"status": "completed", "semanticPolicyVersion": "1"})
        with pytest.raises(ValueError, match="policy"):
            await repo.enqueue("follow up", "off", old["conversationId"])
    finally:
        await repo.close()


async def test_empty_evidence_error_explains_snapshot_ids_are_not_evidence():
    runner = MultiToolRunner({"atcis": Source("atcis")}, snapshots(), "off")
    with pytest.raises(ValueError, match="snapshotId is not evidenceId"):
        await runner.execute("read_evidence", {"evidenceId": snapshots()["atcis"]["snapshotId"]})


async def test_queued_old_policy_run_is_not_silently_upgraded(tmp_path):
    from platform_api.multi_repository import MultiRepository
    from platform_api.multi_runtime import MultiRuntime

    repo = MultiRepository(tmp_path / "platform.db")
    await repo.open()
    try:
        run = await repo.enqueue("old pending", "off")
        await repo.update_run(run["runId"], {"semanticPolicyVersion": "1"})
        await MultiRuntime(repo, None, {}, {}).execute_run(await repo.get_run(run["runId"]))
        interrupted = await repo.get_run(run["runId"])
        assert interrupted["status"] == "interrupted" and "policy" in interrupted["error"]
        assert interrupted["semanticPolicyVersion"] == "1"
        comparison = await repo.create_comparison("old preparing")
        await repo.update_comparison(
            comparison["comparisonId"],
            {"manifest": {"semanticPolicyVersion": "1", "sourceSnapshotSet": {}}},
        )
        await MultiRuntime(repo, None, {}, {}).prepare_comparison(
            await repo.comparison(comparison["comparisonId"])
        )
        assert "policy" in (await repo.comparison(comparison["comparisonId"]))["error"]
    finally:
        await repo.close()


def test_old_graph_is_readable_but_not_reinterpreted_with_new_rules():
    from semantic_core.service import SemanticService

    class OldRepo:
        def require_ready(self, version):
            return {"ontologyVersion": "1.0.0", "mappingVersion": "1.0.0"}

    with pytest.raises(ValueError, match="version"):
        SemanticService(OldRepo()).interpret_concept("old", "availability")


def test_on_arithmetic_requires_semantic_identity_and_all_observations():
    from platform_api.agent.calculation import semantic_count
    from platform_api.agent.multi_tools import AggregateArgs
    from semantic_core.service import SOURCE_MAPPINGS

    records = {
        ("atcis", "U-A01"): ({"readyCode": "R", "ownerUnitCode": "B11"}, ["a"]),
        ("knccs", "C-K77"): ({"serviceability": "READY", "orgRef": "S11"}, ["k"]),
    }
    identity = {
        "systemId": "semantic",
        "originalTool": "resolve_entity",
        "data": {
            "canonicalId": "EX-U01",
            "status": "resolved",
            "sourceRefs": [{"systemId": s, "nativeId": n} for s, n in records],
        },
    }
    concept = {
        "systemId": "semantic",
        "originalTool": "interpret_concept",
        "data": {"status": "resolved", "sourceMappings": SOURCE_MAPPINGS},
    }
    args = AggregateArgs(evidence_ids=["a", "k"])
    result = semantic_count(records, args, [identity], [], [concept])
    assert result["rawRecordCount"] == 2 and result["resolvedUniqueCount"] == 1
    assert result["confirmedAvailable"] == 1 and result["conflicting"] == 0
    with pytest.raises(ValueError, match="coverage"):
        semantic_count(
            {("atcis", "U-A01"): records[("atcis", "U-A01")]}, args, [identity], [], [concept]
        )
    with pytest.raises(ValueError, match="Semantic evidence"):
        semantic_count(records, args, [{**identity, "systemId": "atcis"}], [], [concept])
    with pytest.raises(ValueError, match="unresolved"):
        semantic_count(
            records,
            args,
            [{**identity, "data": {**identity["data"], "status": "conflict"}}],
            [],
            [concept],
        )
    negative = {**records, ("knccs", "C-K77"): ({"serviceability": "NOT_READY"}, ["k"])}
    assert semantic_count(negative, args, [identity], [], [concept])["conflicting"] == 1
    with pytest.raises(ValueError, match="kind proof"):
        semantic_count(
            records, AggregateArgs(evidence_ids=["a", "k"], kind="uav"), [identity], [], [concept]
        )
    empty = {
        "systemId": "semantic",
        "originalTool": "find_equipment_refs",
        "data": {"items": [], "matchedCount": 0, "complete": True, "nextCursor": None},
    }
    assert semantic_count({}, args, [empty], [], [concept])["resolvedUniqueCount"] == 0


def test_semantic_reference_pagination_requires_complete_combined_pages():
    from platform_api.agent.calculation import semantic_count
    from platform_api.agent.multi_tools import AggregateArgs
    from semantic_core.service import SOURCE_MAPPINGS

    records = {
        ("atcis", "a"): ({"readyCode": "R"}, ["a"]),
        ("atcis", "b"): ({"readyCode": "N"}, ["b"]),
    }
    pages = [
        {
            "systemId": "semantic",
            "originalTool": "find_equipment_refs",
            "arguments": {"unitIds": ["atcis:D1"], "cursor": i},
            "data": {
                "items": [
                    {
                        "canonicalId": n,
                        "identityStatus": "resolved",
                        "sourceRefs": [{"systemId": "atcis", "nativeId": n}],
                    }
                ],
                "matchedCount": 2,
                "nextCursor": 1 if i == 0 else None,
                "complete": i == 1,
            },
        }
        for i, n in enumerate(("a", "b"))
    ]
    concept = {
        "systemId": "semantic",
        "originalTool": "interpret_concept",
        "data": {"status": "resolved", "sourceMappings": SOURCE_MAPPINGS},
    }
    args = AggregateArgs(evidence_ids=["a", "b"])
    with pytest.raises(ValueError, match="incomplete"):
        semantic_count(records, args, pages[:1], [], [concept])
    assert semantic_count(records, args, pages, [], [concept])["resolvedUniqueCount"] == 2


def test_old_snapshot_stable_hash_does_not_gain_absent_role_fields():
    from battlefield_ontology import stable_payload

    old = {
        "systemId": "atcis",
        "datasetId": "semantic-demo-v1",
        "epochId": "old-epoch",
        "units": [],
        "equipment": [{"nativeId": "a", "unitId": None, "kind": "tank", "exerciseAssetRef": "A"}],
    }
    assert stable_payload(old) == old
