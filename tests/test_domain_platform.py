import asyncio
import json

import httpx
import pytest
from platform_api.agent.domain_tools import rows
from platform_api.app import create_app
from platform_api.domain_runtime import DomainRuntime
from test_agent import call, final
from test_domain_integration import domain_stack  # noqa: F401 - actual services

pytestmark = pytest.mark.neo4j


class ProcedureProvider:
    """Test-only reactive provider; production keeps the unchanged native loop."""

    async def respond(self, inputs, **kwargs):
        evidence = [
            json.loads(i["output"]) for i in inputs if i.get("type") == "function_call_output"
        ]
        evidence = [e for e in evidence if "evidenceId" in e]
        by_tool = {e["originalTool"]: e for e in evidence}
        on = any(t["name"] == "semantic__get_procedure_definition" for t in kwargs["tools"])
        if on and "get_procedure_definition" not in by_tool:
            return call("semantic__get_procedure_definition", {"documentId": "SOP-01"})
        if "list_activities" not in by_tool:
            return call("atcis__list_activities", {})
        if on and "list_reports" not in by_tool:
            return call("atcis__list_reports", {})
        if on and "evaluate_evidence" not in by_tool:
            return call(
                "evaluate_evidence",
                {
                    "evidenceIds": [
                        by_tool[t]["evidenceId"] for t in ("list_activities", "list_reports")
                    ],
                    "ruleEvidenceId": by_tool["get_procedure_definition"]["evidenceId"],
                    "ruleId": "ACTIVITY-STEP-01",
                },
            )
        if on:
            assert {r["nativeId"]: r["result"] for r in rows(by_tool["evaluate_evidence"])} == {
                "A1": "met",
                "A2": "not_met",
                "A3": "not_met",
            }
        return final(
            "테스트 전용: 현장 확인 완료, 식별 진행, 검토 미착수", [evidence[-1]["evidenceId"]]
        )


async def test_platform_comparison_and_ingestion_use_fabric_not_source_rest(
    domain_stack,  # noqa: F811 - imported pytest fixture
    tmp_path,
    monkeypatch,
):
    env = domain_stack
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "3")

    async def forbidden(*args, **kwargs):
        raise AssertionError("platform bypassed Fabric for direct source REST")

    monkeypatch.setattr(DomainRuntime, "source_get", forbidden)
    sources = {
        s: {
            "url": env[s.upper() + "_BASE_URL"],
            "mcpUrl": env[s.upper() + "_MCP_URL"],
            "token": "",
            "mcpToken": "",
        }
        for s in ("atcis", "knccs")
    }
    semantic = {
        "url": env["SEMANTIC_BASE_URL"],
        "mcpUrl": env["SEMANTIC_MCP_URL"],
        "token": "",
        "mcpToken": "",
        "builderUrl": env["BUILDER_BASE_URL"],
        "adminToken": env["BUILDER_ADMIN_TOKEN"],
    }
    app = create_app(
        tmp_path / "platform.db",
        profile="heterogeneous",
        provider=ProcedureProvider(),
        sources=sources,
        semantic_config=semantic,
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        created = await c.post(
            "/api/v1/comparisons",
            json={
                "question": "INC-1 지금 어디까지 진행됐어?",
                "baselineReportRef": "atcis:report:R0",
            },
        )
        cid = created.json()["comparisonId"]
        for _ in range(1200):
            comparison = (await c.get("/api/v1/comparisons/" + cid)).json()
            if comparison["status"] not in ("preparing", "running"):
                break
            await asyncio.sleep(0.1)
        assert comparison["status"] == "completed", comparison
        actual = [
            (await c.get("/api/v1/analyses/" + comparison[m + "RunId"])).json()
            for m in ("off", "on")
        ]
        assert actual[0]["sourceSnapshotSet"] == actual[1]["sourceSnapshotSet"]
        assert actual[0]["baselineSourceSnapshotSet"] == actual[1]["baselineSourceSnapshotSet"]
        assert all(r["baselineReportRef"] == "atcis:report:R0" for r in actual)
        assert all(r["semanticPolicyVersion"] == "3-domain-native-off" for r in actual)
        assert not any(t["name"].startswith("semantic__") for t in actual[0]["toolCalls"])
        for _ in range(80):
            situation = (await c.get("/api/v1/situation")).json()
            if len(situation.get("entities", [])) == 10:
                break
            await asyncio.sleep(0.05)
        assert len(situation["entities"]) == 10
        async with httpx.AsyncClient(base_url=env["ATCIS_BASE_URL"]) as source:
            assert (await source.post("/api/v1/simulation/step")).status_code == 200
            await asyncio.sleep(0.6)
            assert len((await c.get("/api/v1/analyses")).json()["items"]) == 2
            assert (
                await source.patch("/api/v1/equipment/L-T01", json={"maintenanceCode": "PMC"})
            ).status_code == 200
        for _ in range(300):
            run_list = (await c.get("/api/v1/analyses")).json()["items"]
            if len(run_list) == 3:
                break
            await asyncio.sleep(0.05)
        assert len(run_list) == 3, app.state.runtime.source_status
