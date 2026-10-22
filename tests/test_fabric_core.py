import httpx
import pytest


async def test_fabric_core_off_has_no_graph_dependency_and_pins_same_inputs(tmp_path):
    from mock_atcis.native import create_app as land_app
    from mock_knccs.native import create_app as sea_app
    from semantic_api.fabric import Fabric

    land, sea = (
        land_app(tmp_path / "land.db", tick_enabled=False),
        sea_app(tmp_path / "sea.db", tick_enabled=False),
    )
    async with land.router.lifespan_context(land), sea.router.lifespan_context(sea):
        apps = {"atcis": land, "knccs": sea}

        async def get(system, path, params=None):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=apps[system]), base_url="http://test"
            ) as c:
                r = await c.get("/api/v1" + path, params=params)
                r.raise_for_status()
                return r.json()

        fabric = Fabric({s: {"url": "http://unused"} for s in apps})
        fabric.get = get
        context = await fabric.prepare("off")
        assert context["semanticMode"] == "off" and context["graphInfo"] is None
        assert set(context["sourceSnapshotSet"]) == set(apps)
        assert len(context["documents"]) == 8  # source-qualified versions, no accidental merge
        replay = await fabric.prepare("off", context["sourceSnapshotSet"])
        assert replay["sourceSnapshotSet"] == context["sourceSnapshotSet"]
        assert replay["documents"] == context["documents"]
        situation = await fabric.situation()
        assert len(situation["sources"]["atcis"]["entities"]) == 5
        assert len(situation["sources"]["knccs"]["entities"]) == 5
        first = situation["sources"]["atcis"]["entities"][0]
        assert first["speedMps"] > 0
        assert first["displayVector"]["endPosition"] != first["position"]
        with pytest.raises(ValueError, match="Semantic"):
            await fabric.prepare("on", context["sourceSnapshotSet"])
        broken = {s: dict(r) for s, r in context["sourceSnapshotSet"].items()}
        broken["atcis"]["stableDataHash"] = "wrong"
        with pytest.raises(ValueError, match="snapshot"):
            await fabric.prepare("off", broken)
        original_get = fabric.get

        async def disconnected(system, path, params=None):
            if system == "knccs":
                raise httpx.ConnectError("test source unavailable")
            return await original_get(system, path, params)

        fabric.get = disconnected
        partial = await fabric.prepare("off", allow_partial=True)
        assert set(partial["sourceSnapshotSet"]) == {"atcis"}
        assert partial["coverage"]["knccs"] == "unavailable"
        with pytest.raises(ValueError):
            await fabric.prepare("on", allow_partial=True)


async def test_fabric_api_off_boots_without_neo4j_password(monkeypatch):
    from semantic_api.app import create_app

    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "3")
    # Explicit configuration must not silently reload a local password.
    app = create_app(token="")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        assert (await c.get("/health")).status_code == 200
        assert (await c.get("/v1/catalog")).status_code == 200
