"""v6 declarative ontology: one reviewed declaration renders B documents and compiles C."""

import copy
import json
from pathlib import Path

import pytest
from test_logistics_v5 import exports_v5


@pytest.fixture
def profile6(monkeypatch, tmp_path):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    monkeypatch.setenv("C4I_ONTOLOGY_PROFILE", "6")
    monkeypatch.setenv("FABRIC_KNOWLEDGE_STORE", str(tmp_path / "store"))
    return tmp_path


def base():
    from battlefield_ontology.declaration import load_base

    return load_base()


def test_declaration_schema_rejects_undefined_references_cycles_and_duplicates():
    from battlefield_ontology.declaration import validate

    validate(base())
    broken = base()
    broken["businessQueries"][0]["rules"].append("NO-SUCH-RULE")
    with pytest.raises(ValueError, match="undefined rule"):
        validate(broken)
    cyclic = base()
    rule = next(r for r in cyclic["rules"] if r["ruleId"] == "ORG-ROLE-01")
    rule["dependsOn"] = ["FORCE-SCOPE-01"]
    with pytest.raises(ValueError, match="cycle"):
        validate(cyclic)
    duplicate = base()
    duplicate["rules"].append(copy.deepcopy(duplicate["rules"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate(duplicate)
    relation = base()
    relation["businessQueries"][0]["relations"].append("NOT_A_RELATION")
    with pytest.raises(ValueError, match="undefined relation"):
        validate(relation)


def test_rendering_is_deterministic_and_states_every_rule_and_query():
    from battlefield_ontology.declaration import knowledge_item, render

    first, second = knowledge_item(base()), knowledge_item(base())
    assert first == second
    text = render(base())
    for rule in base()["rules"]:
        assert rule["ruleId"] in text
    for query in base()["businessQueries"]:
        assert query["queryId"] in text
    assert "기본 가용 집계 기준: P1" in text
    assert first["document"]["declaration"] == base()


def test_edits_are_limited_to_editable_paths_and_produce_impact():
    from battlefield_ontology.declaration import apply_edits, diff, impact

    path = "rules.AGGREGATION-POLICY-01.definition.defaultAvailablePolicy"
    changed = apply_edits(base(), {path: "P2"})
    assert changed["revision"] == base()["revision"] + 1
    assert diff(base(), changed) == [
        {
            "path": path,
            "label": "기본 가용 집계 기준",
            "before": "P1",
            "after": "P2",
        }
    ]
    result = impact(base(), changed)
    assert result == impact(base(), changed)
    assert result["rules"] == ["AGGREGATION-POLICY-01"]
    assert result["businessQueries"] == ["asset-availability-summary"]
    assert "availability-answer" in result["screens"]
    with pytest.raises(ValueError, match="not editable"):
        apply_edits(base(), {"rules.AVAIL-LAND-01.definition.default": "available"})
    with pytest.raises(ValueError, match="option"):
        apply_edits(base(), {path: "P3"})


def test_v6_base_knowledge_set_is_in_sync_with_declaration(profile6):
    from battlefield_ontology.declaration import knowledge_item
    from semantic_core.knowledge import KnowledgeCatalog

    catalog = KnowledgeCatalog()
    item = next(d for d in catalog.documents if d["documentKey"] == "fabric:ONTOLOGY-01")
    assert item == knowledge_item(base())
    assert KnowledgeCatalog(catalog.version).hash == catalog.hash
    assert {d["documentKey"] for d in catalog.documents} >= set(base()["sourceDocuments"])


def test_graph_compiles_declaration_rules_queries_and_parity(profile6):
    from battlefield_ontology.declaration import compiled_ids
    from battlefield_ontology.domain import build_domain
    from semantic_core.knowledge import KnowledgeCatalog

    catalog = KnowledgeCatalog()
    model = build_domain(exports_v5(), catalog.documents, catalog.manifest())
    labels = {n["label"] for n in model["nodes"]}
    assert {"OntologyDeclaration", "BusinessQuery"} <= labels
    rendered = compiled_ids(base())
    graph = {
        "rules": sorted(
            n["payload"]["ruleId"] for n in model["nodes"] if n["label"] == "InterpretationRule"
        ),
        "businessQueries": sorted(
            n["payload"]["queryId"] for n in model["nodes"] if n["label"] == "BusinessQuery"
        ),
    }
    assert graph == rendered
    rule = next(
        n["payload"]
        for n in model["nodes"]
        if n["label"] == "InterpretationRule" and n["payload"]["ruleId"] == "AVAIL-LAND-01"
    )
    assert any(ref.get("documentKey") == "fabric:ONTOLOGY-01" for ref in rule["documentRefs"])


def test_v6_interpret_concept_reads_declaration_terms(profile6):
    from battlefield_ontology.declaration import apply_edits
    from test_semantic_efficiency import semantic_service

    service = semantic_service()
    result = service.interpret_concept("test", "정비")
    assert result["selectedRuleIds"] == ["LOG-LINK-01"]
    assert result["declarationVersion"].startswith("6.0.0")
    assert apply_edits  # declaration edits never touch code-held term tables


def test_v5_default_catalog_is_unchanged_without_profile(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    monkeypatch.delenv("C4I_ONTOLOGY_PROFILE", raising=False)
    from semantic_core.knowledge import KnowledgeCatalog

    assert all(d["documentKey"] != "fabric:ONTOLOGY-01" for d in KnowledgeCatalog().documents)


def test_published_version_becomes_current_and_old_versions_stay_readable(profile6):
    from battlefield_ontology.declaration import apply_edits
    from semantic_core.knowledge import KnowledgeCatalog
    from semantic_core.ontology_store import OntologyStore

    store = OntologyStore()
    old = KnowledgeCatalog().version
    path = "rules.AGGREGATION-POLICY-01.definition.defaultAvailablePolicy"
    draft = store.create_draft({path: "P2"}, author="analyst")
    assert draft["status"] == "validated"
    with pytest.raises(ValueError, match="approver"):
        store.approve(draft["draftId"], approver="analyst")
    published = store.approve(draft["draftId"], approver="reviewer")
    current = KnowledgeCatalog()
    assert current.version == published["knowledgeSetVersion"] != old
    assert KnowledgeCatalog(old).version == old
    declaration = next(d for d in current.documents if d["documentKey"] == "fabric:ONTOLOGY-01")[
        "document"
    ]["declaration"]
    assert declaration == apply_edits(base(), {path: "P2"})
    history = store.history()
    assert [h["knowledgeSetVersion"] for h in history][-1] == current.version
    assert history[-1]["approver"] == "reviewer" and history[-1]["author"] == "analyst"
    saved = json.loads(
        (Path(profile6) / "store" / "sets" / (current.version + ".json")).read_text(
            encoding="utf-8"
        )
    )
    assert saved == current.documents
