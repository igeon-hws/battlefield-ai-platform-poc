"""Test-only stack/provider. Production dev profiles always use the real GPT provider."""

import json
import os
from contextlib import ExitStack, contextmanager

from conftest import server


class ScenarioProvider:
    async def respond(self, inputs, **kwargs):
        observations = [
            json.loads(i["output"]) for i in inputs if i.get("type") == "function_call_output"
        ]
        by_tool = {o.get("tool"): o for o in observations}
        on = any(t["name"].startswith("semantic__") for t in kwargs["tools"])
        if on and "semantic__resolve_unit_scope" not in by_tool:
            name, args = "semantic__resolve_unit_scope", {"term": "모의 1사단"}
        elif on and "semantic__find_equipment_refs" not in by_tool:
            name, args = (
                "semantic__find_equipment_refs",
                {
                    "unitIds": by_tool["semantic__resolve_unit_scope"]["data"]["unitIds"],
                    "kind": "tank",
                },
            )
        elif not on and "atcis__list_units" not in by_tool:
            name, args = "atcis__list_units", {}
        elif not on and "atcis__list_unit_relations" not in by_tool:
            name, args = "atcis__list_unit_relations", {}
        elif on and "semantic__interpret_concept" not in by_tool:
            name, args = "semantic__interpret_concept", {"term": "available"}
        elif "atcis__list_equipment" not in by_tool:
            name, args = "atcis__list_equipment", {"typeCode": "TANK", "unitIds": ["B11", "C111"]}
        elif "aggregate_evidence" not in by_tool:
            scopes = (
                [by_tool["semantic__resolve_unit_scope"]]
                if on
                else [by_tool["atcis__list_units"], by_tool["atcis__list_unit_relations"]]
            )
            identities = [by_tool["semantic__find_equipment_refs"]] if on else []
            name, args = (
                "aggregate_evidence",
                {
                    "evidenceIds": [by_tool["atcis__list_equipment"]["evidenceId"]],
                    "identityEvidenceIds": [e["evidenceId"] for e in identities],
                    "conceptEvidenceIds": [by_tool["semantic__interpret_concept"]["evidenceId"]]
                    if on
                    else [],
                    "scopeEvidenceIds": [e["evidenceId"] for e in scopes] if on else [],
                    "unitIds": ["atcis:D1", "atcis:B11", "atcis:C111"] if on else None,
                    "kind": "tank" if on else None,
                    "groupBy": None if on else "readyCode",
                },
            )
        else:
            evidence = by_tool["aggregate_evidence"]
            result = {
                "outcome": "answer",
                "answer": f"모의 1사단의 가용 탱크는 {(evidence['data'].get('confirmedAvailable') if on else evidence['data']['counts']['atcis:R'])}대입니다.",
                "findings": [],
                "evidenceIds": [evidence["evidenceId"]],
                "limitations": ["테스트 모델 어댑터 결과"],
                "courses": None,
            }
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": json.dumps(result, ensure_ascii=False)}
                        ],
                    }
                ],
            }
        return {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": name,
                    "call_id": "test-call-" + str(len(observations)),
                    "arguments": json.dumps(args),
                }
            ],
        }


@contextmanager
def stack(tmp_path):
    with ExitStack() as contexts:
        sources = {}
        for system in ("atcis", "knccs"):
            source = contexts.enter_context(
                server(
                    f"import uvicorn; from mock_{system}.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                    {
                        f"{system.upper()}_DB": str(tmp_path / f"{system}.db"),
                        f"{system.upper()}_READ_TOKEN": "",
                        f"{system.upper()}_CONTROL_TOKEN": "",
                    },
                )
            )
            mcp = contexts.enter_context(
                server(
                    f"import uvicorn; from {system}_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                    {
                        f"{system.upper()}_BASE_URL": source,
                        f"{system.upper()}_READ_TOKEN": "",
                        f"{system.upper()}_MCP_TOKEN": "",
                    },
                )
            )
            sources[system] = {"url": source, "mcpUrl": mcp + "/mcp", "token": "", "mcpToken": ""}
        env = {
            "NEO4J_URI": os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687"),
            "ATCIS_BASE_URL": sources["atcis"]["url"],
            "KNCCS_BASE_URL": sources["knccs"]["url"],
            "ATCIS_READ_TOKEN": "",
            "KNCCS_READ_TOKEN": "",
            "BUILDER_ADMIN_TOKEN": "test-admin",
            "SEMANTIC_READ_TOKEN": "",
        }
        builder = contexts.enter_context(
            server(
                "import uvicorn; from graph_builder.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                env,
            )
        )
        api = contexts.enter_context(
            server(
                "import uvicorn; from semantic_api.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                env,
            )
        )
        mcp = contexts.enter_context(
            server(
                "import uvicorn; from semantic_mcp.server import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
                {"SEMANTIC_BASE_URL": api, "SEMANTIC_READ_TOKEN": "", "SEMANTIC_MCP_TOKEN": ""},
            )
        )
        yield (
            sources,
            {
                "url": api,
                "token": "",
                "mcpUrl": mcp + "/mcp",
                "mcpToken": "",
                "builderUrl": builder,
                "adminToken": "test-admin",
            },
        )


def platform_app():
    from platform_api.app import create_app

    return create_app(profile="heterogeneous", provider=ScenarioProvider())
