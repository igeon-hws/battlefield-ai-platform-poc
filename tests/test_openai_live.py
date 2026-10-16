"""Explicit opt-in only: pytest -m live (makes billable OpenAI requests)."""

import os

import pytest
from dotenv import load_dotenv
from platform_api.agent.loop import AgentLoop
from platform_api.agent.tools import ToolRunner
from platform_api.mcp.client import MCPClient
from platform_api.providers.openai import OpenAIProvider


@pytest.mark.live
async def test_real_gpt_native_tool_calling_and_three_courses(mcp_url, tmp_path):
    load_dotenv()
    missing = [name for name in ("OPENAI_API_KEY", "OPENAI_MODEL") if not os.getenv(name)]
    if missing:
        pytest.skip("Missing local configuration: " + ", ".join(missing))
    async with MCPClient(mcp_url, token="test-mcp") as client:
        runner = ToolRunner(client)
        result = await AgentLoop(OpenAIProvider(), runner).run(
            "현재 등록된 적 탱크는 몇 대인지 조회해줘. 집계 결과에 근거해서 상황 정보의 확인·관찰에 관한 대안 세 가지도 비교해줘. 실제 전투 명령은 요청하지 않는다."
        )
    assert result["status"] == "completed", result.get("error", result["status"])
    assert any(call["name"] == "c4i_summarize_entities" for call in result["toolCalls"])
    counts = [e for e in result["evidence"] if e["tool"] == "c4i_summarize_entities"]
    assert any(e["data"]["matchedCount"] == 3 for e in counts)
    assert len(result["result"]["courses"]) == 3
    assert result["result"]["evidenceIds"]
    from platform_api.repository import Repository

    repo = Repository(tmp_path / "live-conversation.db")
    await repo.open()
    try:
        first = await repo.create_run("상황 확인 대안 비교")
        await repo.update_run(first["runId"], result)
        selected = result["result"]["courses"][1]
        await repo.select(first["runId"], selected["id"])
        history = await repo.history(first["conversationId"])
        async with MCPClient(mcp_url, token="test-mcp") as client:
            followup = await AgentLoop(OpenAIProvider(), ToolRunner(client)).run(
                "내가 선택한 방책의 제목을 원문 그대로 알려주고 내용을 설명해줘. 현재 상황을 새로 분석할 필요는 없어.",
                history=history,
            )
        assert followup["status"] == "completed", followup.get("error", followup["status"])
        assert selected["title"] in followup["result"]["answer"]
        assert followup["result"]["courses"] is None
    finally:
        await repo.close()


@pytest.mark.live
async def test_real_gpt_uses_geo_tool_for_synthetic_coordinates(mcp_url):
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
        pytest.skip("Missing local OpenAI configuration")
    async with MCPClient(mcp_url, token="test-mcp") as client:
        result = await AgentLoop(OpenAIProvider(), ToolRunner(client)).run(
            "모의 객체 BLU-T01과 BLU-T02의 현재 좌표를 조회하고 두 객체 사이 지리적 거리(m)와 첫 객체에서 두 번째 객체로 향하는 방위각을 계산해줘. 방책은 필요 없어."
        )
    assert result["status"] == "completed", result.get("error", result["status"])
    measurements = [item for item in result["evidence"] if item["tool"] == "geo_measure"]
    assert measurements
    from battlefield_geo import measure
    from c4i_contracts import Position

    expected = measure(
        Position(longitude=126.585, latitude=36.875), Position(longitude=126.610, latitude=36.860)
    )
    assert measurements[-1]["data"]["distanceMeters"] == pytest.approx(
        expected["distanceMeters"], abs=0.01
    )
    assert measurements[-1]["data"]["bearingDegrees"] == pytest.approx(
        expected["bearingDegrees"], abs=0.01
    )
    assert result["result"]["evidenceIds"]
    assert result["result"]["courses"] is None
