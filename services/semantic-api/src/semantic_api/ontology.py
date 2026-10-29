"""v6 business queries (C read) and Fabric ontology drafts/review/publication (operator UI)."""

import asyncio

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from semantic_core.business_queries import list_business_queries, run_business_query, stamps
from semantic_core.ontology_store import OntologyStore

from semantic_api.fabric import REF_FIELDS


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graphVersion: str
    params: dict[str, str | None] = Field(default_factory=dict)


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edits: dict[str, str]
    author: str = Field(min_length=1, max_length=80)


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approver: str = Field(min_length=1, max_length=80)


def install_ontology(app, read, service):
    fabric = app.state.fabric
    store = OntologyStore()
    warmups: set[asyncio.Task] = set()

    async def pinned(version):
        info, nodes, edges = await asyncio.to_thread(service.model, version)
        pins = {s: {k: r.get(k) for k in REF_FIELDS} for s, r in info["inputSnapshotSet"].items()}
        for system, pin in pins.items():
            pin["stableDataHash"] = info["inputStableHashes"][system]
        snapshots = await fabric.capture(pins)
        return info, nodes, edges, snapshots

    def clean(params):
        return {k: v for k, v in params.items() if v is not None}

    @app.get("/v1/business-queries", dependencies=[Depends(read)])
    async def queries(graphVersion: str):
        info, nodes, _ = await asyncio.to_thread(service.model, graphVersion)
        items = list_business_queries(nodes)
        if not items:
            raise ValueError("graph has no ontology declaration (v6 profile required)")
        return {**stamps(info), "items": items}

    @app.post("/v1/business-queries/{query_id}", dependencies=[Depends(read)])
    async def query(query_id: str, body: QueryRequest):
        info, nodes, edges, snapshots = await pinned(body.graphVersion)
        return run_business_query(info, nodes, edges, snapshots, query_id, clean(body.params))

    async def current_graph():
        from semantic_core.knowledge import KnowledgeCatalog

        snapshots = await fabric.capture()
        info = await fabric.ensure_graph(
            {s: {k: r[k] for k in REF_FIELDS} for s, r in snapshots.items()},
            KnowledgeCatalog().version,
        )
        return await pinned(info["graphVersion"])

    async def preview(declaration, changed, impacted):
        """Run impacted queries' declared examples under current vs draft definitions."""
        info, nodes, edges, snapshots = await current_graph()
        rows = []
        for item in declaration["businessQueries"]:
            if item["queryId"] not in impacted:
                continue
            for params in item.get("examples", []):
                before = run_business_query(
                    info, nodes, edges, snapshots, item["queryId"], params, declaration
                )
                after = run_business_query(
                    info, nodes, edges, snapshots, item["queryId"], params, changed
                )
                rows.append(
                    {
                        "queryId": item["queryId"],
                        "title": item["title"],
                        "params": params,
                        "before": before.get("counts") or before.get("workOrders"),
                        "after": after.get("counts") or after.get("workOrders"),
                    }
                )
        return {"graphVersion": info["graphVersion"], "rows": rows}

    @app.get("/v1/ontology", dependencies=[Depends(read)])
    async def ontology():
        catalog, declaration = await asyncio.to_thread(store.current)
        from battlefield_ontology.declaration import declaration_version, get_path

        return {
            "knowledgeSetVersion": catalog.version,
            "declarationVersion": declaration_version(declaration),
            "declaration": declaration,
            "editable": [
                {**item, "value": get_path(declaration, item["path"])}
                for item in declaration["editable"]
            ],
            "history": await asyncio.to_thread(store.history),
        }

    @app.post("/v1/ontology/drafts", dependencies=[Depends(read)])
    async def create_draft(body: DraftRequest):
        draft = await asyncio.to_thread(store.create_draft, body.edits, body.author)
        _, declaration = await asyncio.to_thread(store.current)
        try:
            draft["preview"] = await preview(
                declaration, draft["declaration"], draft["impact"]["businessQueries"]
            )
        except Exception as exc:  # noqa: BLE001 - preview is advisory; validation already passed
            draft["preview"] = {"error": f"{type(exc).__name__}: {exc}"[:300], "rows": []}
        return draft

    @app.get("/v1/ontology/drafts/{draft_id}", dependencies=[Depends(read)])
    async def get_draft(draft_id: str):
        return await asyncio.to_thread(store.draft, draft_id)

    @app.post("/v1/ontology/drafts/{draft_id}/approve", dependencies=[Depends(read)])
    async def approve(draft_id: str, body: ApproveRequest):
        entry = await asyncio.to_thread(store.approve, draft_id, body.approver)

        async def warm():
            # Pre-build the new version's graph so the next C conversation starts quickly.
            try:
                await current_graph()
            except Exception:  # noqa: BLE001 - C preparation retries and reports on demand
                return

        task = asyncio.create_task(warm())
        warmups.add(task)
        task.add_done_callback(warmups.discard)
        return entry
