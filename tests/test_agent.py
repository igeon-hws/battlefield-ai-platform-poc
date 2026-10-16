import json

import pytest
from platform_api.agent.loop import AgentLoop
from platform_api.agent.tools import C4I_ALLOWED_TOOLS, ToolRunner
from platform_api.mcp.client import MCPClient


def call(name, args, call_id="call-1"):
    return {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": name,
                "arguments": json.dumps(args),
                "call_id": call_id,
                "id": f"fc-{call_id}",
            }
        ],
    }


def final(answer="안내", evidence=None, courses=None):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "outcome": "answer",
                                "answer": answer,
                                "findings": [],
                                "evidenceIds": evidence or [],
                                "limitations": [],
                                "courses": courses,
                            }
                        ),
                    }
                ],
            }
        ],
    }


class FakeProvider:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.inputs = []
        self.tools = []

    async def respond(self, inputs, **kwargs):
        self.inputs.append(json.loads(json.dumps(inputs)))
        self.tools.append(json.loads(json.dumps(kwargs.get("tools", []))))
        reply = next(self.replies)
        return reply(inputs) if callable(reply) else reply


class FakeMCP:
    async def list_tools(self):
        from c4i_mcp.server import create_app

        return [
            tool.model_dump(mode="json", by_alias=True, exclude_none=True)
            for tool in await create_app().state.tool_server.list_tools()
        ]

    async def call(self, name, args):
        if name == "c4i_get_snapshot":
            return {
                "snapshotId": "s1",
                "epochId": "epoch",
                "sequence": 1,
                "sourceTime": "2026-10-15T00:00:00Z",
                "revision": 1,
            }
        return {
            "snapshotId": args["snapshotId"],
            "matchedCount": 3,
            "groups": [],
            "sourceTime": "2026-10-15T00:00:00Z",
        }


async def test_native_direct_answer_and_dynamic_observation_loop():
    direct = FakeProvider([final()])
    result = await AgentLoop(direct, ToolRunner(FakeMCP())).run("사용법")
    assert result["status"] == "completed" and result["toolCalls"] == []

    def grounded(inputs):
        output = json.loads(inputs[-1]["output"])
        return final("등록된 적 탱크는 3대입니다.", [output["evidenceId"]])

    provider = FakeProvider(
        [
            call("c4i_get_snapshot", {}),
            call(
                "c4i_summarize_entities",
                {"snapshotId": "s1", "filter": {"kind": "tank", "affiliation": "hostile"}},
                "call-2",
            ),
            grounded,
        ]
    )
    result = await AgentLoop(provider, ToolRunner(FakeMCP())).run("적 탱크 수")
    assert result["status"] == "completed"
    assert len(result["toolCalls"]) == 2 and len(result["evidence"]) == 2
    inputs = provider.inputs[1]
    assert inputs[-1]["type"] == "function_call_output" and inputs[-1]["call_id"] == "call-1"
    assert any(item.get("type") == "function_call" for item in inputs)


async def test_permissions_snapshot_evidence_and_budget():
    runner = ToolRunner(FakeMCP())
    with pytest.raises(ValueError, match="snapshot_required"):
        await runner.execute("c4i_get_entity", {"entityId": "T-1", "snapshotId": "s1"})
    with pytest.raises(ValueError, match="not_allowed"):
        await runner.execute("delete_everything", {})
    await runner.execute("c4i_get_snapshot", {})
    with pytest.raises(ValueError, match="snapshot_mismatch"):
        await runner.execute("c4i_get_entity", {"entityId": "T-1", "snapshotId": "other"})
    with pytest.raises(ValueError):
        await runner.execute("read_evidence", {"evidenceId": "missing"})
    provider = FakeProvider([call("c4i_get_snapshot", {})] * 10)
    result = await AgentLoop(provider, ToolRunner(FakeMCP()), max_iterations=2).run("repeat")
    assert result["status"] == "budget_exceeded"
    invalid = FakeProvider([final(evidence=["invented"]), final(evidence=["invented"])])
    assert (await AgentLoop(invalid, ToolRunner(FakeMCP())).run("x"))[
        "status"
    ] == "validation_failed"


async def test_missing_key_never_returns_fake_success():
    from platform_api.providers.openai import OpenAIProvider

    with pytest.raises(RuntimeError, match="OPENAI"):
        await OpenAIProvider(api_key="", model="").respond([])


async def test_real_streamable_mcp_discovery_and_read_only_queries(mcp_url):
    async with MCPClient(mcp_url, token="test-mcp") as client:
        names = [tool["name"] for tool in await client.list_tools()]
        assert "c4i_summarize_entities" in names
        assert not any("patch" in name or "simulation" in name for name in names)
        snapshot = await client.call("c4i_get_snapshot", {})
        result = await client.call(
            "c4i_summarize_entities",
            {
                "snapshotId": snapshot["snapshotId"],
                "filter": {"kind": "tank", "affiliation": "hostile"},
                "groupBy": ["availability"],
            },
        )
        assert result["matchedCount"] == 3
        assert result["groups"][0]["availability"] == "unknown"
        assert snapshot["snapshotId"] == result["snapshotId"]
    assert C4I_ALLOWED_TOOLS >= set(names)


async def test_default_empty_tokens_work_across_all_three_http_hops(tmp_path):
    from conftest import server

    source_code = "import uvicorn; from mock_c4i.app import create_app; uvicorn.run(create_app(tick_enabled=False,token='',control_token='',scenario_id='west-coast-demo'),host='127.0.0.1',port=PORT,log_level='error')"
    mcp_code = "import uvicorn; from c4i_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')"
    with (
        server(source_code, {"C4I_DB": str(tmp_path / "default.db")}) as source_url,
        server(
            mcp_code, {"C4I_BASE_URL": source_url, "C4I_READ_TOKEN": "", "MCP_TOKEN": ""}
        ) as mcp_base,
    ):
        async with MCPClient(mcp_base + "/mcp") as client:
            snapshot = await client.call("c4i_get_snapshot", {})
            result = await client.call(
                "c4i_summarize_entities",
                {
                    "snapshotId": snapshot["snapshotId"],
                    "filter": {"kind": "tank", "affiliation": "hostile"},
                },
            )
            assert result["matchedCount"] == 3
