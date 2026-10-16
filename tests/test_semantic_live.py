"""Opt-in real GPT integration; never mixes test-provider results into live evidence."""

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from platform_api.app import create_app
from platform_api.providers.openai import OpenAIProvider
from semantic_support import stack


@pytest.mark.live
@pytest.mark.neo4j
async def test_real_gpt_semantic_comparison_with_pinned_snapshots(tmp_path):
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
        pytest.skip("Local OpenAI configuration missing; live validation NOT completed")
    with stack(tmp_path) as (sources, semantic):
        app = create_app(
            tmp_path / "platform.db",
            profile="heterogeneous",
            sources=sources,
            semantic_config=semantic,
            provider=OpenAIProvider(),
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            created = (
                await client.post(
                    "/api/v1/comparisons",
                    json={
                        "question": "모의 1사단의 가용한 탱크를 보여줘. 예하 조직을 포함하고, 가용·불가·미확인 수와 원천 객체 ID를 근거와 함께 구분해줘."
                    },
                )
            ).json()
            for _ in range(600):
                comparison = (
                    await client.get("/api/v1/comparisons/" + created["comparisonId"])
                ).json()
                if comparison["status"] not in ("preparing", "running"):
                    break
                await asyncio.sleep(0.5)
            runs = {
                mode: (await client.get("/api/v1/analyses/" + comparison[mode + "RunId"])).json()
                for mode in ("off", "on")
                if comparison.get(mode + "RunId")
            }
            Path("artifacts").mkdir(exist_ok=True)
            Path("artifacts/semantic-live-smoke-v2.json").write_text(
                json.dumps({"comparison": comparison, "runs": runs}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            assert comparison["status"] == "completed", {
                "status": comparison["status"],
                "error": comparison.get("error"),
                "runs": {
                    m: {"status": r["status"], "error": r.get("error")} for m, r in runs.items()
                },
            }
            assert runs["off"]["sourceSnapshotSet"] == runs["on"]["sourceSnapshotSet"]
            assert not any(c["name"].startswith("semantic__") for c in runs["off"]["toolCalls"])
            assert any(c["name"].startswith("semantic__") for c in runs["on"]["toolCalls"])
            for run in runs.values():
                assert run["result"]["evidenceIds"]
                assert "T-A01" in run["result"]["answer"] and "T-A02" in run["result"]["answer"]
