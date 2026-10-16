"""Physical outage of ONLY the dedicated test container, restored in finally."""

import asyncio
import os
import subprocess
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from platform_api.app import create_app
from semantic_support import ScenarioProvider, stack


@pytest.mark.neo4j
async def test_real_neo4j_outage_preserves_sources_and_off_analysis(tmp_path):
    load_dotenv()
    if os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687") != "bolt://127.0.0.1:17687":
        pytest.skip("Physical outage test only controls the dedicated local test container")
    root = Path(__file__).resolve().parents[1]
    with stack(tmp_path) as (sources, semantic):
        app = create_app(
            tmp_path / "platform.db",
            profile="heterogeneous",
            sources=sources,
            semantic_config=semantic,
            provider=ScenarioProvider(),
        )
        try:
            async with (
                app.router.lifespan_context(app),
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client,
            ):
                await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "compose", "--profile", "test", "stop", "neo4j-test"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                )
                async with httpx.AsyncClient() as source:
                    assert (
                        await source.get(sources["atcis"]["url"] + "/api/v1/snapshot")
                    ).status_code == 200
                    assert (
                        await source.get(sources["knccs"]["url"] + "/api/v1/snapshot")
                    ).status_code == 200
                for mode in ("off", "on"):
                    created = (
                        await client.post(
                            "/api/v1/analyses",
                            json={"question": "모의 1사단의 가용한 탱크", "semanticMode": mode},
                        )
                    ).json()
                    for _ in range(250):
                        run = (await client.get("/api/v1/analyses/" + created["runId"])).json()
                        if run["status"] not in ("queued", "running"):
                            break
                        await asyncio.sleep(0.1)
                    assert run["status"] == ("completed" if mode == "off" else "failed"), run.get(
                        "error", run["status"]
                    )
                    if mode == "off":
                        assert run["result"]["answer"] and not any(
                            c["name"].startswith("semantic__") for c in run["toolCalls"]
                        )
                    else:
                        assert run["semanticMode"] == "on" and run["error"]
        finally:
            await asyncio.to_thread(
                subprocess.run,
                [
                    "docker",
                    "compose",
                    "--profile",
                    "test",
                    "up",
                    "-d",
                    "--wait",
                    "--wait-timeout",
                    "60",
                    "neo4j-test",
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
