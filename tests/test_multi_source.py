import pytest
from platform_api.multi_repository import MultiRepository


def test_agent_budget_allows_source_workflow_and_is_shared_by_modes(monkeypatch):
    from platform_api.multi_runtime import MultiRuntime

    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "24")
    runtime = MultiRuntime(None, None, {}, {})
    assert runtime.agent_limits == {"max_iterations": 24, "max_tools": 20, "deadline": 120}


async def test_modes_and_source_event_ids_are_isolated_and_durable(tmp_path):
    repo = MultiRepository(tmp_path / "next.db")
    await repo.open()
    try:
        first = await repo.enqueue("question", "on")
        await repo.update_run(
            first["runId"],
            {"status": "completed", "result": {"answer": "ON only", "courses": None}},
        )
        with pytest.raises(ValueError, match="mode"):
            await repo.enqueue("follow up", "off", first["conversationId"])
        off = await repo.enqueue("question", "off")
        assert await repo.history(off["conversationId"]) == []
        snap = {
            "snapshotId": "s1",
            "epochId": "e1",
            "sequence": 1,
            "datasetId": "d",
            "entities": [],
        }
        event = {"eventId": "same", "type": "equipment.changed", "epochId": "e1", "sequence": 1}
        assert await repo.save_source("atcis", snap, event)
        assert await repo.save_source("knccs", snap, event)
        assert not await repo.save_source("atcis", snap, event)
        situation = await repo.situation()
        assert set(situation["sources"]) == {"atcis", "knccs"}
        comparison = await repo.create_comparison("same question")
        result = await repo.publish_comparison(
            comparison["comparisonId"],
            {"sourceSnapshotSet": {}, "graphVersion": "g"},
            {"graphVersion": "g"},
        )
        assert result["offRunId"] != result["onRunId"]
        assert (await repo.publish_comparison(comparison["comparisonId"], {}, {}))[
            "offRunId"
        ] == result["offRunId"]
        assert (await repo.get_run(result["offRunId"]))["conversationId"] != (
            await repo.get_run(result["onRunId"])
        )["conversationId"]
    finally:
        await repo.close()


async def test_legacy_database_is_not_modified_by_vnext_repository(tmp_path):
    from platform_api.repository import Repository

    path = tmp_path / "legacy.db"
    legacy = Repository(path)
    await legacy.open()
    original = await legacy.create_run("keep me")
    await legacy.close()
    with pytest.raises(ValueError, match="schema"):
        await MultiRepository(path).open()
    legacy = Repository(path)
    await legacy.open()
    try:
        assert (await legacy.get_run(original["runId"]))["question"] == "keep me"
    finally:
        await legacy.close()


async def test_automatic_analysis_pins_configured_mode_and_source_context(tmp_path):
    repo = MultiRepository(tmp_path / "auto.db", auto_mode="on")
    await repo.open()
    try:
        snapshots = {"atcis": {"snapshotId": "frozen"}, "knccs": {"snapshotId": "other-frozen"}}
        await repo.save_source(
            "atcis",
            {"snapshotId": "frozen", "epochId": "e", "sequence": 1, "entities": []},
            {"eventId": "event", "epochId": "e", "sequence": 1, "type": "structure.changed"},
            snapshots,
        )
        run = (await repo.runs())[0]
        assert run["semanticMode"] == "on" and run["sourceSnapshotSet"] == snapshots
        await repo.save_source(
            "atcis",
            {"snapshotId": "tick", "epochId": "e", "sequence": 2, "entities": []},
            {"eventId": "tick", "epochId": "e", "sequence": 2, "type": "positions.updated"},
        )
        assert len(await repo.runs()) == 1
    finally:
        await repo.close()


async def test_comparison_restart_reconciles_interrupted_runs(tmp_path):
    from platform_api.multi_runtime import MultiRuntime

    repo = MultiRepository(tmp_path / "restart.db")
    await repo.open()
    try:
        comparison = await repo.create_comparison("question")
        pair = await repo.publish_comparison(
            comparison["comparisonId"], {"sourceSnapshotSet": {}}, {}
        )
        await repo.update_run(pair["offRunId"], {"status": "completed"})
        await repo.update_run(pair["onRunId"], {"status": "interrupted"})
        runtime = MultiRuntime(repo, None, {}, {})
        await runtime.reconcile_comparisons()
        assert (await repo.comparison(pair["comparisonId"]))["status"] == "incomplete"
    finally:
        await repo.close()


async def test_platform_ingests_two_sources_and_runs_native_mcp_without_semantic(tmp_path):
    import asyncio
    import json

    import httpx
    from conftest import server
    from platform_api.app import create_app

    class Provider:
        async def respond(self, inputs, **kwargs):
            outputs = [i for i in inputs if i.get("type") == "function_call_output"]
            if not outputs:
                return {
                    "status": "completed",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "atcis__list_equipment",
                            "call_id": "native-1",
                            "arguments": "{}",
                        }
                    ],
                }
            observation = json.loads(outputs[-1]["output"])
            result = {
                "outcome": "answer",
                "answer": "원천 모의 객체 조회 완료",
                "findings": [],
                "evidenceIds": [observation["evidenceId"]],
                "limitations": [],
                "courses": None,
            }
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }
                ],
            }

    with (
        server(
            "import uvicorn; from mock_atcis.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
            {"ATCIS_DB": str(tmp_path / "a.db"), "ATCIS_READ_TOKEN": ""},
        ) as a,
        server(
            "import uvicorn; from mock_knccs.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
            {"KNCCS_DB": str(tmp_path / "k.db"), "KNCCS_READ_TOKEN": ""},
        ) as k,
        server(
            "import uvicorn; from atcis_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
            {"ATCIS_BASE_URL": a, "ATCIS_READ_TOKEN": "", "ATCIS_MCP_TOKEN": ""},
        ) as am,
        server(
            "import uvicorn; from knccs_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
            {"KNCCS_BASE_URL": k, "KNCCS_READ_TOKEN": "", "KNCCS_MCP_TOKEN": ""},
        ) as km,
    ):
        sources = {
            s: {"url": u, "mcpUrl": m + "/mcp", "token": "", "mcpToken": ""}
            for s, u, m in (("atcis", a, am), ("knccs", k, km))
        }
        app = create_app(
            tmp_path / "platform-next.db",
            profile="heterogeneous",
            provider=Provider(),
            sources=sources,
        )
        terminal_updates = []
        original_update = app.state.repository.update_run

        async def track_update(rid, data):
            if data.get("status") not in (None, "queued", "running"):
                terminal_updates.append(data.copy())
            return await original_update(rid, data)

        app.state.repository.update_run = track_update
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            for _ in range(100):
                situation = (await client.get("/api/v1/situation")).json()
                if len(situation.get("entities", [])) == 9:
                    break
                await asyncio.sleep(0.05)
            assert len(situation["entities"]) == 9
            assert len({e["entityId"] for e in situation["entities"]}) == 9
            queued = (
                await client.post(
                    "/api/v1/analyses", json={"question": "모의 객체 보여줘", "semanticMode": "off"}
                )
            ).json()
            for _ in range(100):
                run = (await client.get("/api/v1/analyses/" + queued["runId"])).json()
                if run["status"] not in ("queued", "running"):
                    break
                await asyncio.sleep(0.05)
            assert run["status"] == "completed", run
            assert run["finishedAt"] >= run["startedAt"]
            assert all(update.get("finishedAt") for update in terminal_updates)
            assert run["toolCalls"][0]["name"] == "atcis__list_equipment"
            assert not any(t.startswith("semantic__") for t in run["toolDiscovery"]["tools"])
            assert set(run["sourceSnapshotSet"]) == {"atcis", "knccs"}
            assert (
                await client.post(
                    "/api/v1/analyses",
                    json={
                        "question": "follow up",
                        "semanticMode": "on",
                        "conversationId": run["conversationId"],
                    },
                )
            ).status_code == 409
            async with httpx.AsyncClient() as source:
                changed = await source.patch(a + "/api/v1/equipment/T-A03", json={"readyCode": "R"})
            assert changed.status_code == 200
            for _ in range(100):
                event_runs = [
                    r
                    for r in (await client.get("/api/v1/analyses")).json()["items"]
                    if r["trigger"] == "c4i_event"
                ]
                if event_runs:
                    break
                await asyncio.sleep(0.05)
            assert len(event_runs) == 1
            assert (
                event_runs[0]["sourceSnapshotSet"]["atcis"]["snapshotId"]
                == changed.json()["snapshotId"]
            )
