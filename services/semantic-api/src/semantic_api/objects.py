"""Fabric read-only detail endpoints. The platform scopes access by demo context."""

from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from semantic_core.objects import ObjectService


class ObjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    systemId: str
    recordType: str
    nativeId: str
    graphVersion: str | None = None
    sourceSnapshotSet: dict | None = None


def install_objects(app, read, semantic):
    service = ObjectService(app.state.fabric, semantic)

    @app.post("/v1/object-details", dependencies=[Depends(read)])
    async def detail(body: ObjectRequest):
        return await service.detail(
            body.systemId, body.recordType, body.nativeId, body.graphVersion, body.sourceSnapshotSet
        )
