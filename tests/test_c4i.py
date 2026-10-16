import pytest
from battlefield_geo import advance, decorate
from c4i_contracts import Entity, EntityFilter
from httpx import ASGITransport, AsyncClient
from mock_c4i.app import create_app
from mock_c4i.store import C4IStore, CursorExpired
from pydantic import ValidationError


def entity(**overrides):
    return Entity.model_validate(
        {
            "entityId": "T-1",
            "kind": "tank",
            "label": "Alpha",
            "affiliation": "friendly",
            "availability": "available",
            "position": {"longitude": 126.5, "latitude": 36.5},
            "velocity": {"eastMps": 10, "northMps": 0},
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "east,north,bearing", [(0, 10, 0), (10, 0, 90), (0, -10, 180), (-10, 0, 270)]
)
def test_fr02_geodesic_motion(east, north, bearing):
    source = entity(velocity={"eastMps": east, "northMps": north})
    moved = advance(source, 1)
    from pyproj import Geod

    azimuth, _, distance = Geod(ellps="WGS84").inv(
        source.position.longitude,
        source.position.latitude,
        moved.position.longitude,
        moved.position.latitude,
    )
    assert distance == pytest.approx(10, abs=0.01)
    assert azimuth % 360 == pytest.approx(bearing, abs=0.001)
    assert source.position != moved.position


def test_fr02_stationary_and_invalid_coordinates():
    inactive = entity(status="inactive")
    assert advance(inactive, 1).position == inactive.position
    assert decorate(entity(velocity={"eastMps": 0, "northMps": 0}))["displayVector"] is None
    with pytest.raises(ValidationError):
        entity(position={"longitude": 300, "latitude": 36})
    with pytest.raises(ValidationError):
        entity(velocity={"eastMps": float("nan"), "northMps": 0})


async def test_fr09_filters_counts_and_unknown_are_independent(tmp_path):
    store = C4IStore(tmp_path / "c4i.db")
    await store.open(
        [
            entity(),
            entity(entityId="T-2", affiliation="hostile", availability="unknown"),
            entity(entityId="T-3", affiliation="hostile", availability="unavailable"),
            entity(entityId="S-1", kind="naval_vessel", affiliation="hostile"),
        ]
    )
    snapshot = await store.snapshot()
    sid = snapshot["snapshotId"]
    tanks = await store.entities(sid, EntityFilter(kind="tank", affiliation="hostile"), limit=1)
    assert tanks["matchedCount"] == 2 and len(tanks["items"]) == 1
    assert tanks["nextCursor"] is not None
    summary = await store.summary(
        sid, EntityFilter(kind="tank", affiliation="hostile"), ["availability"]
    )
    assert summary["matchedCount"] == 2
    assert {g["availability"]: g["count"] for g in summary["groups"]} == {
        "unknown": 1,
        "unavailable": 1,
    }
    available = await store.entities(sid, EntityFilter(kind="tank", availability="available"))
    assert [e["entityId"] for e in available["items"]] == ["T-1"]
    assert (await store.summary(sid, EntityFilter(kind="unknown"), []))["matchedCount"] == 0
    await store.close()


async def test_fr03_immutable_snapshot_replay_restart_reset(tmp_path):
    path = tmp_path / "c4i.db"
    store = C4IStore(path)
    await store.open([entity()])
    initial = await store.snapshot()
    await store.patch("T-1", {"availability": "unavailable"})
    changed = await store.snapshot()
    assert changed["revision"] > initial["revision"]
    assert (await store.entities(initial["snapshotId"], EntityFilter()))["items"][0][
        "availability"
    ] == "available"
    events = await store.events(initial["epochId"], initial["sequence"])
    assert len(events) == 1 and events[0]["type"] == "entity.status_changed"
    assert events[0]["snapshotId"] == changed["snapshotId"]
    await store.tick()
    await store.reset()
    reset = await store.snapshot()
    assert reset["epochId"] != initial["epochId"]
    assert (await store.events(initial["epochId"], initial["sequence"]))[0] == events[0]
    with pytest.raises(CursorExpired):
        await store.events("missing", 0)
    await store.close()
    reopened = C4IStore(path)
    await reopened.open([entity()])
    assert (await reopened.snapshot())["snapshotId"] == reset["snapshotId"]
    await reopened.close()


async def test_fr01_public_api_auth_validation_and_summary_route(tmp_path):
    app = create_app(
        tmp_path / "c4i.db",
        tick_enabled=False,
        token="secret",
        control_token="control",
        scenario_id="west-coast-demo",
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        assert (await client.get("/api/v1/snapshot")).status_code == 401
        headers = {"Authorization": "Bearer secret"}
        snapshot = (await client.get("/api/v1/snapshot", headers=headers)).json()
        response = await client.get(
            "/api/v1/entities/summary",
            params={"atSnapshot": snapshot["snapshotId"], "kind": "tank"},
            headers=headers,
        )
        assert response.status_code == 200 and response.json()["matchedCount"] > 0
        assert (
            await client.get("/api/v1/entities/summary", params={"kind": "typo"}, headers=headers)
        ).status_code == 422
        assert (
            await client.patch(
                "/api/v1/entities/BLU-T01",
                json={"availability": "unavailable"},
                headers=headers,
            )
        ).status_code == 401
        control = {"Authorization": "Bearer control"}
        assert (
            await client.patch(
                "/api/v1/entities/BLU-T01",
                json={"availability": "unavailable"},
                headers=control,
            )
        ).status_code == 200
        assert (await client.get("/api/v1/missing", headers=headers)).status_code == 404
