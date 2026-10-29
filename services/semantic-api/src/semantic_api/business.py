"""C-only shared metadata and verified situation projection."""

import asyncio

from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from semantic_core.metadata import MetadataCatalog
from semantic_core.objects import resolve_identity

from semantic_api.fabric import REF_FIELDS, display


class SceneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graphVersion: str | None = None
    sourceSnapshotSet: dict | None = None


def install_business(app, read, service):
    fabric = app.state.fabric

    @app.get("/v1/semantic-metadata", dependencies=[Depends(read)])
    async def metadata(graphVersion: str):
        info = await asyncio.to_thread(service.repo.require_ready, graphVersion)
        stamps = {
            k: info[k]
            for k in (
                "graphVersion",
                "inputStableHashes",
                "ontologyVersion",
                "mappingVersion",
                "resolutionRuleVersion",
            )
        }
        try:
            return {**stamps, **MetadataCatalog(info["knowledgeSetVersion"]).public()}
        except KeyError:
            return {
                **stamps,
                "available": False,
                "fields": [],
                "reason": "해당 지식 버전에 표시 메타데이터가 없습니다.",
            }

    @app.post("/v1/semantic-map", dependencies=[Depends(read)])
    async def scene(body: SceneRequest):
        snapshots = await fabric.capture(body.sourceSnapshotSet, allow_partial=True)
        if not body.graphVersion:
            if set(snapshots) != set(fabric.sources):
                raise ValueError("의미 상황판 준비에는 전체 원천이 필요합니다.")
            from semantic_core.knowledge import KnowledgeCatalog

            info = await fabric.ensure_graph(
                {s: {k: r[k] for k in REF_FIELDS} for s, r in snapshots.items()},
                KnowledgeCatalog().version,
            )
            version = info["graphVersion"]
        else:
            version = body.graphVersion
        info, nodes, edges = await asyncio.to_thread(service.model, version)
        stale = any(
            s not in info["inputSnapshotSet"]
            or r["epochId"] != info["inputSnapshotSet"][s]["epochId"]
            or r["stableDataHash"] != info["inputStableHashes"][s]
            for s, r in snapshots.items()
        )
        observations = []
        groups: dict[str, list[str]] = {}
        for system, raw in snapshots.items():
            for e in display(system, raw)["entities"]:
                native = e["entityId"]
                kind = (
                    "equipment"
                    if system == "atcis"
                    else "contact"
                    if "/" in native
                    else "own-force"
                )
                identity = (
                    resolve_identity(nodes, edges, system, kind, native, raw["sourceTime"])
                    if not stale
                    else {"status": "stale", "canonicalId": None, "evidenceRefs": []}
                )
                item = {
                    **e,
                    "entityId": system + "/" + native,
                    "nativeId": native,
                    "source": system,
                    "identityStatus": identity["status"],
                    "canonicalId": identity["canonicalId"],
                    "identityEvidenceRefs": identity["evidenceRefs"],
                }
                observations.append(item)
                if identity["status"] == "resolved":
                    groups.setdefault(identity["canonicalId"], []).append(item["entityId"])
        return {
            "graphVersion": version,
            "knowledgeSetVersion": info.get("knowledgeSetVersion"),
            "observations": observations,
            "groups": [{"canonicalId": k, "observationIds": v} for k, v in groups.items()],
            "counts": {
                "observations": len(observations),
                "canonicalAssets": len(groups),
                "unresolvedObservations": sum(
                    e["identityStatus"] != "resolved" for e in observations
                ),
            },
            "coverage": {
                s: "complete" if s in snapshots else "unavailable" for s in fabric.sources
            },
            "stale": stale,
            "displayOnly": True,
        }
