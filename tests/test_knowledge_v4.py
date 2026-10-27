"""V4 knowledge ownership and capability boundary contracts."""

import httpx
import pytest
from semantic_api.app import create_app
from test_neo4j import graph  # noqa: F401 - isolated Neo4j fixture


async def test_v4_fabric_knowledge_available_without_graph(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "4")
    monkeypatch.setenv("NEO4J_PASSWORD", "")
    app = create_app(token="read")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get("/v1/knowledge/sets")).status_code == 401
        c.headers["Authorization"] = "Bearer read"
        manifest = (await c.get("/v1/knowledge/sets")).json()["items"][0]
        version = manifest["knowledgeSetVersion"]
        docs = (
            await c.get(
                "/v1/knowledge/documents", params={"knowledgeSetVersion": version, "limit": 2}
            )
        ).json()
        assert len(docs["items"]) == 2 and docs["nextCursor"]
        doc = docs["items"][0]
        body = (
            await c.get(
                "/v1/knowledge/documents/" + doc["documentKey"],
                params={"knowledgeSetVersion": version},
            )
        ).json()
        assert body["document"]["text"] and body["knowledgeSetHash"] == manifest["knowledgeSetHash"]
        assert (
            await c.get("/v1/knowledge/search", params={"knowledgeSetVersion": version, "q": "FMC"})
        ).json()["items"]
        assert (
            await c.get("/v1/knowledge/documents", params={"knowledgeSetVersion": "missing"})
        ).status_code == 404


@pytest.mark.parametrize("system", ["atcis", "knccs"])
async def test_v4_source_has_no_explanatory_documents(tmp_path, monkeypatch, system):
    from importlib import import_module

    monkeypatch.setenv("C4I_CONTRACT_VERSION", "4")
    app = import_module(f"mock_{system}.native").create_app(
        tmp_path / (system + ".db"), tick_enabled=False, token="", control_token=""
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        raw = (await c.get("/api/v1/snapshot")).json()
        assert raw["sourceSchemaVersion"] == "4.0.0" and raw["datasetId"] == "c2-domain-demo-v4"
        assert "documents" not in raw["records"]
        assert (
            await c.get("/api/v1/documents", params={"snapshotId": raw["snapshotId"]})
        ).status_code == 404
        assert (
            "documents"
            not in (
                await c.get("/api/v1/stable-export", params={"snapshotId": raw["snapshotId"]})
            ).json()["records"]
        )


async def test_v4_runner_blocks_document_and_semantic_bypass():
    from platform_api.agent.knowledge_tools import KnowledgeToolRunner
    from semantic_core.knowledge import KnowledgeCatalog

    class Client:
        async def list_tools(self):
            return [
                {
                    "name": "list_documents",
                    "description": "old leak",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]

    pins = {
        s: {
            "snapshotId": s,
            "stableDataHash": s,
            "datasetId": "c2-domain-demo-v4",
            "epochId": "epoch",
            "sequence": 1,
            "sourceTime": "2026-10-20T09:10:00Z",
        }
        for s in ("atcis", "knccs")
    }
    for mode in ("native", "documents"):
        runner = KnowledgeToolRunner(
            {"atcis": Client(), "knccs": Client()},
            pins,
            mode,
            knowledge=KnowledgeCatalog().manifest() if mode == "documents" else None,
        )
        await runner.prepare()
        assert not any("list_documents" in d["name"] for d in runner.definitions)
        for name in ("atcis__list_documents", "semantic__interpret_concept", "evaluate_evidence"):
            with pytest.raises(ValueError):
                await runner.execute(name, {})
        if mode == "native":
            assert "knowledgeSetVersion" not in runner.snapshot
            with pytest.raises(ValueError):
                await runner.execute("knowledge__get_knowledge_document", {})


async def test_v4_catalog_provenance_and_cursor_independent_of_graph():
    import json
    from copy import deepcopy
    from pathlib import Path

    from battlefield_ontology.domain import build_domain
    from semantic_core.knowledge import KnowledgeCatalog

    catalog = KnowledgeCatalog()
    manifest = catalog.manifest()
    sources = {
        s: json.loads(
            Path(f"tests/fixtures/c2-domain-demo-v4/{s}.json").read_text(encoding="utf-8")
        )
        for s in ("atcis", "knccs")
    }
    for system, source in sources.items():
        source.update(systemId=system, epochId="test-epoch", snapshotId="test-snapshot", sequence=1)
    model = build_domain(sources, catalog.documents, manifest)
    rules = [n["payload"] for n in model["nodes"] if n["label"] == "InterpretationRule"]
    assert len(rules) == 12
    assert all(
        any(r["documentKey"] == "fabric:POLICY-01" for r in rule["documentRefs"]) for rule in rules
    )
    for rule in rules:
        for ref in rule["documentRefs"]:
            actual = catalog.document(ref["knowledgeSetVersion"], ref["documentKey"])
            assert actual["document"]["hash"] == ref["hash"]
    bad = deepcopy(manifest)
    bad["documents"][0]["hash"] = "tampered"
    with pytest.raises(ValueError):
        catalog.validate(bad)
    first = catalog.page(catalog.version, limit=1)
    with pytest.raises(ValueError):
        catalog.page(catalog.version, q="changed", cursor=first["nextCursor"])
    assert len({d["documentKey"] for d in manifest["documents"]}) == 9


def test_v4_grading_does_not_require_semantic_rules_from_a_or_b():
    from test_domain_evaluation import grader

    grade_record = grader().grade_record
    state = {"status": "completed", "evidence": [], "toolCalls": [], "result": {"claims": []}}
    expected = {"ruleIds": ["SOME-C-RULE"]}
    for mode in ("native", "documents"):
        grade = grade_record({"mode": mode, "scenario": "F1", "state": state}, expected)
        assert grade["capabilityBoundaryValid"] and not grade["missingRuleIds"]
    state["toolCalls"] = [{"name": "knowledge__get_knowledge_document"}]
    assert not grade_record({"mode": "native", "scenario": "F1", "state": state}, expected)[
        "capabilityBoundaryValid"
    ]


@pytest.mark.neo4j
async def test_v4_graph_rejects_unreviewed_knowledge(graph):  # noqa: F811
    import json
    from copy import deepcopy
    from importlib import import_module
    from pathlib import Path
    from uuid import uuid4

    from semantic_core.knowledge import KnowledgeCatalog

    sources = {}
    for system in ("atcis", "knccs"):
        state = json.loads(
            Path(f"tests/fixtures/c2-domain-demo-v4/{system}.json").read_text(encoding="utf-8")
        )
        state.update(systemId=system, epochId="test-epoch", snapshotId="test-snapshot", sequence=1)
        sources[system] = import_module(f"mock_{system}.native").stable(state) | {
            "sourceTime": state["sourceTime"]
        }
    with pytest.raises(ValueError):
        graph.build(sources)
    manifest = KnowledgeCatalog().manifest()
    bad = deepcopy(manifest)
    bad["knowledgeSetHash"] = "wrong"
    with pytest.raises(ValueError):
        graph.build(sources, knowledge=bad)
    version = "test-v4-" + uuid4().hex
    try:
        info = graph.build(sources, graph_version=version, knowledge=manifest)
        assert (
            info["ontologyVersion"] == "4.0.0"
            and info["knowledgeSetHash"] == manifest["knowledgeSetHash"]
        )
        assert (
            graph.build(sources, graph_version=version, knowledge=manifest)["graphVersion"]
            == version
        )
    finally:
        graph.remove_test_build(version)


async def test_v4_comparison_preserves_a_b_when_graph_preparation_fails(tmp_path):
    from platform_api.knowledge_runtime import KnowledgeRepository
    from semantic_core.knowledge import KnowledgeCatalog

    repo = KnowledgeRepository(tmp_path / "abc.db", "off", "4-knowledge-abc", "4")
    await repo.open()
    try:
        item = await repo.create_comparison("test", "documents")
        c = KnowledgeCatalog()
        manifest = {
            "sourceSnapshotSet": {},
            "baselineSourceSnapshotSet": {},
            "knowledgeSetVersion": c.version,
            "knowledgeSetHash": c.hash,
            "structuredPreparationError": "Neo4j unavailable",
        }
        result = await repo.publish_abc(item, manifest, None)
        runs = {m: await repo.get_run(r) for m, r in result["runIds"].items()}
        assert runs["structured"]["status"] == "failed"
        assert runs["documents"]["status"] == runs["native"]["status"] == "queued"
        assert len({r["conversationId"] for r in runs.values()}) == 3
    finally:
        await repo.close()


def test_v4_knowledge_archive_is_immutable_and_addressable():
    from semantic_core.knowledge import KnowledgeCatalog

    catalog = KnowledgeCatalog()
    assert KnowledgeCatalog(catalog.version).manifest() == catalog.manifest()
    with pytest.raises(KeyError):
        KnowledgeCatalog("../../knowledge_documents")


async def test_v4_public_config_exposes_knowledge_modes_and_fabric_url(tmp_path, monkeypatch):
    from platform_api.app import create_app

    monkeypatch.setenv("C4I_CONTRACT_VERSION", "4")
    monkeypatch.setenv("SEMANTIC_BASE_URL", "http://127.0.0.1:5400")
    app = create_app(tmp_path / "platform.db", profile="heterogeneous", provider=object())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        config = (await client.get("/api/v1/config")).json()
        assert config["knowledgeModes"] == ["native", "documents", "structured"]
        assert config["defaultKnowledgeMode"] == "native"
        assert "defaultSemanticMode" not in config
        assert config["fabricUrl"] == "http://127.0.0.1:5400"


@pytest.mark.parametrize("system", ["atcis", "knccs"])
def test_v4_source_cli_uses_separate_database(monkeypatch, system):
    import importlib
    import os

    module = importlib.import_module(f"mock_{system}.app")
    key = system.upper() + "_DB"
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "4")
    monkeypatch.setenv(key, "var/" + system + "-v2.db")
    monkeypatch.setenv(system.upper() + "_V4_DB", "var/test-" + system + "-v4.db")
    monkeypatch.setattr(module, "create_app", lambda: os.environ[key])
    observed = []
    monkeypatch.setattr(module.uvicorn, "run", lambda app, **kwargs: observed.append(app))
    module.main()
    assert observed == ["var/test-" + system + "-v4.db"]


async def test_v4_event_capture_preserves_other_source_snapshot():
    from types import SimpleNamespace

    from platform_api.knowledge_runtime import KnowledgeRuntime

    runtime = KnowledgeRuntime(
        SimpleNamespace(policy_version="4-knowledge-abc", source_contract="4"),
        object(),
        {"atcis": {}, "knccs": {}},
        {},
    )
    latest = {"atcis": {"snapshotId": "land-latest"}, "knccs": {"snapshotId": "sea-latest"}}
    calls = []

    async def request(method, path, **kwargs):
        body = kwargs["json"]
        calls.append(body)
        pins = body.get("sourceSnapshotSet") or latest
        return {
            "sourceSnapshotSet": pins,
            "capturedAt": "2026-10-20T09:10:00Z",
            "captureSpanSeconds": 0.01,
            "sourceRunning": {s: False for s in pins},
            "baselineSourceSnapshotSet": {},
        }

    runtime.fabric_request = request
    pins = await runtime.capture(overrides={"atcis": {"snapshotId": "land-event"}})
    assert pins == {"atcis": {"snapshotId": "land-event"}, "knccs": {"snapshotId": "sea-latest"}}
    assert len(calls) == 2
