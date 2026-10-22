from contextlib import ExitStack

import httpx
import pytest
from conftest import server
from platform_api.agent.domain_tools import DomainToolRunner
from platform_api.mcp.client import MCPClient

pytestmark = pytest.mark.neo4j


@pytest.fixture
def domain_stack(tmp_path):
    with ExitStack() as stack:
        env = {
            "C4I_CONTRACT_VERSION": "3",
            "NEO4J_URI": "bolt://127.0.0.1:17687",
            "BUILDER_ADMIN_TOKEN": "domain-test-admin",
            "SEMANTIC_READ_TOKEN": "",
            "SEMANTIC_MCP_TOKEN": "",
            "BUILDER_GRAPH_PREFIX": "test-",
        }
        for system in ("atcis", "knccs"):
            env[system.upper() + "_DB"] = str(tmp_path / f"{system}.db")
            env[system.upper() + "_READ_TOKEN"] = ""
            env[system.upper() + "_CONTROL_TOKEN"] = ""
            env[system.upper() + "_MCP_TOKEN"] = ""
            url = stack.enter_context(
                server(
                    f"import uvicorn; from mock_{system}.native import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
                    env,
                )
            )
            env[system.upper() + "_BASE_URL"] = url
            mcp = stack.enter_context(
                server(
                    f"import uvicorn; from {system}_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                    env,
                )
            )
            env[system.upper() + "_MCP_URL"] = mcp + "/mcp"
        env["BUILDER_BASE_URL"] = stack.enter_context(
            server(
                "import uvicorn; from graph_builder.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                env,
            )
        )
        env["SEMANTIC_BASE_URL"] = stack.enter_context(
            server(
                "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                env,
            )
        )
        mcp = stack.enter_context(
            server(
                "import uvicorn; from semantic_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                env,
            )
        )
        env["SEMANTIC_MCP_URL"] = mcp + "/mcp"
        yield env


async def test_native_fabric_semantic_mcp_agent_arithmetic_end_to_end(domain_stack):
    env = domain_stack
    async with httpx.AsyncClient(base_url=env["SEMANTIC_BASE_URL"], timeout=45) as http:
        off = await http.post("/v1/analysis-contexts", json={"semanticMode": "off"})
        assert off.status_code == 200, off.text
        off_context = off.json()
        on = await http.post(
            "/v1/analysis-contexts",
            json={"semanticMode": "on", "sourceSnapshotSet": off_context["sourceSnapshotSet"]},
        )
        assert on.status_code == 200, on.text
        context = on.json()
        assert off_context["documents"] == context["documents"]
    async with (
        MCPClient(env["ATCIS_MCP_URL"]) as land,
        MCPClient(env["KNCCS_MCP_URL"]) as sea,
        MCPClient(env["SEMANTIC_MCP_URL"]) as semantic,
    ):
        runner = DomainToolRunner(
            {"atcis": land, "knccs": sea, "semantic": semantic},
            context["sourceSnapshotSet"],
            "on",
            context["graphInfo"],
        )
        await runner.prepare()
        assert not runner.discovery_error, runner.discovery_error
        assert len([n for n in runner.registry if n.startswith("semantic__")]) == 7
        native = [
            await runner.execute("atcis__list_equipment", {}),
            await runner.execute("knccs__list_own_forces", {}),
        ]
        concept = await runner.execute("semantic__interpret_concept", {"term": "all"})
        scopes = [
            await runner.execute("semantic__resolve_unit_scope", {"term": term})
            for term in ("모의 1사단", "모의 1함대")
        ]
        unit_ids = [u for s in scopes for u in s["data"]["unitIds"]]
        refs = await runner.execute("semantic__find_equipment_refs", {"unitIds": unit_ids})
        evaluated = [
            await runner.execute(
                "evaluate_evidence",
                {
                    "evidenceIds": [n["evidenceId"]],
                    "ruleEvidenceId": concept["evidenceId"],
                    "ruleId": rule,
                },
            )
            for n, rule in zip(native, ("AVAIL-LAND-01", "AVAIL-NAVAL-01"), strict=True)
        ]
        args = {
            "evidenceIds": [e["evidenceId"] for e in native],
            "identityEvidenceIds": [refs["evidenceId"]],
            "scopeEvidenceIds": [e["evidenceId"] for e in scopes],
            "conceptEvidenceIds": [concept["evidenceId"]],
            "evaluationEvidenceIds": [e["evidenceId"] for e in evaluated],
        }
        counted = (await runner.execute("aggregate_evidence", args))["data"]
        assert counted["resolvedUniqueCount"] == 7
        assert counted["counts"] == {"available": 4, "limited": 1, "unavailable": 1, "unknown": 1}
        assert counted["policyIncludedCount"] == 4
        grouped = (await runner.execute("aggregate_evidence", {**args, "groupBy": "kind,status"}))[
            "data"
        ]
        assert grouped["typeStatusCounts"]["tank"] == {"available": 1, "limited": 1}
        p2 = (await runner.execute("aggregate_evidence", {**args, "policy": "P2"}))["data"]
        assert p2["policyIncludedCount"] == 5 and p2["counts"] == counted["counts"]
        with pytest.raises(ValueError, match="snapshot"):
            await runner.execute("knccs__list_own_forces", {"snapshotId": "another"})
        off_runner = DomainToolRunner(
            {"atcis": land, "knccs": sea, "semantic": semantic}, context["sourceSnapshotSet"], "off"
        )
        await off_runner.prepare()
        assert not any(n.startswith("semantic__") for n in off_runner.registry)
        raw = [
            await off_runner.execute("atcis__list_equipment", {}),
            await off_runner.execute("knccs__list_own_forces", {}),
        ]
        assert (
            await off_runner.execute(
                "aggregate_evidence", {"evidenceIds": [e["evidenceId"] for e in raw]}
            )
        )["data"]["rawRecordCount"] == 7
