"""Reuse the single Agent loop/repository with Fabric-owned capture and display."""

import asyncio
import json

import httpx
from httpx_sse import aconnect_sse

from platform_api.agent.domain_tools import DomainToolRunner
from platform_api.multi_runtime import MultiRuntime


class DomainRuntime(MultiRuntime):
    def __init__(self, *args):
        super().__init__(*args)
        self.runner_class = DomainToolRunner
        self.baseline_snapshots = {}

    def headers(self):
        return (
            {"Authorization": "Bearer " + self.semantic["token"]}
            if self.semantic.get("token")
            else {}
        )

    async def fabric_request(self, method, path, **kwargs):
        async with httpx.AsyncClient(
            base_url=self.semantic["url"], headers=self.headers(), timeout=45
        ) as client:
            r = await client.request(method, path, **kwargs)
            r.raise_for_status()
            return r.json()

    async def capture(self, *, strict=False, overrides=None):
        """Prepare through Fabric; display projection is never injected as Agent evidence."""
        context = await self.fabric_request(
            "POST",
            "/v1/analysis-contexts",
            json={"semanticMode": "off", "allowPartial": not strict},
        )
        pins = context["sourceSnapshotSet"]
        if overrides:
            pins.update(overrides)
            context = await self.fabric_request(
                "POST",
                "/v1/analysis-contexts",
                json={"semanticMode": "off", "sourceSnapshotSet": pins, "allowPartial": not strict},
            )
        self.last_capture = {
            k: context[k]
            for k in (
                "capturedAt",
                "preparationSeconds",
                "captureSpanSeconds",
                "sourceRunning",
                "documents",
                "baselineSourceSnapshotSet",
            )
        }
        self.baseline_snapshots = context["baselineSourceSnapshotSet"]
        if strict and (
            set(pins) != set(self.sources)
            or any(context["sourceRunning"].values())
            and context["captureSpanSeconds"] > 2
        ):
            raise ValueError("incomplete or inconsistent Fabric capture")
        return context["sourceSnapshotSet"]

    async def ensure_graph(self, snapshots):
        context = await self.fabric_request(
            "POST",
            "/v1/analysis-contexts",
            json={"semanticMode": "on", "sourceSnapshotSet": snapshots},
        )
        return context["graphInfo"]

    async def prepare_run_context(self, snapshots):
        # Resolve T0 for these exact pins, not the last capture of another queued run.
        context = await self.fabric_request(
            "POST",
            "/v1/analysis-contexts",
            json={
                "semanticMode": "off",
                "sourceSnapshotSet": snapshots,
                "allowPartial": len(snapshots) < 2,
            },
        )
        return context["baselineSourceSnapshotSet"]

    async def ingest(self, system):
        while True:
            try:
                current = await self.fabric_request("GET", "/v1/source-projections/" + system)
                await self.repo.save_source(system, current)
                async with (
                    httpx.AsyncClient(
                        headers=self.headers(), timeout=httpx.Timeout(10, read=30)
                    ) as http,
                    aconnect_sse(
                        http,
                        "GET",
                        self.semantic["url"] + "/v1/events",
                        params={
                            "systemId": system,
                            "epochId": current["epochId"],
                            "after": current["sequence"],
                        },
                    ) as stream,
                ):
                    stream.response.raise_for_status()
                    self.source_status[system].update(connected=True, error=None)
                    async for message in stream.aiter_sse():
                        if message.event == "reset":
                            break
                        event = json.loads(message.data)
                        projection = await self.fabric_request(
                            "GET",
                            "/v1/source-projections/" + system,
                            params={"snapshotId": event["snapshotId"]},
                        )
                        pins = (
                            await self.capture(
                                overrides={
                                    system: {
                                        k: projection[k]
                                        for k in (
                                            "datasetId",
                                            "epochId",
                                            "snapshotId",
                                            "sequence",
                                            "sourceTime",
                                            "stableDataHash",
                                        )
                                    }
                                }
                            )
                            if event["type"]
                            in (
                                "equipment.changed",
                                "structure.changed",
                                "activity.changed",
                                "report.received",
                                "message.received",
                            )
                            else None
                        )
                        await self.repo.save_source(system, projection, event, pins)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect without changing analysis policy
                self.source_status[system].update(
                    connected=False, error=type(exc).__name__ + ": Fabric unavailable"
                )
                await asyncio.sleep(1)
