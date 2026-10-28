"""Explicit demo capabilities, independent from external user authentication."""

import secrets
import time
from typing import TypedDict
from urllib.parse import quote

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

MODES = {"native", "documents", "structured", "compare"}


class DemoSession(TypedDict):
    mode: str
    expires: float


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str


def install_demo(app, repo, runtime):
    sessions: dict[str, DemoSession] = {}

    @app.post("/api/v1/demo-sessions")
    async def create(body: SessionInput):
        if body.mode not in MODES:
            raise HTTPException(422, "unknown demo mode")
        now = time.monotonic()
        for token, entry in list(sessions.items()):
            if entry["expires"] < now:
                del sessions[token]
        if len(sessions) >= 1000:
            raise HTTPException(429, "too many demo sessions")
        token = secrets.token_urlsafe(32)
        sessions[token] = {"mode": body.mode, "expires": now + 8 * 3600}
        return {
            "sessionId": token,
            "mode": body.mode,
            "policyVersion": "5-logistics-abc",
            "datasetId": "c2-logistics-demo-v5",
        }

    @app.middleware("http")
    async def capabilities(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1/") or path in ("/api/v1/config", "/api/v1/demo-sessions"):
            return await call_next(request)
        context = sessions.get(request.headers.get("x-demo-session", ""))
        if not context or context["expires"] < time.monotonic():
            return JSONResponse({"detail": "demo context required"}, status_code=401)
        mode = context["mode"]
        request.state.demo_mode = mode
        if (
            path == "/api/v1/events"
            or path == "/api/v1/semantic/status"
            and mode not in ("structured", "compare")
        ):
            return JSONResponse({"detail": "endpoint unavailable in this context"}, status_code=403)
        if "/comparisons" in path and mode != "compare":
            return JSONResponse({"detail": "comparison page required"}, status_code=403)
        if path.startswith("/api/v1/objects") and mode != "structured":
            return JSONResponse({"detail": "structured page required"}, status_code=403)
        if path.startswith("/api/v1/knowledge") and mode not in ("documents", "structured"):
            return JSONResponse({"detail": "knowledge forbidden"}, status_code=403)
        try:
            if path.startswith("/api/v1/analyses/"):
                run = await repo.get_run(path.split("/")[4])
                if (
                    mode == "compare"
                    and not run.get("comparisonId")
                    or mode != "compare"
                    and (run.get("knowledgeMode") != mode or run.get("comparisonId"))
                ):
                    return JSONResponse({"detail": "run context mismatch"}, status_code=403)
            if path.startswith("/api/v1/conversations/"):
                conversation = await repo.conversation(path.split("/")[4])
                if mode == "compare" or any(
                    r.get("knowledgeMode") != mode or r.get("comparisonId") for r in conversation
                ):
                    return JSONResponse(
                        {"detail": "conversation context mismatch"}, status_code=403
                    )
            if path == "/api/v1/analyses" and request.method == "POST":
                body = await request.json()
                if mode == "compare" or body.get("knowledgeMode") != mode:
                    return JSONResponse({"detail": "mode context mismatch"}, status_code=403)
                if body.get("conversationId"):
                    conversation = await repo.conversation(body["conversationId"])
                    if not conversation or any(
                        r.get("knowledgeMode") != mode or r.get("comparisonId")
                        for r in conversation
                    ):
                        return JSONResponse(
                            {"detail": "conversation context mismatch"}, status_code=403
                        )
        except KeyError:
            return JSONResponse({"detail": "not found"}, status_code=404)
        return await call_next(request)

    @app.get("/api/v1/native-records/{system}/{resource}")
    async def native_records(
        system: str,
        resource: str,
        snapshotId: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        continuation: str | None = None,
    ):
        # Always the public source API. Never call a semantic helper here.
        from semantic_core.objects import RESOURCE_FIELDS

        resources = {v[0] for v in RESOURCE_FIELDS.values()} | {
            "contacts",
            "tracks",
            "formations",
            "relations",
            "reports",
            "journal",
            "activities",
            "messages",
            "delivery-events",
            "associations",
        }
        if system not in runtime.sources or resource not in resources:
            raise HTTPException(422, "unknown native resource")
        config = runtime.sources[system]
        import httpx

        async with httpx.AsyncClient(
            base_url=config["url"],
            headers={"Authorization": "Bearer " + config["token"]} if config.get("token") else {},
            timeout=10,
        ) as client:
            if not snapshotId:
                r = await client.get("/api/v1/snapshot")
                r.raise_for_status()
                snapshotId = r.json()["snapshotId"]
            else:
                r = await client.get("/api/v1/snapshots/" + quote(snapshotId, safe=""))
                r.raise_for_status()
            source_time = r.json()["sourceTime"]
            params = {"snapshotId": snapshotId, "limit": limit}
            if system == "knccs":
                if continuation:
                    params["continuation"] = continuation
            else:
                params["offset"] = offset
            r = await client.get("/api/v1/" + quote(resource, safe=""), params=params)
            r.raise_for_status()
            from datetime import UTC, datetime

            return {
                "systemId": system,
                "snapshotId": snapshotId,
                "sourceTime": source_time,
                "lastReceivedAt": datetime.now(UTC).isoformat(),
                "page": r.json(),
                "displayOnly": True,
            }

    @app.post("/api/v1/objects/detail")
    async def object_detail(request: Request):
        body = await request.json()
        import httpx

        try:
            return await runtime.fabric_request("POST", "/v1/object-details", json=body)
        except httpx.HTTPStatusError as exc:
            return JSONResponse({"detail": exc.response.text}, status_code=exc.response.status_code)
        except httpx.HTTPError:
            raise HTTPException(503, "Fabric object query unavailable")

    @app.get("/api/v1/knowledge/{path:path}")
    async def knowledge(path: str, request: Request):
        if ".." in path or not path:
            raise HTTPException(422, "invalid knowledge path")
        return await runtime.fabric_request(
            "GET", "/v1/knowledge/" + path, params=dict(request.query_params)
        )
