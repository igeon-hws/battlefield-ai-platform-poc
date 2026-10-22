from uuid import uuid4

import pytest
from test_domain_semantics import exports
from test_neo4j import graph  # noqa: F401 - dedicated Neo4j fixture

pytestmark = pytest.mark.neo4j


def test_domain_graph_publishes_typed_nodes_proof_and_native_scope(graph):  # noqa: F811 - fixture
    from semantic_core.domain import DomainService

    version = "test-domain-" + uuid4().hex
    try:
        info = graph.build(exports(), graph_version=version)
        assert info["ontologyVersion"] == "3.0.0" and info["status"] == "READY"
        service = DomainService(graph)
        scope = service.resolve_unit_scope(version, "모의 1사단")
        assert len(scope["unitIds"]) == 3
        refs = service.find_equipment_refs(version, scope["unitIds"], "tank")
        assert {r["canonicalId"] for r in refs["items"]} == {
            "atcis:equipment:L-T01",
            "atcis:equipment:L-T02",
        }
        resolved = service.resolve_entity(version, "knccs", "NORTH/007")
        assert resolved["canonicalId"] == "atcis:equipment:L-V01"
        assert resolved["kind"] == "armored_vehicle"
        assert resolved["classificationRule"]["documentRefs"]
        assert service.resolve_entity(version, "knccs", "SOUTH/007")["status"] == "unresolved"
        evidence = service.get_semantic_evidence(version, resolved["evidenceRefs"][0])
        assert evidence["assertion"]["documentRefs"]
        relations = service.query_relations(version, "atcis:report:R2", ["DERIVED_FROM"], 2, 100)
        assert any(e["end"] == "atcis:report:R1" for e in relations["items"])
        rules = service.get_procedure_definition(version, "SOP-01")
        assert rules["rules"][0]["definition"]["closure"] == "all_steps_have_completion_evidence"
        assert graph.build(exports(), graph_version=version)["graphVersion"] == version
    finally:
        graph.remove_test_build(version)


def test_expired_support_and_truncated_scope_are_not_complete_membership(graph):  # noqa: F811 - fixture
    from semantic_core.domain import DomainService

    sources = exports()
    sources["knccs"]["records"]["relations"][1]["until"] = "2026-10-20T09:05:00Z"
    version = "test-domain-" + uuid4().hex
    try:
        graph.build(sources, graph_version=version)
        service = DomainService(graph)
        navy = service.resolve_unit_scope(version, "모의 1함대")
        refs = service.find_equipment_refs(version, navy["unitIds"])
        assert {e["canonicalId"] for e in refs["items"]} == {
            "knccs:equipment:N-S01",
            "knccs:equipment:N-S02",
        }
        assert service.resolve_unit_scope(version, "모의 1사단", 0)["completeness"] == "partial"
        proof = service.query_relations(version, "atcis:equipment:L-U01", ["ASSIGNED_TO"], 0, 1)
        assert proof["completeness"] == "partial"
    finally:
        graph.remove_test_build(version)
