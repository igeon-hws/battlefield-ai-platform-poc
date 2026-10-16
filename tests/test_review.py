import pytest
from platform_api.repository import Repository


async def test_extended_equipment_history_through_actual_mcp(c4i_url, mcp_url):
    import httpx
    from platform_api.agent.tools import ToolRunner
    from platform_api.mcp.client import MCPClient

    async with MCPClient(mcp_url, token="test-mcp") as client:
        runner = ToolRunner(client)
        snapshot = (await runner.execute("c4i_get_snapshot", {}))["data"]
        equipment = (
            await runner.execute(
                "c4i_list_entities",
                {"snapshotId": snapshot["snapshotId"], "filter": {"kind": "armored_vehicle"}},
            )
        )["data"]
        assert equipment["matchedCount"] == 1
        assert equipment["items"][0]["maintenanceStatus"] == "serviceable"
        assert equipment["items"][0]["unitId"]
        assert equipment["items"][0]["source"] == "synthetic-scenario"
        summary = (
            await runner.execute(
                "c4i_summarize_entities",
                {
                    "snapshotId": snapshot["snapshotId"],
                    "filter": {"unitId": "DEMO-BLUE", "maintenanceStatus": "maintenance"},
                    "groupBy": ["kind", "maintenanceStatus"],
                },
            )
        )["data"]
        assert summary["matchedCount"] == 2
        assert {item["kind"] for item in summary["groups"]} == {"tank", "support_vehicle"}
        async with httpx.AsyncClient() as source:
            updated = (
                await source.patch(
                    c4i_url + "/api/v1/entities/BLU-A01",
                    json={"maintenanceStatus": "maintenance", "availability": "unavailable"},
                    headers={"Authorization": "Bearer test-control"},
                )
            ).json()
        # New run gets a fresh pinned snapshot; old run cannot see future history.
        args = {
            "epochId": updated["epochId"],
            "entityId": "BLU-A01",
            "after": 0,
            "throughSequence": updated["sequence"],
            "limit": 1,
        }
        with pytest.raises(ValueError, match="snapshot_mismatch"):
            await runner.execute("c4i_list_entity_history", args)
        fresh = ToolRunner(client)
        await fresh.execute("c4i_get_snapshot", {})
        first = (await fresh.execute("c4i_list_entity_history", args))["data"]
        assert len(first["items"]) == 1
        assert first["nextAfter"] is not None
        second = (
            await fresh.execute("c4i_list_entity_history", {**args, "after": first["nextAfter"]})
        )["data"]
        assert second["items"][0]["entity"]["availability"] == "unavailable"
        assert second["nextAfter"] is None
        empty = (await fresh.execute("c4i_list_entity_history", {**args, "entityId": "missing"}))[
            "data"
        ]
        assert empty["items"] == [] and empty["nextAfter"] is not None
        native = {tool["name"]: tool for tool in fresh.definitions}
        discovered = (await client.session.list_tools()).tools
        for tool in discovered:
            assert native[tool.name]["description"] == tool.description


async def test_old_entity_snapshot_accepts_new_optional_fields(tmp_path):
    import json

    from c4i_contracts import Entity, EntityFilter
    from mock_c4i.store import C4IStore

    old = Entity.model_validate(
        {"entityId": "old", "label": "old", "position": {"longitude": 126.5, "latitude": 36.5}}
    )
    assert old.maintenance_status == "unknown"
    store = C4IStore(tmp_path / "legacy.db")
    await store.open([old])
    try:
        current = await store.snapshot()
        for name in ("maintenanceStatus", "unitId", "subtype", "source", "observedAt"):
            store.state["entities"][0].pop(name, None)
        legacy = json.dumps(store.state)
        await store.db.execute("UPDATE current_state SET body=? WHERE id=1", (legacy,))
        await store.db.execute(
            "UPDATE snapshots SET body=? WHERE id=?", (legacy, current["snapshotId"])
        )
        await store.db.commit()
        await store.close()
        await store.open([old])
        assert "maintenanceStatus" not in (await store.snapshot())["entities"][0]
        assert (
            await store.entities(current["snapshotId"], EntityFilter(maintenanceStatus="unknown"))
        )["matchedCount"] == 1
        await store.tick()
        assert (await store.entities(None, EntityFilter(), 100))["items"][0][
            "maintenanceStatus"
        ] == "unknown"
        assert (await store.snapshot(current["snapshotId"]))["snapshotId"] == current["snapshotId"]
    finally:
        await store.close()


async def test_selected_course_context_and_independent_turns(tmp_path):
    repo = Repository(tmp_path / "conversation.db")
    await repo.open()
    try:
        first = await repo.create_run("세 가지 대안")
        result = {
            "answer": "비교 결과",
            "courses": [
                {"id": str(i), "title": f"대안 {i}", "summary": f"내용 {i}"} for i in range(3)
            ],
        }
        await repo.update_run(first["runId"], {"status": "completed", "result": result})
        await repo.select(first["runId"], "1")
        second = await repo.create_run("선택한 대안을 설명해줘", first["conversationId"])
        history = await repo.history(first["conversationId"], second["runId"])
        assert first["runId"] in history[-1]["content"]
        assert '"selectedCourseId": "1"' in history[-1]["content"]
        assert "내용 1" in history[-1]["content"]
        await repo.update_run(second["runId"], {"status": "completed", "result": result})
        await repo.select(second["runId"], "2")
        assert (await repo.get_run(first["runId"]))["selectedCourseId"] == "1"
        assert (await repo.get_run(second["runId"]))["selectedCourseId"] == "2"
        with pytest.raises(ValueError):
            await repo.select(second["runId"], "missing")
        for _ in range(201):
            await repo.create_run("다른 대화")
        assert len(await repo.conversation(first["conversationId"])) == 2
    finally:
        await repo.close()
