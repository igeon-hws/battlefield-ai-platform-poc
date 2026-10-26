"""Explorer authentication and validation without Neo4j or external services."""

import httpx
import pytest
from semantic_api.app import create_app


@pytest.mark.parametrize(
    "path,params",
    [
        ("graph-builds", {}),
        ("graph-summary", {"graphVersion": "missing"}),
        ("graph-nodes", {"graphVersion": "missing"}),
        ("graph-node", {"graphVersion": "missing", "nodeKey": "x"}),
        ("graph-neighborhood", {"graphVersion": "missing", "subject": "x"}),
    ],
)
async def test_explorer_requires_auth_and_reports_graph_outage(monkeypatch, path, params):
    monkeypatch.setenv("C4I_CONTRACT_VERSION", "3")
    monkeypatch.setenv("NEO4J_PASSWORD", "")
    app = create_app(token="read")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get("/v1/" + path, params=params)).status_code == 401
        r = await c.get("/v1/" + path, params=params, headers={"Authorization": "Bearer read"})
        assert r.status_code == 503 and r.json()["error"] == "graph_unavailable"
