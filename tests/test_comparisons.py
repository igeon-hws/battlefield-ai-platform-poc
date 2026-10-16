import asyncio

import httpx
import pytest
from dotenv import load_dotenv
from platform_api.app import create_app
from semantic_support import ScenarioProvider, stack


@pytest.mark.neo4j
async def test_comparison_freezes_sources_and_keeps_independent_native_runs(tmp_path):
    load_dotenv()
    with stack(tmp_path) as (sources, semantic):
        app = create_app(
            tmp_path / "platform.db",
            profile="heterogeneous",
            sources=sources,
            semantic_config=semantic,
            provider=ScenarioProvider(),
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            created = await client.post(
                "/api/v1/comparisons", json={"question": "모의 1사단의 가용한 탱크를 보여줘."}
            )
            assert created.status_code == 202
            cid = created.json()["comparisonId"]
            for _ in range(300):
                comparison = (await client.get("/api/v1/comparisons/" + cid)).json()
                if comparison["status"] not in ("preparing", "running"):
                    break
                await asyncio.sleep(0.1)
            assert comparison["status"] == "completed", comparison.get("error") or comparison
            assert comparison["manifest"]["preparationSeconds"] >= 0
            assert (
                comparison["manifest"]["preparedAt"]
                >= comparison["manifest"]["preparationStartedAt"]
            )
            off = (await client.get("/api/v1/analyses/" + comparison["offRunId"])).json()
            on = (await client.get("/api/v1/analyses/" + comparison["onRunId"])).json()
            assert (
                off["sourceSnapshotSet"]
                == on["sourceSnapshotSet"]
                == comparison["manifest"]["sourceSnapshotSet"]
            )
            assert off["conversationId"] != on["conversationId"]
            assert off["graphInfo"] is None
            assert any(t["name"].startswith("semantic__") for t in on["toolCalls"])
            assert not any(t["name"].startswith("semantic__") for t in off["toolCalls"])
            for run in (off, on):
                assert "2대" in run["result"]["answer"]
                aggregate = next(
                    e["data"] for e in run["evidence"] if e["tool"] == "aggregate_evidence"
                )
                assert (
                    aggregate["confirmedAvailable"]
                    if run["semanticMode"] == "on"
                    else aggregate["counts"]["atcis:R"]
                ) == 2
                assert run["registryHash"]
            assert {e["evidenceId"] for e in off["evidence"]}.isdisjoint(
                e["evidenceId"] for e in on["evidence"]
            )
            graph_evidence_id = next(
                e["data"]["evidenceRefs"][0]
                for e in on["evidence"]
                if e["systemId"] == "semantic" and e["data"].get("evidenceRefs")
            )
            proof = await client.get(
                f"/api/v1/analyses/{on['runId']}/semantic-evidence/{graph_evidence_id}"
            )
            assert proof.status_code == 200 and proof.json()["item"]["sourceSnapshotRefs"]
            assert (
                await client.get(
                    f"/api/v1/analyses/{off['runId']}/semantic-evidence/{graph_evidence_id}"
                )
            ).status_code == 404


async def test_graph_preparation_failure_is_explicit_and_standalone_off_is_available(tmp_path):
    app = create_app(
        tmp_path / "platform.db",
        profile="heterogeneous",
        provider=ScenarioProvider(),
        sources={"atcis": {"url": "http://127.0.0.1:1", "mcpUrl": "http://127.0.0.1:1/mcp"}},
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        created = await client.post("/api/v1/comparisons", json={"question": "same question"})
        assert created.status_code == 202
        for _ in range(100):
            comparison = (
                await client.get("/api/v1/comparisons/" + created.json()["comparisonId"])
            ).json()
            if comparison["status"] == "failed":
                break
            await asyncio.sleep(0.05)
        assert comparison["status"] == "failed" and comparison["error"]
        assert (
            await client.post(
                "/api/v1/analyses", json={"question": "일반 설명", "semanticMode": "off"}
            )
        ).status_code == 202
