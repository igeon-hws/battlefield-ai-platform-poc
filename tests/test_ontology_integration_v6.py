"""v6 over real sources, Graph Builder/Neo4j, Semantic API and MCP: one Fabric publish moves
B's document and C's business-query result together. Deterministic, no model cost."""

import asyncio
import json
import subprocess
import sys

import httpx
import pytest
from test_knowledge_integration import v4_stack

POLICY = "rules.AGGREGATION-POLICY-01.definition.defaultAvailablePolicy"


async def structured(fabric):
    r = await fabric.post(
        "/v1/analysis-contexts", json={"knowledgeMode": "structured", "sourceSnapshotSet": None}
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.neo4j
async def test_v6_business_queries_and_fabric_publish_over_real_stack(tmp_path):
    from platform_api.mcp.client import MCPClient

    extra = {"C4I_ONTOLOGY_PROFILE": "6", "FABRIC_KNOWLEDGE_STORE": str(tmp_path / "store")}
    with v4_stack(tmp_path, graph=True, version="5", extra_env=extra) as (url, env):
        output = tmp_path / "v6-manifest.json"
        dry = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "scripts/evaluate_knowledge.py",
                "--dry-run",
                "--contract-version",
                "5",
                "--ontology-profile",
                "6",
                "--url",
                url,
                "--max-runs",
                "27",
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert dry.returncode == 0, dry.stdout + dry.stderr
        manifest = json.loads(output.read_text(encoding="utf-8"))
        assert manifest["comparisonPolicyVersion"] == "6-ontology-abc"
        assert manifest["plannedRuns"] == 27 and not manifest["records"]
        assert manifest["reviewRubric"]["gold"].endswith("c2-ontology-demo-v6/expected.json")
        async with httpx.AsyncClient(base_url=env["SEMANTIC_BASE_URL"], timeout=60) as fabric:
            before = await structured(fabric)
            assert before["semanticPolicyVersion"] == "6-ontology-abc"
            version = before["graphInfo"]["graphVersion"]
            async with MCPClient(env["SEMANTIC_MCP_URL"]) as mcp:
                listed = await mcp.call("list_business_queries", {"graphVersion": version})
                assert len(listed["items"]) == 3
                summary = await mcp.call(
                    "run_business_query",
                    {
                        "graphVersion": version,
                        "queryId": "asset-availability-summary",
                        "unit": "D1",
                        "kind": "tank",
                    },
                )
                assert summary["counts"]["available"] == 1
                assert summary["declarationVersion"] == "6.0.0-r1"
                assert {r["snapshotId"] for r in summary["sourceRecords"]} <= {
                    p["snapshotId"] for p in before["sourceSnapshotSet"].values()
                }
                chain = await mcp.call(
                    "run_business_query",
                    {
                        "graphVersion": version,
                        "queryId": "asset-maintenance-chain",
                        "systemId": "atcis",
                        "nativeId": "L-T02",
                    },
                )
                work = chain["workOrders"][0]
                assert work["conditionalForecast"]["earliestCompletion"] == "2026-10-21T15:00:00Z"
            draft = (
                await fabric.post(
                    "/v1/ontology/drafts", json={"edits": {POLICY: "P2"}, "author": "analyst"}
                )
            ).json()
            assert draft["impact"]["businessQueries"] == ["asset-availability-summary"]
            assert any(row["after"]["available"] == 2 for row in draft["preview"]["rows"])
            published = (
                await fabric.post(
                    f"/v1/ontology/drafts/{draft['draftId']}/approve", json={"approver": "reviewer"}
                )
            ).json()
            after = await structured(fabric)
            assert after["knowledgeSetVersion"] == published["knowledgeSetVersion"]
            assert after["knowledgeSetVersion"] != before["knowledgeSetVersion"]
            new_version = after["graphInfo"]["graphVersion"]
            assert new_version != version
            async with MCPClient(env["SEMANTIC_MCP_URL"]) as mcp:
                changed = await mcp.call(
                    "run_business_query",
                    {
                        "graphVersion": new_version,
                        "queryId": "asset-availability-summary",
                        "unit": "D1",
                        "kind": "tank",
                    },
                )
                old = await mcp.call(
                    "run_business_query",
                    {
                        "graphVersion": version,
                        "queryId": "asset-availability-summary",
                        "unit": "D1",
                        "kind": "tank",
                    },
                )
            assert changed["counts"]["available"] == 2
            assert changed["declarationVersion"] == "6.0.0-r2"
            assert old["counts"]["available"] == 1
        async with MCPClient(env["KNOWLEDGE_MCP_URL"]) as knowledge:
            document = await knowledge.call(
                "get_knowledge_document",
                {
                    "knowledgeSetVersion": published["knowledgeSetVersion"],
                    "documentKey": "fabric:ONTOLOGY-01",
                },
            )
            previous = await knowledge.call(
                "get_knowledge_document",
                {
                    "knowledgeSetVersion": before["knowledgeSetVersion"],
                    "documentKey": "fabric:ONTOLOGY-01",
                },
            )
        assert "기본 가용 집계 기준: P2" in document["document"]["text"]
        assert "기본 가용 집계 기준: P1" in previous["document"]["text"]
