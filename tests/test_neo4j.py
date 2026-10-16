import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from semantic_core.graph import GraphRepository

pytestmark = pytest.mark.neo4j


@pytest.fixture
def graph():
    load_dotenv()
    repo = GraphRepository(
        os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687"), "neo4j", os.environ["NEO4J_PASSWORD"]
    )
    repo.verify()
    repo.ensure_schema()
    yield repo
    repo.close()


def fixture_sources():
    return json.loads(
        (Path(__file__).parent / "fixtures/semantic-demo-v1/sources.json").read_text(
            encoding="utf-8"
        )
    )


def test_real_graph_build_is_versioned_evidenced_and_idempotent(graph):
    version = "test-" + uuid4().hex
    sources = fixture_sources()
    try:
        first = graph.build(sources, graph_version=version)
        assert first["status"] == "READY"
        assert graph.build(sources, graph_version=version)["graphVersion"] == version
        model = graph.model(version)
        assert len(model["equipment"]) == 8
        assert len(model["units"]) == 6
        scope = graph.unit_scope(version, "모의 1사단")
        assert len(scope["unitIds"]) == 3
        refs = graph.equipment_refs(version, scope["unitIds"], "tank")
        assert len(refs["items"]) == 4
        assert all(i["sourceRefs"] and i["evidenceRefs"] for i in refs["items"])
        evidence = graph.evidence(version, refs["items"][0]["evidenceRefs"][0])
        assert evidence["sourceRefs"] and evidence["ruleId"]
        assert "payloadJson" in evidence
        assert evidence["sourceSnapshotRefs"]
        assert all(
            "availability" not in json.dumps(e) and "position" not in json.dumps(e)
            for e in model["equipment"]
        )
        resolved = graph.resolve_entity(version, "atcis", "U-A01")
        assert resolved["status"] == "resolved" and resolved["canonicalId"] == "EX-U01"
        assert len(resolved["sourceRefs"]) == 2
        with pytest.raises(KeyError):
            graph.model("nonexistent")
    finally:
        graph.remove_test_build(version)


def test_invalid_build_never_replaces_active_and_inputs_are_immutable(graph):
    good, bad = "test-" + uuid4().hex, "test-" + uuid4().hex
    sources = fixture_sources()
    try:
        graph.build(sources, graph_version=good)
        invalid = deepcopy(sources)
        invalid["atcis"]["units"][0]["parentId"] = "C111"
        with pytest.raises(ValueError, match="cycle"):
            graph.build(invalid, graph_version=bad)
        assert graph.active_version() == good
        assert graph.build_info(bad)["status"] == "FAILED"
        changed = deepcopy(sources)
        changed["atcis"]["equipment"][0]["unitId"] = "D2"
        with pytest.raises(ValueError, match="immutable"):
            graph.build(changed, graph_version=good)
        assert graph.build_info(good)["status"] == "READY"
    finally:
        graph.remove_test_build(good)
        graph.remove_test_build(bad)
