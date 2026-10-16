import json
from copy import deepcopy
from pathlib import Path

import pytest
from platform_api.agent.multi_tools import MultiToolRunner


def snapshots():
    return {
        s: {
            "datasetId": "semantic-demo-v1",
            "epochId": s + "-epoch-1",
            "snapshotId": s + "-snapshot",
            "sequence": 1,
            "sourceTime": "2026-10-16T00:00:00Z",
            "stableDataHash": s + "-hash",
        }
        for s in ("atcis", "knccs")
    }


class Source:
    def __init__(self, system):
        self.system = system
        self.calls = []
        self.discovered = 0
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/semantic-demo-v1/sources.json").read_text(
                encoding="utf-8"
            )
        )[system]
        self.data = []
        for e in fixture["equipment"]:
            if system == "atcis":
                self.data.append(
                    {
                        "trackKey": e["nativeId"],
                        "ownerUnitCode": e["unitId"],
                        "classCode": "TANK" if e["kind"] == "tank" else "UAV",
                        "readyCode": {"available": "R", "unavailable": "N", "unknown": "U"}[
                            e["availability"]
                        ],
                        "exerciseAssetRef": e["exerciseAssetRef"],
                    }
                )
            else:
                self.data.append(
                    {
                        "contactNo": e["nativeId"],
                        "orgRef": e["unitId"],
                        "platformCategory": "SURFACE" if e["kind"] == "naval_vessel" else "AIR",
                        "aircraftType": "UNMANNED",
                        "serviceability": {
                            "available": "READY",
                            "unavailable": "NOT_READY",
                            "unknown": "UNCONFIRMED",
                        }[e["availability"]],
                        "exerciseAssetRef": e["exerciseAssetRef"],
                    }
                )

    async def list_tools(self):
        self.discovered += 1
        return [
            {
                "name": name,
                "description": "Read source data at snapshotId",
                "inputSchema": {
                    "type": "object",
                    "properties": {"snapshotId": {"type": "string"}},
                    "required": ["snapshotId"],
                },
            }
            for name in ("list_equipment", "list_identity_records")
        ]

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {
            "systemId": self.system,
            **snapshots()[self.system],
            "items": deepcopy(self.data),
            "matchedCount": len(self.data),
            "nextCursor": None,
        }


async def test_off_discovery_is_source_only_and_wrong_snapshots_are_rejected():
    clients = {s: Source(s) for s in ("atcis", "knccs", "semantic") if s != "semantic"}
    clients["semantic"] = Source("atcis")
    runner = MultiToolRunner(clients, snapshots(), "off")
    await runner.prepare()
    assert clients["semantic"].discovered == 0
    assert {"atcis__list_equipment", "knccs__list_equipment"} <= {
        d["name"] for d in runner.definitions
    }
    assert not any(d["name"].startswith("semantic__") for d in runner.definitions)
    with pytest.raises(ValueError, match="not_allowed"):
        await runner.execute("semantic__resolve_entity", {})
    with pytest.raises(ValueError, match="snapshot_mismatch"):
        await runner.execute("atcis__list_equipment", {"snapshotId": "newer"})
    result = await runner.execute("atcis__list_equipment", {})
    assert result["systemId"] == "atcis"
    assert clients["atcis"].calls[0][1]["snapshotId"] == snapshots()["atcis"]["snapshotId"]
    with pytest.raises(ValueError, match="evidence_not_found"):
        await runner.execute("read_evidence", {"evidenceId": "previous-on-run"})


async def test_off_aggregation_never_resolves_cross_system_identity():
    runner = MultiToolRunner({s: Source(s) for s in ("atcis", "knccs")}, snapshots(), "off")
    a = await runner.execute("atcis__list_equipment", {})
    k = await runner.execute("knccs__list_equipment", {})
    identity = [await runner.execute(s + "__list_identity_records", {}) for s in ("atcis", "knccs")]
    with pytest.raises(ValueError, match="semantic.*off"):
        await runner.execute(
            "aggregate_evidence",
            {
                "evidenceIds": [a["evidenceId"], k["evidenceId"]],
                "identityEvidenceIds": [i["evidenceId"] for i in identity],
            },
        )
    result = await runner.execute(
        "aggregate_evidence", {"evidenceIds": [a["evidenceId"], k["evidenceId"]]}
    )
    assert result["data"]["rawRecordCount"] == 9
    assert "resolvedUniqueCount" not in result["data"]
    runner.evidence[a["evidenceId"]]["data"]["nextCursor"] = 100
    with pytest.raises(ValueError, match="incomplete"):
        await runner.execute("aggregate_evidence", {"evidenceIds": [a["evidenceId"]]})


async def test_on_requires_valid_graph_snapshot_correspondence():
    with pytest.raises(ValueError, match="graph"):
        MultiToolRunner(
            {},
            snapshots(),
            "on",
            graph_info={"graphVersion": "v", "inputStableHashes": {"atcis": "wrong"}},
        )


async def test_future_event_payload_is_rejected_even_if_tool_arguments_are_pinned():
    class FutureSource(Source):
        async def list_tools(self):
            return [
                {
                    "name": "list_events",
                    "description": "Bounded events",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "epochId": {"type": "string"},
                            "throughSequence": {"type": "integer"},
                        },
                        "required": ["epochId", "throughSequence"],
                    },
                }
            ]

        async def call(self, name, arguments):
            return {"items": [{"epochId": "atcis-epoch-1", "sequence": 2}]}

    runner = MultiToolRunner({"atcis": FutureSource("atcis")}, snapshots(), "off")
    with pytest.raises(ValueError, match="future_event"):
        await runner.execute("atcis__list_events", {})
