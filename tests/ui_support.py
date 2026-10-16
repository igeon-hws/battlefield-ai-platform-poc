"""Test-only provider. Never imported by production entry points."""

import json
from hashlib import sha256

from platform_api.app import create_app


class UIProvider:
    async def respond(self, inputs, **kwargs):
        outputs = [item for item in inputs if item.get("type") == "function_call_output"]
        if not outputs:
            name, args = "c4i_get_snapshot", {}
        elif len(outputs) == 1:
            snapshot = json.loads(outputs[-1]["output"])["data"]
            name, args = (
                "c4i_summarize_entities",
                {
                    "snapshotId": snapshot["snapshotId"],
                    "filter": {"kind": "tank", "affiliation": "hostile"},
                },
            )
        else:
            observation = json.loads(outputs[-1]["output"])
            evidence_id = observation["evidenceId"]
            question = [item["content"] for item in inputs if item.get("role") == "user"][-1]
            course_prefix = sha256(question.encode()).hexdigest()[:8]
            result = {
                "outcome": "answer",
                "answer": f"등록된 적 탱크는 {observation['data']['matchedCount']}대입니다. 원천 모의 시나리오 기준이며 가용 상태 전체를 포함합니다.",
                "findings": [],
                "evidenceIds": [evidence_id],
                "limitations": ["테스트 모델 어댑터 결과"],
                "courses": [
                    {
                        "id": f"{course_prefix}-course-{i}",
                        "title": f"검토 대안 {i}",
                        "summary": "모의 상황 데이터의 추가 확인을 위한 비교 대안입니다.",
                        "evidenceIds": [evidence_id],
                        "expectedEffects": ["상황 정보의 최신성 확인"],
                        "risksAndConstraints": ["모의 데이터에 한정됨"],
                    }
                    for i in range(1, 4)
                ],
            }
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }
                ],
            }
        return {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": name,
                    "arguments": json.dumps(args),
                    "call_id": f"call-{len(outputs)}",
                }
            ],
        }


def app():
    return create_app(provider=UIProvider())
