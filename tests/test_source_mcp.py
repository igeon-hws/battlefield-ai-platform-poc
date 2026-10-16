import pytest
from conftest import server
from platform_api.mcp.client import MCPClient


@pytest.mark.parametrize("system,object_id", [("atcis", "T-A01"), ("knccs", "V-K01")])
async def test_independent_source_mcp_uses_public_api(tmp_path, system, object_id):
    source_code = f"""
import contextlib,uvicorn
import battlefield_source_runtime.app as runtime
from mock_{system}.app import create_app
app=create_app(tick_enabled=False)
original=app.router.lifespan_context
def forbidden(*args,**kwargs):
    raise AssertionError('Semantic normalizer called from native source MCP')
@contextlib.asynccontextmanager
async def lifespan(app):
    async with original(app):
        runtime.normalize_equipment=forbidden
        yield
app.router.lifespan_context=lifespan
uvicorn.run(app,host='127.0.0.1',port=PORT,log_level='error')
"""
    with server(  # noqa: SIM117 - the second process needs the first process URL
        source_code,
        {
            f"{system.upper()}_DB": str(tmp_path / "source.db"),
            f"{system.upper()}_READ_TOKEN": "source-read",
        },
    ) as source:
        with server(
            f"import uvicorn; from {system}_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
            {
                f"{system.upper()}_BASE_URL": source,
                f"{system.upper()}_READ_TOKEN": "source-read",
                f"{system.upper()}_MCP_TOKEN": "mcp-read",
            },
        ) as url:
            async with MCPClient(url + "/mcp", "mcp-read") as client:
                definitions = await client.list_tools()
                assert len(definitions) == 11
                assert all(d["description"] and d["inputSchema"] for d in definitions)
                listing = next(d for d in definitions if d["name"] == "list_equipment")
                assert {"typeCode", "statusCode"} <= listing["inputSchema"]["properties"].keys()
                assert not {"kind", "availability"} & listing["inputSchema"]["properties"].keys()
                assert not any("patch" in d["name"] or "reset" in d["name"] for d in definitions)
                snap = await client.call("get_snapshot", {})
                assert snap["systemId"] == system
                assert "tracks" not in snap and "contacts" not in snap
                data = await client.call(
                    "list_equipment", {"snapshotId": snap["snapshotId"], "nativeIds": [object_id]}
                )
                assert len(data["items"]) == 1
                units = await client.call("list_units", {"snapshotId": snap["snapshotId"]})
                assert units["matchedCount"] >= 2
                identity = await client.call(
                    "list_identity_records", {"snapshotId": snap["snapshotId"]}
                )
                assert any(r["exerciseAssetRef"] == "EX-U01" for r in identity["items"])
                detail = await client.call(
                    "get_equipment", {"snapshotId": snap["snapshotId"], "nativeId": object_id}
                )
                assert detail["item"] == data["items"][0]
                summary = await client.call(
                    "summarize_equipment", {"snapshotId": snap["snapshotId"]}
                )
                assert summary["matchedCount"] == (6 if system == "atcis" else 3)
                assert ("TANK" if system == "atcis" else "SURFACE") in summary["counts"]
                for name in ("list_unit_relations", "list_assignments"):
                    assert (await client.call(name, {"snapshotId": snap["snapshotId"]}))["items"]
                assert not (
                    await client.call(
                        "get_changes",
                        {"fromSnapshotId": snap["snapshotId"], "toSnapshotId": snap["snapshotId"]},
                    )
                )["items"]
                for name in ("list_events", "list_equipment_history"):
                    arguments = {"epochId": snap["epochId"], "throughSequence": snap["sequence"]}
                    if name == "list_equipment_history":
                        arguments["nativeId"] = object_id
                    assert (await client.call(name, arguments))["items"]
                with pytest.raises(ValueError, match="mcp_tool_error"):
                    await client.call("list_equipment", {"snapshotId": "nonexistent"})
