import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from mock_c4i.app import create_app
from mock_c4i.store import C4IStore, CursorExpired
from platform_api.agent.loop import AgentLoop
from platform_api.agent.tools import ToolRunner
from platform_api.app import create_app as platform_app
from test_agent import FakeMCP, FakeProvider, call, final
from test_c4i import entity


async def test_bbox_is_query_filter_and_same_count_contract(tmp_path):
    app = create_app(tmp_path / "source.db", tick_enabled=False)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/v1/entities", params={"bbox": "0,0,1,1"})
        assert response.status_code == 200 and response.json()["matchedCount"] == 0
        summary = await client.get("/api/v1/entities/summary", params={"bbox": "0,0,1,1"})
        assert summary.status_code == 200 and summary.json()["matchedCount"] == 0
        assert (await client.get("/api/v1/entities", params={"bbox": "1,1,0,0"})).status_code == 422


async def test_event_epoch_bounds_invalid_cursor_and_changes(tmp_path):
    store = C4IStore(tmp_path / "source.db")
    await store.open([entity(velocity={"eastMps": 0, "northMps": 0})])
    before = await store.snapshot()
    await store.tick()
    after = await store.snapshot()
    assert not (await store.changes(before["snapshotId"], after["snapshotId"]))["items"]
    await store.reset()
    reset = await store.snapshot()
    assert all(e["epochId"] == reset["epochId"] for e in await store.events(reset["epochId"], 0))
    with pytest.raises(CursorExpired):
        await store.events(reset["epochId"], 999999)
    await store.close()


async def test_direct_answer_does_not_require_live_mcp(tmp_path):
    app = platform_app(
        tmp_path / "platform.db",
        c4i_url="http://127.0.0.1:1",
        mcp_url="http://127.0.0.1:1/mcp",
        provider=FakeProvider([final("사용 안내")]),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        run = (await client.post("/api/v1/analyses", json={"question": "사용법"})).json()
        for _ in range(40):
            state = (await client.get("/api/v1/analyses/" + run["runId"])).json()
            if state["status"] not in ("queued", "running"):
                break
            await asyncio.sleep(0.05)
        assert state["status"] == "completed" and not state["toolCalls"]


async def test_timed_out_tool_trace_is_not_left_running():
    class SlowMCP(FakeMCP):
        async def call(self, name, args):
            await asyncio.sleep(1)

    result = await AgentLoop(
        FakeProvider([call("c4i_get_snapshot", {})]), ToolRunner(SlowMCP()), deadline=0.02
    ).run("query")
    assert result["status"] == "timeout"
    assert result["toolCalls"][0]["status"] == "timeout"
