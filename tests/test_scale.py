import asyncio
import json
import platform
import time
from datetime import UTC, datetime
from statistics import quantiles

import httpx
import pytest
from conftest import server
from platform_api.app import create_app
from test_agent import FakeProvider


@pytest.mark.performance
async def test_120_entities_stream_for_60_seconds(tmp_path):
    code = "import uvicorn; from mock_c4i.app import create_app; uvicorn.run(create_app(token='',control_token='',scenario_id='border-demo'),host='127.0.0.1',port=PORT,log_level='error')"
    with server(code, {"C4I_DB": str(tmp_path / "scale-source.db")}) as url:
        provider = FakeProvider([])
        app = create_app(
            tmp_path / "scale-platform.db", c4i_url=url, c4i_token="", provider=provider
        )
        async with app.router.lifespan_context(app), httpx.AsyncClient(base_url=url) as source:
            await source.post("/api/v1/simulation/start")
            latencies = []
            seen = set()
            start = time.monotonic()
            while time.monotonic() - start < 60:
                snapshot = await app.state.repository.situation()
                if snapshot.get("simulationTime", 0) > 0 and snapshot["snapshotId"] not in seen:
                    seen.add(snapshot["snapshotId"])
                    latencies.append(
                        (
                            datetime.now(UTC) - datetime.fromisoformat(snapshot["sourceTime"])
                        ).total_seconds()
                    )
                    assert len(snapshot["entities"]) == 120
                await asyncio.sleep(0.1)
            mirrored = await app.state.repository.situation()
            original = (await source.get("/api/v1/snapshots/" + mirrored["snapshotId"])).json()
            assert mirrored["entities"] == original["entities"]
            assert mirrored["simulationTime"] >= 55 and len(latencies) >= 55
            p95 = quantiles(latencies, n=100)[94]
            print(
                json.dumps(
                    {
                        "environment": platform.platform(),
                        "python": platform.python_version(),
                        "entities": 120,
                        "durationSeconds": round(time.monotonic() - start, 2),
                        "samples": len(latencies),
                        "latencyP95Seconds": round(p95, 4),
                        "maxSeconds": round(max(latencies), 4),
                    }
                )
            )
            assert p95 < 2
            assert not provider.inputs
            assert not await app.state.repository.runs()
