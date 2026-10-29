"""Regression coverage for scoped semantic lookup and pinned run evidence."""

from test_logistics_v5 import exports_v5


def semantic_service():
    from battlefield_ontology.domain import build_domain
    from semantic_core.domain import DomainService
    from semantic_core.knowledge import KnowledgeCatalog

    catalog = KnowledgeCatalog()
    model = build_domain(exports_v5(), catalog.documents, catalog.manifest())
    info = {
        "graphVersion": "test",
        "ontologyVersion": "5.0.0",
        "mappingVersion": "5.0.0",
        "resolutionRuleVersion": "5.0.0",
        "inputStableHashes": {},
    }
    service = DomainService(None)
    service.model = lambda version: (info, model["nodes"], model["edges"])
    return service


def test_availability_selects_only_relevant_rules(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    service = semantic_service()
    rules = service.interpret_concept("test", "availability")["rules"]
    ids = {rule["ruleId"] for rule in rules}
    assert {"AVAIL-LAND-01", "AVAIL-NAVAL-01"} <= ids
    assert not ids & {"ACTIVITY-STEP-01", "REPORT-LINEAGE-01", "ORG-ROLE-01"}
    assert service.interpret_concept("test", "not-a-concept")["status"] == "unresolved"


def test_logistics_relation_requires_explicit_identity_bridge(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    service = semantic_service()
    result = service.query_relations(
        "test", "atcis:equipment:L-T02", ["SAME_AS", "MAINTAINS"], depth=2
    )
    assert {(e["kind"], e["start"], e["end"]) for e in result["items"]} >= {
        ("SAME_AS", "logistics:asset:EQ-781", "atcis:equipment:L-T02"),
        ("MAINTAINS", "logistics:work-order:M-17", "logistics:asset:EQ-781"),
    }
    assert (
        service.query_relations("test", "atcis:equipment:L-T02", ["MAINTAINS"], depth=2)[
            "matchedCount"
        ]
        == 0
    )


async def test_identical_pinned_source_call_reuses_run_evidence():
    from platform_api.agent.multi_tools import MultiToolRunner

    pin = {
        "datasetId": "demo",
        "epochId": "epoch",
        "snapshotId": "snapshot",
        "sequence": 1,
        "sourceTime": "2026-10-20T09:10:00Z",
        "stableDataHash": "hash",
    }

    class Client:
        def __init__(self):
            self.calls = 0

        async def list_tools(self):
            return [
                {
                    "name": "list_equipment",
                    "description": "Read equipment",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"snapshotId": {"type": "string"}},
                        "required": ["snapshotId"],
                    },
                }
            ]

        async def call(self, name, arguments):
            self.calls += 1
            return {"systemId": "atcis", "snapshotId": arguments["snapshotId"], "items": []}

    client = Client()
    runner = MultiToolRunner({"atcis": client}, {"atcis": pin}, "off")
    first = await runner.execute("atcis__list_equipment", {})
    second = await runner.execute("atcis__list_equipment", {"snapshotId": "snapshot"})
    assert first == second
    assert client.calls == 1
    assert len(runner.evidence) == 1
    other = MultiToolRunner({"atcis": client}, {"atcis": {**pin, "snapshotId": "next"}}, "off")
    await other.execute("atcis__list_equipment", {})
    assert client.calls == 2


async def test_tool_budget_reserves_a_final_answer_turn():
    from platform_api.agent.loop import AgentLoop
    from platform_api.agent.tools import ToolRunner
    from test_agent import FakeMCP, FakeProvider, call, final

    provider = FakeProvider([call("c4i_get_snapshot", {}), final("부분 답변")])
    state = await AgentLoop(provider, ToolRunner(FakeMCP()), max_tools=1).run("상황")
    assert state["status"] == "completed"
    assert provider.tools[1] == []


async def test_final_answer_notice_is_added_once_across_corrections():
    from platform_api.agent.loop import AgentLoop
    from platform_api.agent.tools import ToolRunner
    from test_agent import FakeMCP, FakeProvider, call, final

    invalid = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "not json"}],
            }
        ],
    }
    provider = FakeProvider([call("c4i_get_snapshot", {}), invalid, final("부분 답변")])
    state = await AgentLoop(provider, ToolRunner(FakeMCP()), max_tools=1).run("상황")
    assert state["status"] == "completed"
    notices = [
        item
        for item in provider.inputs[-1]
        if item.get("role") == "developer" and "도구 조회 예산" in str(item.get("content"))
    ]
    assert len(notices) == 1


def test_native_prompt_has_no_document_only_labor_hour_definition():
    from platform_api.agent.agent import INSTRUCTIONS

    assert "laborHours는" not in INSTRUCTIONS


def test_l3_gold_does_not_require_an_unasked_cutoff():
    import json
    from pathlib import Path

    gold = json.loads(
        Path("tests/fixtures/c2-logistics-demo-v5/expected.json").read_text(encoding="utf-8")
    )
    assert "18:00" not in gold["questions"]["L3"]
    assert "result" not in gold["facts"]["L3"]


async def test_procedure_tool_is_explicitly_incident_only(monkeypatch):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "5")
    from semantic_mcp.server import create_app

    tools = await create_app().state.tool_server.list_tools()
    definition = next(tool for tool in tools if tool.name == "get_procedure_definition")
    assert "incident" in definition.description
    assert "repair" in definition.description
    schema = definition.inputSchema
    assert "documentId" in schema["required"]
