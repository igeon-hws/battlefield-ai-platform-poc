"""Independent v5 logistics contracts; no LLM calls."""

import json
from pathlib import Path

import httpx
from conftest import server


def test_logistics_wheel_contains_ui_and_no_graph_or_agent_dependency(tmp_path):
    import subprocess
    import sys
    from zipfile import ZipFile

    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--outdir",
            str(tmp_path),
            "services/mock-logistics",
        ],
        check=True,
        capture_output=True,
    )
    with ZipFile(next(tmp_path.glob("mock_logistics*.whl"))) as wheel:
        assert "mock_logistics/web_static/index.html" in wheel.namelist()
        assert "mock_logistics/seed.json" in wheel.namelist()
        metadata = wheel.read(next(p for p in wheel.namelist() if p.endswith("METADATA"))).decode()
        assert "Requires-Dist: platform-api" not in metadata
        assert "Requires-Dist: battlefield-ontology" not in metadata
        assert "Requires-Dist: openai" not in metadata


def test_v5_launcher_keeps_source_and_mcp_processes_separate():
    from test_dev import load_dev

    service_specs = load_dev().service_specs
    sources = service_specs("sources", contract_version="5")
    assert {m for m, _ in sources} == {"mock_atcis.app", "mock_knccs.app", "mock_logistics.app"}
    fabric = service_specs("fabric", contract_version="5")
    assert "mock_logistics.mcp" in {m for m, _ in fabric}
    assert not any(m.endswith(".app") and m.startswith("mock_") for m, _ in fabric)
    assert len(service_specs("full", contract_version="5")) == 11


def exports_v5():
    result = {}
    for system in ("atcis", "knccs", "logistics"):
        seed = json.loads(
            Path(f"tests/fixtures/c2-logistics-demo-v5/{system}.json").read_text(encoding="utf-8")
        )
        seed.update(
            systemId=system, epochId="epoch-" + system, snapshotId="snapshot-" + system, sequence=1
        )
        module = __import__(
            "mock_" + system + ".app" if system == "logistics" else "mock_" + system + ".native",
            fromlist=["stable"],
        )
        result[system] = {
            **module.stable(seed),
            "sourceTime": seed["sourceTime"],
            "snapshotId": seed["snapshotId"],
            "sequence": 1,
        }
    return result


def test_v5_graph_explicit_identity_and_dependency_provenance(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    from battlefield_ontology.domain import build_domain
    from semantic_core.knowledge import KnowledgeCatalog

    c = KnowledgeCatalog()
    model = build_domain(exports_v5(), c.documents, c.manifest())
    assert any(
        e["kind"] == "SAME_AS"
        and e["start"] == "logistics:asset:EQ-781"
        and e["end"] == "atcis:equipment:L-T02"
        for e in model["edges"]
    )
    assert any(
        e["kind"] == "CARRIED_BY" and e["end"] == "knccs:transport:N-21" for e in model["edges"]
    )
    for edge in model["edges"]:
        assert edge["evidenceId"]
    assert not any("onHand" in n["payload"] for n in model["nodes"])
    assert not any("otherFaults" in n["payload"] for n in model["nodes"])
    from semantic_core.domain import DomainService

    semantic = DomainService(None)
    semantic.model = lambda version: (
        {
            "graphVersion": "test",
            "mappingVersion": "5.0.0",
            "resolutionRuleVersion": "5.0.0",
            "inputStableHashes": {},
            "ontologyVersion": "5.0.0",
            "inputSnapshotSet": {
                system: {"sourceTime": "2026-10-20T09:10:00Z"}
                for system in ("atcis", "knccs", "logistics")
            },
        },
        model["nodes"],
        model["edges"],
    )
    assert semantic.resolve_entity("test", "knccs", "N-21")["canonicalId"] == "knccs:transport:N-21"


async def test_object_detail_without_agent_and_partial_failure(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    from battlefield_ontology import digest
    from battlefield_ontology.domain import build_domain
    from semantic_core.knowledge import KnowledgeCatalog
    from semantic_core.objects import ObjectService

    exports = exports_v5()
    c = KnowledgeCatalog()
    m = build_domain(exports, c.documents, c.manifest())
    pins = {
        s: {k: v[k] for k in ("datasetId", "epochId", "snapshotId", "sequence", "sourceTime")}
        | {
            "stableDataHash": digest(
                {k: x for k, x in v.items() if k not in ("sourceTime", "snapshotId", "sequence")}
            )
        }
        for s, v in exports.items()
    }
    info = {
        "graphVersion": "test-v5",
        "inputSnapshotSet": pins,
        "inputStableHashes": {s: p["stableDataHash"] for s, p in pins.items()},
        "knowledgeSetVersion": c.version,
        "knowledgeSetHash": c.hash,
    }

    class Semantic:
        def model(self, version):
            return info, m["nodes"], m["edges"]

    class Fabric:
        def __init__(self):
            self.sources = {s: {} for s in exports}
            self.received = {}

        fail = False

        async def capture(self, requested_pins=None, allow_partial=False):
            snapshots = {}
            for s, v in exports.items():
                if self.fail and s == "logistics":
                    continue
                filename = "seed.json" if s == "logistics" else "native_seed_v5.json"
                raw = json.loads(
                    Path(f"services/mock-{s}/src/mock_{s}/{filename}").read_text(encoding="utf-8")
                )
                snapshots[s] = {
                    **raw,
                    **v,
                    "records": raw["records"],
                    "stableDataHash": pins[s]["stableDataHash"],
                }
            return snapshots

    f = Fabric()
    service = ObjectService(f, Semantic())
    result = await service.detail("atcis", "equipment", "L-T02", "test-v5")
    assert result["identityStatus"] == "resolved"
    assert any(r["record"].get("workOrderId") == "M-17" for r in result["records"])
    assert any(r["record"].get("transportId") == "N-21" for r in result["records"])
    assert result["links"] and result["graphVersion"] == "test-v5"
    navy = await service.detail("knccs", "own-force", "N-S01", "test-v5")
    assert any(r["record"].get("pennant") == "N-S01" for r in navy["records"])
    contact_id = next(
        n["sourceRef"]["nativeId"] for n in m["nodes"] if n["label"] == "ContactObservation"
    )
    contact = await service.detail("knccs", "contact", contact_id, "test-v5")
    assert any(r["recordType"] == "contact" for r in contact["records"])
    f.fail = True
    result = await service.detail("atcis", "equipment", "L-T02", "test-v5")
    assert result["coverage"]["logistics"] == "unavailable"
    assert any(r["systemId"] == "atcis" for r in result["records"])
    info["inputStableHashes"]["atcis"] = "changed"
    stale = await service.detail("atcis", "equipment", "L-T02", "test-v5")
    assert stale["identityStatus"] == "stale" and stale["links"] == []
    assert len(stale["records"]) == 1


def test_identity_ambiguity_expired_registration_and_independent_gold(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    from copy import deepcopy

    from battlefield_ontology.domain import build_domain
    from semantic_core.knowledge import KnowledgeCatalog
    from semantic_core.objects import resolve_identity

    c = KnowledgeCatalog()
    model = build_domain(exports_v5(), c.documents, c.manifest())
    edge = next(
        e
        for e in model["edges"]
        if e["kind"] == "SAME_AS" and e["start"] == "logistics:asset:EQ-781"
    )
    extra = {**deepcopy(edge), "end": "atcis:equipment:L-T01", "evidenceId": "conflict"}
    result = resolve_identity(
        model["nodes"],
        model["edges"] + [extra],
        "logistics",
        "asset",
        "EQ-781",
        "2026-10-20T09:10:00Z",
    )
    assert result["status"] == "ambiguous" and result["canonicalId"] is None
    edge["validTo"] = "2026-10-19T00:00:00Z"
    assert (
        resolve_identity(
            model["nodes"], model["edges"], "logistics", "asset", "EQ-781", "2026-10-20T09:10:00Z"
        )["status"]
        == "unresolved"
    )
    gold = json.loads(
        Path("tests/fixtures/c2-logistics-demo-v5/expected.json").read_text(encoding="utf-8")
    )
    fixture = json.loads(
        Path("tests/fixtures/c2-logistics-demo-v5/logistics.json").read_text(encoding="utf-8")
    )
    inventory = fixture["records"]["inventory"][0]
    assert inventory["onHand"] - inventory["reserved"] == gold["facts"]["L0"]["unreserved"]
    assert sum(r["quantity"] for r in fixture["records"]["reservations"]) == inventory["reserved"]


async def test_v5_page_context_enforces_server_boundaries(tmp_path, monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    from platform_api.multi_app import create_multi_app

    app = create_multi_app(path=tmp_path / "platform.db", provider=object())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        assert (await c.get("/api/v1/analyses")).status_code == 401
        a = (await c.post("/api/v1/demo-sessions", json={"mode": "native"})).json()
        headers = {"x-demo-session": a["sessionId"]}
        assert (await c.get("/api/v1/analyses", headers=headers)).status_code == 200
        for url, method in [
            ("/api/v1/objects/detail", "POST"),
            ("/api/v1/comparisons", "GET"),
            ("/api/v1/knowledge/sets", "GET"),
            ("/api/v1/semantic/status", "GET"),
            ("/api/v1/events", "GET"),
        ]:
            assert (
                await c.request(method, url, headers=headers, json={} if method == "POST" else None)
            ).status_code == 403
        assert (
            await c.post(
                "/api/v1/analyses",
                headers=headers,
                json={"question": "test", "knowledgeMode": "structured"},
            )
        ).status_code == 403
        assert app.state.runtime.sources.keys() == {"atcis", "knccs", "logistics"}


async def test_logistics_standalone_snapshots_reservations_and_controls(tmp_path):
    with server(
        "import uvicorn; from mock_logistics.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
        {
            "LOGISTICS_DB": str(tmp_path / "logistics.db"),
            "LOGISTICS_READ_TOKEN": "read",
            "LOGISTICS_CONTROL_TOKEN": "control",
        },
    ) as url:
        async with httpx.AsyncClient(base_url=url, headers={"Authorization": "Bearer read"}) as c:
            snapshot = (await c.get("/api/v1/snapshot")).json()
            assert snapshot["datasetId"] == "c2-logistics-demo-v5"
            assert snapshot["sourceSchemaVersion"] == "5.0.0"
            assert "documents" not in snapshot["records"]
            pin = snapshot["snapshotId"]
            inventory = (await c.get("/api/v1/inventory", params={"snapshotId": pin})).json()
            assert inventory["items"][0]["onHand"] == 2
            assert inventory["items"][0]["reserved"] == 1
            assert (await c.post("/api/v1/simulation/step")).status_code == 401
            changed = await c.patch(
                "/api/v1/work-orders/M-17",
                json={"status": "DONE"},
                headers={"Authorization": "Bearer control"},
            )
            assert changed.status_code == 200
            old = (await c.get("/api/v1/work-orders", params={"snapshotId": pin})).json()
            assert old["items"][0]["status"] == "WAIT_PART"
            current = (await c.get("/api/v1/snapshot")).json()
            assert current["records"]["work-orders"][0]["status"] == "DONE"
            assert current["stableDataHash"] == snapshot["stableDataHash"]
            assert (await c.get("/api/v1/documents", params={"snapshotId": pin})).status_code == 404


async def test_logistics_mcp_reads_public_api(tmp_path):
    from platform_api.mcp.client import MCPClient

    with (
        server(
            "import uvicorn; from mock_logistics.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
            {"LOGISTICS_DB": str(tmp_path / "mcp.db"), "LOGISTICS_READ_TOKEN": "read"},
        ) as source,
        server(
            "import uvicorn; from mock_logistics.mcp import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
            {
                "LOGISTICS_BASE_URL": source,
                "LOGISTICS_READ_TOKEN": "read",
                "LOGISTICS_MCP_TOKEN": "",
            },
        ) as endpoint,
    ):
        async with MCPClient(endpoint + "/mcp") as c:
            tools = await c.list_tools()
            assert "list_inventory" in {t["name"] for t in tools}
            assert "list_documents" not in {t["name"] for t in tools}
            snap = await c.call("get_snapshot", {})
            rows = await c.call("list_inventory", {"snapshotId": snap["snapshotId"]})
            assert rows["items"][0]["partId"] == "P-08"
