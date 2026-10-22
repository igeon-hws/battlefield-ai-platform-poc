import asyncio
import json
import os

import httpx
from battlefield_ontology import (
    MAPPING_VERSION,
    ONTOLOGY_VERSION,
    RESOLUTION_VERSION,
    digest,
    stable_hash,
)


class GraphBuilder:
    def __init__(self, repository, sources):
        self.repository, self.sources = repository, sources
        # Distinct source endpoints must not consume each other's restart checkpoints/jobs.
        self.scope = digest({s: c["url"].rstrip("/") for s, c in sources.items()})
        self.cursors: dict[str, dict] = {}
        self.wake = asyncio.Event()
        self.lock = asyncio.Lock()
        self.last_error = None
        self.last_version = None

    async def get(self, system, path, params=None):
        source = self.sources[system]
        async with httpx.AsyncClient(
            base_url=source["url"],
            headers={"Authorization": f"Bearer {source['token']}"} if source.get("token") else {},
            timeout=10,
        ) as client:
            response = await client.get("/api/v1" + path, params=params)
            response.raise_for_status()
            return response.json()

    async def snapshot_set(self):
        async def snapshot(system):
            raw = await self.get(system, "/snapshot")
            return system, {
                k: raw[k]
                for k in (
                    "datasetId",
                    "epochId",
                    "snapshotId",
                    "sequence",
                    "sourceTime",
                    "stableDataHash",
                )
            }

        return dict(await asyncio.gather(*(snapshot(s) for s in self.sources)))

    async def ensure_build(self, snapshots):
        """Read immutable public exports, validate their pins, then publish/reuse a build."""
        async with self.lock:
            exports = {}
            for system, ref in snapshots.items():
                if system not in self.sources:
                    raise ValueError("untrusted source")
                data = await self.get(system, "/stable-export", {"snapshotId": ref["snapshotId"]})
                for key in ("datasetId", "epochId", "snapshotId", "sequence"):
                    if data[key] != ref[key]:
                        raise ValueError("source snapshot mismatch")
                if (
                    data["stableDataHash"] != stable_hash(data)
                    or ref.get("stableDataHash", data["stableDataHash"]) != data["stableDataHash"]
                ):
                    raise ValueError("stable data hash mismatch")
                exports[system] = data
            if set(exports) != {"atcis", "knccs"}:
                raise ValueError("incomplete source coverage")
            if os.getenv("BUILDER_GRAPH_PREFIX"):
                prefix = os.environ["BUILDER_GRAPH_PREFIX"]
                if prefix != "test-":
                    raise ValueError("only test graph prefix supported")
                from battlefield_ontology.domain import catalog_hash

                version = (
                    prefix
                    + digest(
                        {
                            "hashes": {s: d["stableDataHash"] for s, d in exports.items()},
                            "catalog": catalog_hash(),
                        }
                    )[:32]
                )
                info = await asyncio.to_thread(
                    self.repository.build, exports, graph_version=version
                )
            else:
                info = await asyncio.to_thread(self.repository.build, exports)
            self.last_version, self.last_error = info["graphVersion"], None
            return info

    async def sync_once(self):
        snapshots = await self.snapshot_set()
        # Reconcile immutable public snapshots after stream gaps/reset; do not infer edges
        # from partial event payloads. Same stable input makes build a no-op.
        info = await self.ensure_build(snapshots)
        self.cursors = {
            s: {"epochId": r["epochId"], "sequence": r["sequence"]} for s, r in snapshots.items()
        }
        await asyncio.to_thread(
            self.repository.query,
            "MERGE (s:GraphState {id:$id}) SET s.bodyJson=$body",
            id="source-checkpoints-" + self.scope,
            body=json.dumps(self.cursors),
        )
        return info

    async def watch(self, system):
        while True:
            try:
                source = self.sources[system]
                cursor = self.cursors.get(system, {})
                headers = (
                    {"Authorization": f"Bearer {source['token']}"} if source.get("token") else {}
                )
                async with (
                    httpx.AsyncClient(
                        timeout=httpx.Timeout(20, read=None), headers=headers
                    ) as client,
                    client.stream(
                        "GET",
                        source["url"] + "/api/v1/stream",
                        params={"after": cursor.get("sequence", 0)},
                    ) as response,
                ):
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            event = json.loads(line[6:])
                            if event["type"] in (
                                "structure.changed",
                                "scenario.reset",
                                "report.received",
                                "message.received",
                            ):
                                self.wake.set()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect boundary records adapter failures
                self.last_error = f"{system} stream: {type(exc).__name__}"
                await asyncio.sleep(1)

    async def submit(self, snapshots, versions):
        expected = {
            "ontologyVersion": ONTOLOGY_VERSION,
            "mappingVersion": MAPPING_VERSION,
            "resolutionRuleVersion": RESOLUTION_VERSION,
        }
        if os.getenv("C4I_CONTRACT_VERSION") == "3":
            expected = {k: "3.0.0" for k in expected}
        if versions != expected:
            raise ValueError("unsupported rule versions")
        request_id = (
            "build-request-"
            + digest(
                {
                    "scope": self.scope,
                    "snapshots": snapshots,
                    "versions": versions,
                    "domainCatalog": self.domain_catalog(),
                }
            )[:32]
        )
        await asyncio.to_thread(
            self.repository.query,
            "MERGE (r:BuildRequest {requestId:$id}) ON CREATE SET r.status='QUEUED',r.bodyJson=$body,r.sourceScope=$scope",
            id=request_id,
            scope=self.scope,
            body=json.dumps(snapshots),
        )
        self.wake.set()
        return await self.request_info(request_id)

    @staticmethod
    def domain_catalog():
        if os.getenv("C4I_CONTRACT_VERSION") == "3":
            from battlefield_ontology.domain import catalog_hash

            return catalog_hash()
        return None

    async def request_info(self, request_id):
        rows = await asyncio.to_thread(
            self.repository.query,
            "MATCH (r:BuildRequest {requestId:$id,sourceScope:$scope}) RETURN properties(r) AS r",
            id=request_id,
            scope=self.scope,
        )
        if not rows:
            raise KeyError(request_id)
        return {k: v for k, v in rows[0]["r"].items() if k != "bodyJson"}

    async def run(self):
        await asyncio.to_thread(
            self.repository.query,
            "MATCH (r:BuildRequest {status:'RUNNING',sourceScope:$scope}) SET r.status='QUEUED'",
            scope=self.scope,
        )
        while True:
            self.wake.clear()
            rows = await asyncio.to_thread(
                self.repository.query,
                "MATCH (r:BuildRequest {status:'QUEUED',sourceScope:$scope}) RETURN r.requestId AS id,r.bodyJson AS body ORDER BY r.requestId LIMIT 1",
                scope=self.scope,
            )
            if rows:
                request = rows[0]
                await asyncio.to_thread(
                    self.repository.query,
                    "MATCH (r:BuildRequest {requestId:$id}) SET r.status='RUNNING'",
                    id=request["id"],
                )
                try:
                    info = await self.ensure_build(json.loads(request["body"]))
                    await asyncio.to_thread(
                        self.repository.query,
                        "MATCH (r:BuildRequest {requestId:$id}) SET r.status='READY',r.graphVersion=$v",
                        id=request["id"],
                        v=info["graphVersion"],
                    )
                except Exception as exc:  # noqa: BLE001 - persist failed managed build
                    await asyncio.to_thread(
                        self.repository.query,
                        "MATCH (r:BuildRequest {requestId:$id}) SET r.status='FAILED',r.error=$e",
                        id=request["id"],
                        e=str(exc),
                    )
                continue
            try:
                await self.sync_once()
            except Exception as exc:  # noqa: BLE001 - reconciliation records source errors
                self.last_error = f"sync: {type(exc).__name__}: {exc}"
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=2)
            except TimeoutError:
                pass

    async def run_forever(self):
        while True:
            try:
                await self.run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - restart the single background writer
                self.last_error = f"builder: {type(exc).__name__}: {exc}"
                await asyncio.sleep(1)
