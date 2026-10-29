import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from conftest import server
from dotenv import load_dotenv
from graph_builder.worker import GraphBuilder
from semantic_core.graph import GraphRepository

pytestmark = pytest.mark.neo4j


async def test_builder_queues_and_restart_recovery_are_scoped_to_source_endpoints():
    from battlefield_ontology import MAPPING_VERSION, ONTOLOGY_VERSION, RESOLUTION_VERSION

    load_dotenv()
    repo = GraphRepository(
        os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687"), "neo4j", os.environ["NEO4J_PASSWORD"]
    )
    suffix = uuid4().hex
    a = GraphBuilder(repo, {"atcis": {"url": "http://a-" + suffix}})
    b = GraphBuilder(repo, {"atcis": {"url": "http://b-" + suffix}})
    versions = {
        "ontologyVersion": ONTOLOGY_VERSION,
        "mappingVersion": MAPPING_VERSION,
        "resolutionRuleVersion": RESOLUTION_VERSION,
    }
    snapshots = {"test": {"snapshotId": suffix}}
    ids = []
    task = None
    try:
        first = await a.submit(snapshots, versions)
        ids.append(first["requestId"])
        second = await b.submit(snapshots, versions)
        ids.append(second["requestId"])
        assert first["requestId"] != second["requestId"]
        with pytest.raises(KeyError):
            await b.request_info(first["requestId"])
        queued = await a.submit({"test": {"snapshotId": suffix + "-queued"}}, versions)
        ids.append(queued["requestId"])
        repo.query(
            "MATCH (r:BuildRequest {requestId:$id}) SET r.status='RUNNING'", id=first["requestId"]
        )
        repo.query(
            "MATCH (r:BuildRequest {requestId:$id}) SET r.status='RUNNING'", id=second["requestId"]
        )
        processed = asyncio.Event()

        async def build(refs, knowledge_version=None):
            assert refs == snapshots
            return {"graphVersion": "test-" + suffix}

        async def idle():
            processed.set()
            await asyncio.Event().wait()

        b.ensure_build = build
        b.sync_once = idle
        task = asyncio.create_task(b.run())
        await asyncio.wait_for(processed.wait(), timeout=5)
        assert (await a.request_info(first["requestId"]))["status"] == "RUNNING"
        assert (await a.request_info(queued["requestId"]))["status"] == "QUEUED"
        assert (await b.request_info(second["requestId"]))["status"] == "READY"
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        repo.query("MATCH (r:BuildRequest) WHERE r.requestId IN $ids DELETE r", ids=ids)
        repo.close()


async def test_builder_reads_public_snapshots_ignores_ticks_and_recovers_reset(tmp_path):
    load_dotenv()
    repo = GraphRepository(
        os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687"), "neo4j", os.environ["NEO4J_PASSWORD"]
    )
    repo.ensure_schema()
    with (
        server(
            "import uvicorn; from mock_atcis.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
            {"ATCIS_DB": str(tmp_path / "a.db"), "ATCIS_READ_TOKEN": "", "ATCIS_CONTROL_TOKEN": ""},
        ) as a,
        server(
            "import uvicorn; from mock_knccs.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
            {"KNCCS_DB": str(tmp_path / "k.db"), "KNCCS_READ_TOKEN": "", "KNCCS_CONTROL_TOKEN": ""},
        ) as k,
    ):
        worker = GraphBuilder(
            repo, {"atcis": {"url": a, "token": ""}, "knccs": {"url": k, "token": ""}}
        )
        versions = set()
        try:
            first = await worker.sync_once()
            versions.add(first["graphVersion"])
            assert first["status"] == "READY"
            async with httpx.AsyncClient() as client:
                await client.patch(a + "/api/v1/equipment/T-A01", json={"readyCode": "N"})
                assert (await worker.sync_once())["graphVersion"] == first["graphVersion"]
                await client.patch(a + "/api/v1/equipment/T-A01", json={"ownerUnitCode": "D2"})
                changed = await worker.sync_once()
                versions.add(changed["graphVersion"])
                assert changed["graphVersion"] != first["graphVersion"]
                assert (
                    len(repo.equipment_refs(first["graphVersion"], ["atcis:B11"], "tank")["items"])
                    == 2
                )
                assert (
                    len(
                        repo.equipment_refs(changed["graphVersion"], ["atcis:B11"], "tank")["items"]
                    )
                    == 1
                )
                await client.post(k + "/api/v1/scenario/reset")
                reset = await worker.sync_once()
                versions.add(reset["graphVersion"])
                assert reset["graphVersion"] != changed["graphVersion"]
                assert (
                    worker.cursors["knccs"]["epochId"]
                    != changed["inputSnapshotSet"]["knccs"]["epochId"]
                )
                assert (await worker.ensure_build(first["inputSnapshotSet"]))[
                    "graphVersion"
                ] == first["graphVersion"]
        finally:
            # This test uses a dedicated Neo4j container; only its own versions are removed.
            for version in versions:
                repo.query("MATCH (n:SemanticNode {graphVersion:$v}) DETACH DELETE n", v=version)
                repo.query("MATCH (b:GraphBuild {graphVersion:$v}) DELETE b", v=version)
            repo.close()


async def test_internal_build_requests_require_auth_and_are_idempotent(tmp_path):
    load_dotenv()
    uri = os.getenv("NEO4J_TEST_URI", "bolt://127.0.0.1:17687")
    with (
        server(
            "import uvicorn; from mock_atcis.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
            {"ATCIS_DB": str(tmp_path / "a.db"), "ATCIS_READ_TOKEN": ""},
        ) as a,
        server(
            "import uvicorn; from mock_knccs.app import create_app; uvicorn.run(create_app(tick_enabled=False),host='127.0.0.1',port=PORT,log_level='error')",
            {"KNCCS_DB": str(tmp_path / "k.db"), "KNCCS_READ_TOKEN": ""},
        ) as k,
        server(
            "import uvicorn; from graph_builder.app import create_app; uvicorn.run(create_app(),host='127.0.0.1',port=PORT,log_level='error')",
            {
                "NEO4J_URI": uri,
                "ATCIS_BASE_URL": a,
                "KNCCS_BASE_URL": k,
                "BUILDER_ADMIN_TOKEN": "admin",
                "ATCIS_READ_TOKEN": "",
                "KNCCS_READ_TOKEN": "",
            },
        ) as builder,
    ):
        async with httpx.AsyncClient() as client:
            snapshots = {}
            for system, url in (("atcis", a), ("knccs", k)):
                snap = (await client.get(url + "/api/v1/snapshot")).json()
                snapshots[system] = {
                    key: snap[key]
                    for key in (
                        "datasetId",
                        "epochId",
                        "snapshotId",
                        "sequence",
                        "sourceTime",
                        "stableDataHash",
                    )
                }
            body = {"snapshots": snapshots}
            assert (
                await client.post(builder + "/internal/build-requests", json=body)
            ).status_code == 401
            headers = {"Authorization": "Bearer admin"}
            response = await client.post(
                builder + "/internal/build-requests", json=body, headers=headers
            )
            assert response.status_code == 202
            request_id = response.json()["requestId"]
            assert (
                await client.post(builder + "/internal/build-requests", json=body, headers=headers)
            ).json()["requestId"] == request_id
            for _ in range(100):
                result = (
                    await client.get(
                        builder + "/internal/build-requests/" + request_id, headers=headers
                    )
                ).json()
                if result["status"] in ("READY", "FAILED"):
                    break
                await asyncio.sleep(0.1)
            assert result["status"] == "READY", result
            assert (
                await client.post(
                    builder + "/internal/build-requests",
                    json={**body, "ontologyVersion": "unsupported"},
                    headers=headers,
                )
            ).status_code == 422
