import asyncio
from copy import deepcopy
from uuid import uuid4

from battlefield_geo import measure
from c4i_contracts import Model, Position
from platform_api.mcp.schema import native_definition, normalize_arguments
from platform_contracts.models import strict_schema
from pydantic import Field

C4I_ALLOWED_TOOLS = frozenset(
    {
        "c4i_get_snapshot",
        "c4i_list_entities",
        "c4i_summarize_entities",
        "c4i_get_entity",
        "c4i_get_changes",
        "c4i_list_events",
        "c4i_list_entity_history",
    }
)


class EvidenceArgs(Model):
    evidence_id: str = Field(description="현재 run에서 발급한 근거 ID")


class GeoArgs(EvidenceArgs):
    first_entity_id: str
    second_entity_id: str


LOCAL_MODELS: dict[str, type[Model]] = {"read_evidence": EvidenceArgs, "geo_measure": GeoArgs}
LOCAL_DESCRIPTIONS = {
    "read_evidence": "현재 run의 evidenceId로 이미 확보한 원문을 다시 읽는다. 다른 run의 근거는 사용할 수 없으며 새 C4I 조회가 아니다. 반환은 원래 evidenceId/tool/arguments/data. 없는 ID는 오류다.",
    "geo_measure": "같은 c4i_list_entities 근거의 data.items에 포함된 두 모의 객체 사이 WGS84 거리·방위를 계산한다. evidenceId, firstEntityId(출발), secondEntityId(도착)가 필요하다. 반환 distanceMeters(m), bearingDegrees(북0·동90), algorithm, inputEvidenceIds, snapshotId. 경로 거리·도달 시간은 아니다. 후보 비교 시 모든 페이지·후보를 확보하고 동률·0건을 명시한다.",
}
LOCAL_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": name,
        "description": LOCAL_DESCRIPTIONS[name],
        "strict": True,
        "parameters": strict_schema(model.model_json_schema(by_alias=True)),
    }
    for name, model in LOCAL_MODELS.items()
]


class ToolRunner:
    def __init__(self, mcp, snapshot=None):
        self.mcp, self.snapshot = mcp, snapshot
        self.evidence: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.registry: dict[str, dict] = {}
        self.definitions = deepcopy(LOCAL_TOOL_DEFINITIONS)
        self.prepared = False
        self.discovery_error: str | None = None

    async def prepare(self):
        if self.prepared:
            return
        try:
            async with asyncio.timeout(5):
                tools = await self.mcp.list_tools()
        except Exception:  # noqa: BLE001 - discovery failure preserves tool-free explanations
            self.discovery_error = (
                "MCP tool discovery unavailable; current C4I facts cannot be verified"
            )
            self.prepared = True
            return
        registry = {}
        definitions = deepcopy(LOCAL_TOOL_DEFINITIONS)
        seen = set()
        for tool in tools:
            name = tool["name"]
            if name in seen or name in LOCAL_MODELS:
                raise ValueError("duplicate or conflicting MCP tool name")
            seen.add(name)
            if name not in C4I_ALLOWED_TOOLS:
                continue
            registry[name] = deepcopy(tool)
            definitions.append(native_definition(tool))
        self.registry, self.definitions = registry, definitions
        self.prepared = True

    async def execute(self, name: str, arguments: dict):
        if name not in LOCAL_MODELS and name not in C4I_ALLOWED_TOOLS:
            raise ValueError("tool_not_allowed")
        await self.prepare()
        if name in LOCAL_MODELS:
            args = (
                LOCAL_MODELS[name].model_validate(arguments).model_dump(mode="json", by_alias=True)
            )
        else:
            if name not in self.registry:
                raise ValueError("MCP tool not discovered")
            args = normalize_arguments(self.registry[name]["inputSchema"], arguments)
        if name == "read_evidence":
            if args["evidenceId"] not in self.evidence:
                raise ValueError("evidence_not_found")
            return self.evidence[args["evidenceId"]]
        if name == "geo_measure":
            evidence = self.evidence.get(args["evidenceId"])
            if not evidence:
                raise ValueError("evidence_not_found")
            positions = {
                e["entityId"]: Position.model_validate(e["position"])
                for e in evidence["data"].get("items", [])
            }
            if not self.snapshot or any(
                args[key] not in positions for key in ("firstEntityId", "secondEntityId")
            ):
                raise ValueError("objects must be present in the same list evidence")
            data = measure(positions[args["firstEntityId"]], positions[args["secondEntityId"]]) | {
                "inputEvidenceIds": [args["evidenceId"]],
                "snapshotId": self.snapshot["snapshotId"],
            }
        else:
            if name != "c4i_get_snapshot" and not self.snapshot:
                raise ValueError("snapshot_required")
            if self.snapshot:
                sid = args.get("snapshotId", args.get("toSnapshotId"))
                if name == "c4i_get_snapshot":
                    sid = sid or self.snapshot["snapshotId"]
                    args["snapshotId"] = sid
                if sid is not None and sid != self.snapshot["snapshotId"]:
                    raise ValueError("snapshot_mismatch")
                if name in ("c4i_list_events", "c4i_list_entity_history") and (
                    args["epochId"] != self.snapshot["epochId"]
                    or args["throughSequence"] > self.snapshot["sequence"]
                ):
                    raise ValueError("snapshot_mismatch")
            data = await self.mcp.call(name, args)
            if name == "c4i_get_snapshot":
                self.snapshot = data
            elif data.get("snapshotId") and data["snapshotId"] != self.snapshot["snapshotId"]:
                raise ValueError("response_snapshot_mismatch")
        eid = "ev-" + uuid4().hex[:12]
        evidence = {"evidenceId": eid, "tool": name, "arguments": args, "data": data}
        self.evidence[eid] = evidence
        return evidence
