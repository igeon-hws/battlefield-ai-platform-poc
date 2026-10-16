import copy
from types import SimpleNamespace

import pytest
from platform_api.agent.loop import AgentLoop
from platform_api.agent.tools import ToolRunner
from platform_api.mcp.client import MCPClient
from test_agent import FakeProvider, final


async def test_discovery_pagination():
    client = MCPClient("unused")

    class Session:
        async def list_tools(self, cursor=None):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        model_dump=lambda **kw: {
                            "name": "first" if cursor is None else "second",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    )
                ],
                nextCursor="page2" if cursor is None else None,
            )

    client.session = Session()
    assert [item["name"] for item in await client.list_tools()] == ["first", "second"]


async def test_server_discovery_is_model_definition_and_frozen(mcp_url):
    async with MCPClient(mcp_url, token="test-mcp") as client:
        discovered = await client.list_tools()
        runner = ToolRunner(client)
        await runner.prepare()
        definition = next(t for t in runner.definitions if t["name"] == "c4i_list_entities")
        original = next(t for t in discovered if t["name"] == "c4i_list_entities")
        assert definition["description"] == original["description"]
        assert "kind" in str(definition["parameters"]) and "maintenanceStatus" in str(
            definition["parameters"]
        )
        frozen = copy.deepcopy(runner.definitions)
        provider = FakeProvider([final()])
        await AgentLoop(provider, runner).run("설명")
        assert runner.definitions == frozen
        assert provider.tools[0] == frozen
        snapshot = (await runner.execute("c4i_get_snapshot", {}))["data"]
        result = await runner.execute(
            "c4i_list_entities",
            {"snapshotId": snapshot["snapshotId"], "limit": None, "filter": {"kind": "tank"}},
        )
        assert result["data"]["matchedCount"] == 6
        with pytest.raises(ValueError):
            await runner.execute(
                "c4i_list_entities",
                {"snapshotId": snapshot["snapshotId"], "filter": {"kind": "invalid"}},
            )


async def test_discovered_description_changes_without_client_copy():
    class Server:
        description = "server version one"

        async def list_tools(self):
            return [
                {
                    "name": "c4i_get_snapshot",
                    "description": self.description,
                    "inputSchema": {
                        "type": "object",
                        "properties": {"snapshotId": {"type": "string"}},
                        "additionalProperties": False,
                    },
                }
            ]

    server = Server()
    first = ToolRunner(server)
    await first.prepare()
    server.description = "server version two"
    await first.prepare()
    second = ToolRunner(server)
    await second.prepare()
    assert first.definitions[-1]["description"] == "server version one"
    assert second.definitions[-1]["description"] == "server version two"


@pytest.mark.parametrize("extra", [{"additionalProperties": True}, {"oneOf": [{"type": "object"}]}])
def test_unrepresentable_schema_is_rejected(extra):
    from platform_api.mcp.schema import native_definition

    with pytest.raises(ValueError):
        native_definition(
            {
                "name": "c4i_get_snapshot",
                "inputSchema": {"type": "object", "properties": {}, **extra},
            }
        )


async def test_unlisted_tools_and_local_name_collisions():
    class Server:
        name = "delete_everything"

        async def list_tools(self):
            return [{"name": self.name, "inputSchema": {"type": "object", "properties": {}}}]

    server = Server()
    runner = ToolRunner(server)
    await runner.prepare()
    assert not runner.registry
    server.name = "read_evidence"
    with pytest.raises(ValueError, match="conflicting"):
        await ToolRunner(server).prepare()
