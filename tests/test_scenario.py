from collections import Counter

from c4i_contracts import EntityFilter
from mock_c4i.scenario import border_entities, border_scenario, initial_entities
from mock_c4i.store import C4IStore


async def test_border_seed_counts_pages_and_legacy_restart(tmp_path):
    seed, metadata = border_entities(), border_scenario()
    assert seed == border_entities()
    assert len(seed) == len({entity.entity_id for entity in seed}) == 120
    assert Counter(entity.kind.value for entity in seed) == {
        "tank": 40,
        "armored_vehicle": 24,
        "support_vehicle": 20,
        "uav": 12,
        "naval_vessel": 24,
    }
    sectors = {zone["id"]: zone for zone in metadata["zones"]}
    for entity in seed:
        zone = sectors[entity.unit_id.split(":")[1]]
        west, south, east, north = zone["bounds"]
        assert west <= entity.position.longitude <= east
        assert south <= entity.position.latitude <= north
        assert (entity.kind == "naval_vessel") == (zone["domain"] == "sea")
    store = C4IStore(tmp_path / "source.db")
    await store.open(initial_entities())
    old = await store.snapshot()
    await store.close()
    await store.open(seed, scenario=metadata)
    try:
        assert (await store.snapshot())["scenarioId"] == "west-coast-demo"
        await store.tick()
        assert store.state["scenarioId"] == "west-coast-demo"
        await store.reset()
        current = await store.snapshot()
        assert current["epochId"] != old["epochId"]
        assert current["scenario"]["scenarioId"] == metadata["scenarioId"]
        assert (await store.snapshot(old["snapshotId"]))["scenarioId"] == "west-coast-demo"
        first = await store.entities(None, EntityFilter(), 100)
        second = await store.entities(None, EntityFilter(), 100, first["nextCursor"])
        assert first["matchedCount"] == 120 and len(first["items"]) == 100
        assert len(second["items"]) == 20 and second["nextCursor"] is None
        assert (await store.summary(None, EntityFilter(), ["kind"]))["matchedCount"] == 120
        zones_summary = await store.summary(None, EntityFilter(), ["zoneId"])
        assert len(zones_summary["groups"]) == 8
        assert sum(group["count"] for group in zones_summary["groups"]) == 120
        await store.tick()
        assert store.state["scenarioId"] == metadata["scenarioId"]
    finally:
        await store.close()


async def test_legacy_platform_metadata_refresh_does_not_skip_events(tmp_path, c4i_url):
    import asyncio

    import httpx
    from platform_api.app import create_app
    from platform_api.repository import Repository
    from test_agent import FakeProvider

    async with httpx.AsyncClient() as source:
        initial = (
            await source.get(
                c4i_url + "/api/v1/snapshot", headers={"Authorization": "Bearer test-read"}
            )
        ).json()
        initial.pop("scenario")
        path = tmp_path / "old-platform.db"
        repo = Repository(path)
        await repo.open()
        await repo.bootstrap(initial)
        await repo.close()
        await source.patch(
            c4i_url + "/api/v1/entities/BLU-T01",
            json={"availability": "unavailable"},
            headers={"Authorization": "Bearer test-control"},
        )
    app = create_app(path, c4i_url=c4i_url, c4i_token="test-read", provider=FakeProvider([]))
    async with app.router.lifespan_context(app):
        for _ in range(100):
            snapshot = await app.state.repository.situation()
            runs = await app.state.repository.runs()
            if snapshot.get("scenario") and runs:
                break
            await asyncio.sleep(0.05)
        assert snapshot["scenario"]["scenarioId"] == "west-coast-demo"
        assert len(runs) == 1 and runs[0]["trigger"] == "c4i_event"
