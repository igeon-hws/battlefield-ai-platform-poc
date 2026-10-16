import httpx
import pytest
from mock_atcis.app import create_app


@pytest.mark.parametrize(
    "module,system,key",
    [("mock_atcis.app", "atcis", "tracks"), ("mock_knccs.app", "knccs", "contacts")],
)
async def test_sources_own_native_snapshot_history_and_state(tmp_path, module, system, key):
    from importlib import import_module

    app = import_module(module).create_app(tmp_path / f"{system}.db", tick_enabled=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        first = (await client.get("/api/v1/snapshot")).json()
        assert first["systemId"] == system and first[key]
        assert first[key][0].get("observedAt" if system == "atcis" else "reportTime")
        stable = (
            await client.get("/api/v1/stable-export", params={"snapshotId": first["snapshotId"]})
        ).json()
        assert "availability" not in stable["equipment"][0]
        assert stable["stableDataHash"] == first["stableDataHash"]
        await client.post("/api/v1/simulation/start")
        await app.state.store.tick()
        moved = (await client.get("/api/v1/snapshot")).json()
        assert moved[key][0] != first[key][0]
        assert moved["stableDataHash"] == first["stableDataHash"]
        old = (await client.get(f"/api/v1/snapshots/{first['snapshotId']}")).json()
        assert old == first
        assert (
            await client.get(
                "/api/v1/equipment", params={"snapshotId": first["snapshotId"], "limit": 1}
            )
        ).json()["nextCursor"] == 1
        await client.post("/api/v1/scenario/reset")
        reset = (await client.get("/api/v1/snapshot")).json()
        assert reset["epochId"] != first["epochId"]
        assert reset["stableDataHash"] != first["stableDataHash"]
        events = (
            await client.get(
                "/api/v1/events",
                params={
                    "epochId": first["epochId"],
                    "after": 0,
                    "throughSequence": moved["sequence"],
                },
            )
        ).json()
        assert all(e["epochId"] == first["epochId"] for e in events["items"])


async def test_atcis_raw_organization_and_changes_are_queryable(tmp_path):
    app = create_app(tmp_path / "atcis.db", tick_enabled=False, token="read", control_token="write")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer read"},
        ) as client,
    ):
        snapshot = (await client.get("/api/v1/snapshot")).json()
        sid = snapshot["snapshotId"]
        units = (await client.get("/api/v1/units", params={"snapshotId": sid})).json()
        assert any(u["unitCode"] == "D1" for u in units["items"])
        assert (
            await client.patch("/api/v1/equipment/T-A01", json={"readyCode": "N"})
        ).status_code == 401
        changed = await client.patch(
            "/api/v1/equipment/T-A01",
            json={"readyCode": "N"},
            headers={"Authorization": "Bearer write"},
        )
        assert changed.status_code == 200
        assert changed.json()["stableDataHash"] == snapshot["stableDataHash"]
        structural = await client.patch(
            "/api/v1/equipment/T-A01",
            json={"ownerUnitCode": "D2"},
            headers={"Authorization": "Bearer write"},
        )
        assert structural.json()["stableDataHash"] != snapshot["stableDataHash"]
        identity = (await client.get("/api/v1/identity-records", params={"snapshotId": sid})).json()
        assert any(i["exerciseAssetRef"] == "EX-U01" for i in identity["items"])
        assert (
            await client.get("/api/v1/equipment", params={"snapshotId": "nonexistent"})
        ).status_code == 404
        assert (
            await client.patch(
                "/api/v1/equipment/T-A01",
                json={"bogus": 1},
                headers={"Authorization": "Bearer write"},
            )
        ).status_code == 422
