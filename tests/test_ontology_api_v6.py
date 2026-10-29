"""v6 Semantic API: business queries over pinned snapshots and the Fabric edit/review flow."""

import httpx
import pytest
from test_business_queries_v6 import model as business_model  # noqa: F401 - fixture reuse


class Repo:
    def __getattr__(self, name):
        raise AssertionError("graph repository must not be used directly: " + name)


@pytest.fixture
def api(business_model, monkeypatch):  # noqa: F811
    from semantic_api.app import create_app
    from semantic_core.domain import DomainService

    info, nodes, edges, snapshots = business_model
    info = {
        **info,
        "inputSnapshotSet": {
            s: {
                "datasetId": "c2-logistics-demo-v5",
                "epochId": "epoch-" + s,
                "snapshotId": snapshots[s]["snapshotId"],
                "sequence": 1,
                "sourceTime": snapshots[s]["sourceTime"],
            }
            for s in snapshots
        },
        "inputStableHashes": {s: "hash-" + s for s in snapshots},
    }
    snapshots = {
        s: {**raw, **info["inputSnapshotSet"][s], "stableDataHash": "hash-" + s}
        for s, raw in snapshots.items()
    }
    monkeypatch.setattr(DomainService, "model", lambda self, version: (info, nodes, edges))
    app = create_app(repository=Repo(), token="")
    captured = []

    async def capture(pins=None, allow_partial=False):
        captured.append(pins)
        return snapshots

    async def ensure_graph(refs, knowledge_version=None):
        return {"graphVersion": "test"}

    app.state.fabric.capture = capture
    app.state.fabric.ensure_graph = ensure_graph
    return app, captured, info


async def test_business_query_reads_the_graph_pinned_snapshot(api):
    app, captured, info = api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        listed = (await c.get("/v1/business-queries", params={"graphVersion": "test"})).json()
        assert listed["inputStableHashes"] == info["inputStableHashes"]
        assert {q["queryId"] for q in listed["items"]} == {
            "asset-availability-summary",
            "asset-maintenance-chain",
            "part-supply-status",
        }
        r = await c.post(
            "/v1/business-queries/asset-availability-summary",
            json={"graphVersion": "test", "params": {"unit": "D1", "kind": "tank", "partId": None}},
        )
    assert r.status_code == 200, r.text
    assert r.json()["counts"]["available"] == 1
    pins = captured[-1]
    assert {s: p["snapshotId"] for s, p in pins.items()} == {
        s: v["snapshotId"] for s, v in info["inputSnapshotSet"].items()
    }
    assert all(p["stableDataHash"] == "hash-" + s for s, p in pins.items())


async def test_fabric_edit_impact_preview_review_and_publish(api):
    app, _, _ = api
    path = "rules.AGGREGATION-POLICY-01.definition.defaultAvailablePolicy"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        current = (await c.get("/v1/ontology")).json()
        assert current["editable"][0]["value"] == "P1"
        bad = await c.post(
            "/v1/ontology/drafts",
            json={"edits": {"rules.AVAIL-LAND-01.definition.default": "available"}, "author": "a"},
        )
        assert bad.status_code == 422
        draft = (
            await c.post("/v1/ontology/drafts", json={"edits": {path: "P2"}, "author": "analyst"})
        ).json()
        assert draft["impact"]["businessQueries"] == ["asset-availability-summary"]
        assert draft["preview"]["rows"], draft["preview"]
        tank = next(
            row
            for row in draft["preview"]["rows"]
            if row["params"] == {"unit": "D1", "kind": "tank"}
        )
        assert (tank["before"]["available"], tank["after"]["available"]) == (1, 2)
        same = await c.post(
            f"/v1/ontology/drafts/{draft['draftId']}/approve", json={"approver": "analyst"}
        )
        assert same.status_code == 422
        published = (
            await c.post(
                f"/v1/ontology/drafts/{draft['draftId']}/approve", json={"approver": "reviewer"}
            )
        ).json()
        after = (await c.get("/v1/ontology")).json()
    assert after["knowledgeSetVersion"] == published["knowledgeSetVersion"]
    assert after["knowledgeSetVersion"] != current["knowledgeSetVersion"]
    assert after["editable"][0]["value"] == "P2"
    assert after["declarationVersion"] == "6.0.0-r2"
    assert after["history"][-1]["approver"] == "reviewer"


async def test_business_query_tools_exist_only_in_profile6(monkeypatch):
    from semantic_mcp.server import create_app

    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    monkeypatch.delenv("C4I_ONTOLOGY_PROFILE", raising=False)
    names = {t.name for t in await create_app().state.tool_server.list_tools()}
    assert "run_business_query" not in names
    monkeypatch.setenv("C4I_ONTOLOGY_PROFILE", "6")
    tools = {t.name: t for t in await create_app().state.tool_server.list_tools()}
    assert {"list_business_queries", "run_business_query"} <= set(tools)
    from platform_api.mcp.schema import native_definition

    definition = native_definition(tools["run_business_query"].model_dump(by_alias=True))
    assert definition["parameters"]["additionalProperties"] is False
