import pytest
from conftest import server
from platform_api.mcp.client import MCPClient


@pytest.mark.parametrize(
    "system,tool,collection",
    [("atcis", "list_equipment", "items"), ("knccs", "list_own_forces", "payload")],
)
async def test_native_domain_mcp_is_actual_http_and_read_only(tmp_path, system, tool, collection):
    with server(  # noqa: SIM117 - source URL is required to start its MCP
        f"import uvicorn; from mock_{system}.native import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
        {f"{system.upper()}_DB": str(tmp_path / "native.db")},
    ) as source:
        with server(
            f"import uvicorn; from {system}_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
            {"C4I_CONTRACT_VERSION": "3", f"{system.upper()}_BASE_URL": source},
        ) as mcp:
            async with MCPClient(mcp + "/mcp") as client:
                definitions = await client.list_tools()
                names = {d["name"] for d in definitions}
                assert {tool, "list_documents", "get_snapshot"} <= names
                assert not any("patch" in n or "reset" in n for n in names)
                snapshot = await client.call("get_snapshot", {})
                assert "records" not in snapshot
                args = {"snapshotId": snapshot["snapshotId"], "limit": 1}
                result = await client.call(tool, args)
                assert len(result[collection]) == 1
                docs = await client.call("list_documents", {"snapshotId": snapshot["snapshotId"]})
                assert len(docs[collection]) == 4
                with pytest.raises(ValueError):
                    await client.call(tool, {"snapshotId": "missing"})
