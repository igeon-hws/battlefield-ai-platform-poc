import asyncio

import httpx
from conftest import server
from httpx import ASGITransport, AsyncClient
from platform_api.app import create_app
from platform_api.repository import Repository


async def test_fr02_running_c4i_moves_and_platform_replays_same_snapshot(tmp_path):
    code = "import uvicorn; from mock_c4i.app import create_app; uvicorn.run(create_app(token='',control_token=''),host='127.0.0.1',port=PORT,log_level='error')"
    with server(code, {"C4I_DB": str(tmp_path / "moving-source.db")}) as url:
        app = create_app(tmp_path / "moving-platform.db", c4i_url=url, c4i_token="")
        async with app.router.lifespan_context(app), httpx.AsyncClient() as source:
            initial = (await source.get(url + "/api/v1/snapshot")).json()
            await source.post(url + "/api/v1/simulation/start")
            for _ in range(100):
                mirrored = await app.state.repository.situation()
                if mirrored.get("simulationTime", 0) >= 1:
                    break
                await asyncio.sleep(0.05)
            assert mirrored["simulationTime"] >= 1
            original = (
                await source.get(url + "/api/v1/snapshots/" + mirrored["snapshotId"])
            ).json()
            assert mirrored["entities"] == original["entities"]
            assert any(
                a["position"] != b["position"]
                for a, b in zip(mirrored["entities"], initial["entities"])
            )
            assert not await app.state.repository.runs()  # position ticks never invoke the LLM


async def test_atomic_ingestion_duplicate_and_restart(tmp_path):
    repo = Repository(tmp_path / "platform.db")
    await repo.open()
    snapshot = {"snapshotId": "s1", "epochId": "e1", "sequence": 10, "entities": []}
    await repo.bootstrap(snapshot)
    event = {
        "eventId": "evt-1",
        "type": "entity.status_changed",
        "epochId": "e1",
        "sequence": 11,
        "snapshotId": "s2",
        "snapshot": {**snapshot, "snapshotId": "s2", "sequence": 11},
    }
    assert await repo.ingest(event)
    assert not await repo.ingest(event)
    assert len(await repo.runs()) == 1
    await repo.close()
    await repo.open()
    assert (await repo.situation())["snapshotId"] == "s2"
    assert len(await repo.runs()) == 1
    assert not await repo.ingest(event)
    await repo.close()


async def test_conversation_course_selection_and_invalid_reference(tmp_path):
    import pytest
    from platform_contracts.models import AnalysisResult
    from pydantic import ValidationError

    repo = Repository(tmp_path / "platform.db")
    await repo.open()
    run = await repo.create_run("방책")
    result = {
        "outcome": "answer",
        "answer": "비교",
        "findings": [],
        "evidenceIds": [],
        "limitations": [],
        "courses": [
            {
                "id": str(i),
                "title": str(i),
                "summary": "대안",
                "evidenceIds": [],
                "expectedEffects": [],
                "risksAndConstraints": [],
            }
            for i in range(3)
        ],
    }
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({**result, "courses": result["courses"][:2]})
    await repo.update_run(run["runId"], {"status": "completed", "result": result})
    saved = await repo.select(run["runId"], "1")
    assert saved["selectedCourseId"] == "1"
    with pytest.raises(ValueError):
        await repo.select(run["runId"], "missing")
    followup = await repo.create_run("그중 두 번째는?", run["conversationId"])
    assert (await repo.history(followup["conversationId"], followup["runId"]))[0][
        "content"
    ] == "방책"
    with pytest.raises(ValueError, match="busy"):
        await repo.create_run("중복", run["conversationId"])
    await repo.close()


async def test_platform_ingestion_and_missing_llm_status(tmp_path, c4i_url, mcp_url, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "")
    app = create_app(
        tmp_path / "platform.db",
        c4i_url=c4i_url,
        mcp_url=mcp_url,
        c4i_token="test-read",
        mcp_token="test-mcp",
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        for _ in range(100):
            situation = (await client.get("/api/v1/situation")).json()
            if situation.get("entities"):
                break
            await asyncio.sleep(0.05)
        assert len(situation["entities"]) == 11
        response = await client.post("/api/v1/analyses", json={"question": "적 탱크 수"})
        assert response.status_code == 202
        run_id = response.json()["runId"]
        for _ in range(100):
            run = (await client.get(f"/api/v1/analyses/{run_id}")).json()
            if run["status"] not in ("queued", "running"):
                break
            await asyncio.sleep(0.05)
        assert run["status"] == "failed"
        assert "OPENAI" in run["error"]
        assert run["result"] is None
        async with AsyncClient() as source:
            await source.patch(
                c4i_url + "/api/v1/entities/BLU-T01",
                json={"availability": "unavailable"},
                headers={"Authorization": "Bearer test-control"},
            )
        for _ in range(100):
            runs = (await client.get("/api/v1/analyses")).json()["items"]
            if any(item["trigger"] == "c4i_event" for item in runs):
                break
            await asyncio.sleep(0.05)
        assert any(item["trigger"] == "c4i_event" for item in runs)
        situation = (await client.get("/api/v1/situation")).json()
        assert (
            next(e for e in situation["entities"] if e["entityId"] == "BLU-T01")["availability"]
            == "unavailable"
        )
