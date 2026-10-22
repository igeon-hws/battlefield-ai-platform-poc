"""V3 contracts: native models remain independent of semantic interpretation."""

from importlib import import_module

import httpx
import pytest


@pytest.mark.parametrize("system", ["atcis", "knccs"])
async def test_v3_sources_pin_native_pages_documents_and_live_hash(tmp_path, system):
    module = import_module(f"mock_{system}.native")
    app = module.create_app(tmp_path / f"{system}.db", tick_enabled=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        snap = (await c.get("/api/v1/snapshot")).json()
        assert snap["datasetId"] == "c2-domain-demo-v3"
        sid = snap["snapshotId"]
        baseline = (await c.get("/api/v1/snapshots/" + snap["baselineSnapshotId"])).json()
        assert baseline["sourceTime"] == "2026-10-20T09:00:00Z"
        reports = baseline["records"]["reports" if system == "atcis" else "messages"]
        assert len(reports) == (1 if system == "atcis" else 0)
        resource = "equipment" if system == "atcis" else "own-forces"
        page = (await c.get(f"/api/v1/{resource}", params={"snapshotId": sid, "limit": 1})).json()
        if system == "atcis":
            assert page["nextOffset"] == 1 and page["total"] == 5
            assert page["items"][0]["equipmentId"] == "L-T01"
        else:
            assert page["header"]["continuation"] and page["header"]["total"] == 2
            assert page["payload"][0]["pennant"] == "N-S01"
        export = (await c.get("/api/v1/stable-export", params={"snapshotId": sid})).json()
        assert export["sourceSchemaVersion"] == "3.0.0"
        assert export["stableDataHash"] == snap["stableDataHash"]
        assert "availability" not in str(export["records"])
        docs = await c.get("/api/v1/documents", params={"snapshotId": sid})
        assert docs.status_code == 200
        await c.post("/api/v1/simulation/start")
        await app.state.store.tick()
        moved = (await c.get("/api/v1/snapshot")).json()
        assert moved["sequence"] > snap["sequence"]
        assert moved["stableDataHash"] == snap["stableDataHash"]
        assert (await c.get(f"/api/v1/snapshots/{sid}")).json() == snap
        assert (
            await c.get(f"/api/v1/{resource}", params={"snapshotId": "missing"})
        ).status_code == 404
        await c.post("/api/v1/scenario/reset")
        reset = (await c.get("/api/v1/snapshot")).json()
        assert reset["epochId"] != snap["epochId"]
        assert reset["stableDataHash"] != snap["stableDataHash"]


async def test_navy_composite_keys_and_cursor_cannot_cross_snapshot(tmp_path):
    from mock_knccs.native import create_app

    app = create_app(tmp_path / "navy.db", tick_enabled=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        s = (await c.get("/api/v1/snapshot")).json()
        params = {"snapshotId": s["snapshotId"], "limit": 1}
        p = (await c.get("/api/v1/contacts", params=params)).json()
        rows = p["payload"]
        while p["header"]["continuation"]:
            p = (
                await c.get(
                    "/api/v1/contacts",
                    params={**params, "continuation": p["header"]["continuation"]},
                )
            ).json()
            rows.extend(p["payload"])
        assert {(r["originator"], r["trackNo"]) for r in rows} == {
            ("NORTH", "077"),
            ("NORTH", "007"),
            ("SOUTH", "007"),
        }
        old_page = (await c.get("/api/v1/contacts", params=params)).json()
        await c.post("/api/v1/scenario/reset")
        newer = (await c.get("/api/v1/snapshot")).json()
        bad = await c.get(
            "/api/v1/contacts",
            params={
                "snapshotId": newer["snapshotId"],
                "continuation": old_page["header"]["continuation"],
            },
        )
        assert bad.status_code == 422


async def test_source_control_auth_and_stable_live_separation(tmp_path):
    from mock_atcis.native import create_app

    app = create_app(tmp_path / "land.db", tick_enabled=False, token="read", control_token="write")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        assert (await c.get("/api/v1/snapshot")).status_code == 401
        c.headers["Authorization"] = "Bearer read"
        before = (await c.get("/api/v1/snapshot")).json()
        assert (
            await c.patch("/api/v1/equipment/L-T01", json={"maintenanceCode": "PMC"})
        ).status_code == 401
        changed = await c.patch(
            "/api/v1/equipment/L-T01",
            headers={"Authorization": "Bearer write"},
            json={"maintenanceCode": "PMC"},
        )
        assert changed.status_code == 200
        assert changed.json()["stableDataHash"] == before["stableDataHash"]
        invalid = await c.patch(
            "/api/v1/equipment/L-T01",
            headers={"Authorization": "Bearer write"},
            json={"availability": "available"},
        )
        assert invalid.status_code == 422


@pytest.mark.parametrize(
    "system,master,state",
    [
        ("atcis", "land_equipment_master", "land_equipment_state"),
        ("knccs", "navy_force_master", "navy_force_state"),
    ],
)
async def test_native_databases_separate_master_and_live_state(tmp_path, system, master, state):
    app = import_module(f"mock_{system}.native").create_app(
        tmp_path / f"{system}.db", tick_enabled=False
    )
    async with app.router.lifespan_context(app):
        db = app.state.store.db
        async with db.execute(f"SELECT count(*) FROM {master}") as cursor:
            assert (await cursor.fetchone())[0] == (5 if system == "atcis" else 2)
        async with db.execute(f"SELECT count(*) FROM {state}") as cursor:
            assert (await cursor.fetchone())[0] == (5 if system == "atcis" else 2)


async def test_land_activity_and_report_changes_preserve_old_snapshot(tmp_path):
    from mock_atcis.native import create_app

    app = create_app(tmp_path / "source.db", tick_enabled=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        before = (await c.get("/api/v1/snapshot")).json()
        activity = await c.patch(
            "/api/v1/activities/A2", json={"state": "DONE", "evidenceReport": "R1"}
        )
        assert activity.status_code == 200
        assert activity.json()["stableDataHash"] == before["stableDataHash"]
        report = await c.post(
            "/api/v1/reports",
            json={
                "reportId": "R5",
                "revision": 3,
                "incidentId": "INC-1",
                "unitCode": "C111",
                "text": "추가 확인",
                "supersedes": "R4",
            },
        )
        assert report.status_code == 201
        assert report.json()["stableDataHash"] != before["stableDataHash"]
        old = (await c.get("/api/v1/snapshots/" + before["snapshotId"])).json()
        assert old == before


async def test_native_name_and_maritime_message_receipts_are_independent_events(tmp_path):
    from mock_atcis.native import create_app as land_app
    from mock_knccs.native import create_app as sea_app

    for app, path, body, expected_event in (
        (
            land_app(tmp_path / "land.db", tick_enabled=False),
            "/api/v1/units/C111",
            {"name": "모의 111중대 새 명칭"},
            "structure.changed",
        ),
        (
            sea_app(tmp_path / "sea.db", tick_enabled=False),
            "/api/v1/messages",
            {"serial": "M4", "thread": "INC-1", "text": "새 전문"},
            "message.received",
        ),
    ):
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
        ):
            before = (await c.get("/api/v1/snapshot")).json()
            result = await c.request("PATCH" if "units" in path else "POST", path, json=body)
            assert result.status_code in (200, 201)
            current = result.json()
            assert current["stableDataHash"] != before["stableDataHash"]
            events = (
                await c.get(
                    "/api/v1/events",
                    params={
                        "epochId": current["epochId"],
                        "throughSequence": current["sequence"],
                        "after": before["sequence"],
                    },
                )
            ).json()
            assert events["items"][-1]["type"] == expected_event
            if "messages" in path:
                receipt = await c.post(
                    "/api/v1/delivery-events",
                    json={"receiptId": "ACK2", "serial": "M4", "delivery": "ACK"},
                )
                assert receipt.status_code == 201
                assert receipt.json()["stableDataHash"] == current["stableDataHash"]
