import asyncio
import json
from contextlib import AsyncExitStack
from functools import partial

import httpx
from httpx_sse import aconnect_sse

from platform_api.agent.loop import AgentLoop
from platform_api.agent.tools import ToolRunner
from platform_api.mcp.client import MCPClient


class LazyMCP:
    def __init__(self, runtime, stack):
        self.runtime, self.stack = runtime, stack
        self.session: MCPClient | None = None

    async def call(self, name, args):
        return await self._request("call", name, args)

    async def list_tools(self):
        return await self._request("list_tools")

    async def _request(self, method, *args):
        try:
            if self.session is None:
                self.session = await self.stack.enter_async_context(
                    MCPClient(self.runtime.mcp_url, self.runtime.mcp_token)
                )
            result = await getattr(self.session, method)(*args)
            self.runtime.mcp_connected, self.runtime.mcp_error = True, None
            return result
        except asyncio.CancelledError:
            self.runtime.mcp_connected = False
            self.runtime.mcp_error = "MCP request timed out or cancelled"
            raise
        except Exception as exc:
            self.runtime.mcp_connected = False
            self.runtime.mcp_error = str(exc)[:500]
            raise


class Runtime:
    def __init__(self, repo, provider, c4i_url, mcp_url, c4i_token="", mcp_token=""):
        self.repo, self.provider = repo, provider
        self.c4i_url, self.mcp_url = c4i_url, mcp_url
        self.c4i_token, self.mcp_token = c4i_token, mcp_token
        self.source_connected = False
        self.mcp_connected = False
        self.source_error = None
        self.mcp_error = None

    async def ingest_loop(self):
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.c4i_token}"} if self.c4i_token else {},
            timeout=httpx.Timeout(10, read=30),
        ) as http:
            while True:
                try:
                    snapshot = await self.repo.situation()
                    if (
                        snapshot.get("snapshotId")
                        and snapshot.get("scenarioId")
                        and not snapshot.get("scenario")
                    ):
                        # Enrich this exact historical cursor, never skip pending source events.
                        response = await http.get(
                            self.c4i_url + "/api/v1/snapshots/" + snapshot["snapshotId"]
                        )
                        if response.status_code == 404:
                            response = await http.get(self.c4i_url + "/api/v1/snapshot")
                            response.raise_for_status()
                            snapshot = response.json()
                            await self.repo.bootstrap(snapshot, gap=True)
                        else:
                            response.raise_for_status()
                            snapshot = response.json()
                            await self.repo.bootstrap(snapshot)
                    if not snapshot.get("snapshotId"):
                        response = await http.get(self.c4i_url + "/api/v1/snapshot")
                        response.raise_for_status()
                        snapshot = response.json()
                        await self.repo.bootstrap(snapshot)
                    async with aconnect_sse(
                        http,
                        "GET",
                        self.c4i_url + "/api/v1/stream",
                        params={"epochId": snapshot["epochId"], "after": snapshot["sequence"]},
                    ) as source:
                        if source.response.status_code == 409:
                            response = await http.get(self.c4i_url + "/api/v1/snapshot")
                            response.raise_for_status()
                            await self.repo.bootstrap(response.json(), gap=True)
                            continue
                        source.response.raise_for_status()
                        self.source_connected, self.source_error = True, None
                        async for event in source.aiter_sse():
                            if event.data:
                                await self.repo.ingest(json.loads(event.data))
                except Exception as exc:  # noqa: BLE001 - reconnect boundary records failures
                    self.source_connected = False
                    self.source_error = str(exc)[:500]
                    await asyncio.sleep(1)

    async def worker(self):
        while True:
            run = await self.repo.next_run()
            if not run:
                await asyncio.sleep(0.1)
                continue
            rid = run["runId"]
            await self.repo.update_run(rid, {"status": "running"})
            try:
                async with AsyncExitStack() as stack:
                    event = run["sourceEvent"]
                    snapshot = None
                    if event:
                        snapshot = {
                            "snapshotId": event["snapshotId"],
                            "epochId": event["epochId"],
                            "sequence": event["sequence"],
                            "sourceTime": event.get("occurredAt"),
                        }
                    runner = ToolRunner(LazyMCP(self, stack), snapshot)
                    loop = AgentLoop(
                        self.provider, runner, on_progress=partial(self.repo.update_run, rid)
                    )
                    history = (
                        await self.repo.history(run["conversationId"], rid)
                        if run["conversationId"]
                        else []
                    )
                    result = await loop.run(run["question"], history)
                    await self.repo.update_run(rid, result)
            except Exception as exc:  # noqa: BLE001 - persist a failed queued run
                self.mcp_connected = False
                self.mcp_error = str(exc)[:500]
                await self.repo.update_run(rid, {"status": "failed", "error": str(exc)[:1000]})
