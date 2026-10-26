"""Authenticated read-only graph explorer routes, independent of builder controls."""

import asyncio

from fastapi import Depends, Query
from semantic_core.explorer import GraphExplorer


def install_explorer(app, read, repo):
    explorer = GraphExplorer(repo)

    @app.get("/v1/graph-builds", dependencies=[Depends(read)])
    async def builds(
        q: str = "",
        dataset: str = "",
        date: str = "",
        cursor: str = "",
        limit: int = Query(20, ge=1, le=50),
    ):
        return await asyncio.to_thread(explorer.builds, q, dataset, date, cursor, limit)

    @app.get("/v1/graph-summary", dependencies=[Depends(read)])
    async def summary(graphVersion: str):
        return await asyncio.to_thread(explorer.summary, graphVersion)

    @app.get("/v1/graph-nodes", dependencies=[Depends(read)])
    async def nodes(
        graphVersion: str,
        q: str = "",
        system: str = "",
        type: str = "",
        cursor: str = "",
        limit: int = Query(30, ge=1, le=100),
    ):
        return await asyncio.to_thread(explorer.nodes, graphVersion, q, system, type, cursor, limit)

    @app.get("/v1/graph-node", dependencies=[Depends(read)])
    async def node(graphVersion: str, nodeKey: str):
        return await asyncio.to_thread(explorer.node, graphVersion, nodeKey)

    @app.get("/v1/graph-neighborhood", dependencies=[Depends(read)])
    async def neighborhood(
        graphVersion: str,
        subject: str,
        relationTypes: str = "SUBORDINATE_TO,ASSIGNED_TO,REFERS_TO,DERIVED_FROM,SUPERSEDES",
        depth: int = Query(1, ge=0, le=2),
        nodeLimit: int = Query(100, ge=1, le=200),
        edgeLimit: int = Query(150, ge=1, le=300),
    ):
        return await asyncio.to_thread(
            explorer.neighborhood, graphVersion, subject, relationTypes, depth, nodeLimit, edgeLimit
        )
