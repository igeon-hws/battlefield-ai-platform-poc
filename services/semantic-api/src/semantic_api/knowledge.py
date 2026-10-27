"""Knowledge reads are available independently of Neo4j and graph preparation."""

from fastapi import Depends, Query
from semantic_core.knowledge import KnowledgeCatalog


def install_knowledge(app, read):
    catalog = KnowledgeCatalog()
    app.state.knowledge = catalog

    @app.get("/v1/knowledge/sets", dependencies=[Depends(read)])
    async def sets():
        versions = {catalog.version}
        from pathlib import Path

        import semantic_core.knowledge as module

        versions.update(
            p.stem for p in Path(module.__file__).with_name("knowledge_sets").glob("*.json")
        )
        return {
            "items": [
                KnowledgeCatalog(v).manifest()
                for v in sorted(versions, key=lambda v: v != catalog.version)
            ]
        }

    @app.get("/v1/knowledge/sets/{version}", dependencies=[Depends(read)])
    async def manifest(version: str):
        return KnowledgeCatalog(version).manifest()

    @app.get("/v1/knowledge/documents", dependencies=[Depends(read)])
    async def documents(
        knowledgeSetVersion: str, cursor: str = "", limit: int = Query(20, ge=1, le=50)
    ):
        return KnowledgeCatalog(knowledgeSetVersion).page(
            knowledgeSetVersion, cursor=cursor, limit=limit
        )

    @app.get("/v1/knowledge/search", dependencies=[Depends(read)])
    async def search(
        knowledgeSetVersion: str,
        q: str = Query("", max_length=500),
        cursor: str = "",
        limit: int = Query(20, ge=1, le=50),
    ):
        return KnowledgeCatalog(knowledgeSetVersion).page(
            knowledgeSetVersion, q=q, cursor=cursor, limit=limit
        )

    @app.get("/v1/knowledge/documents/{documentKey}", dependencies=[Depends(read)])
    async def document(documentKey: str, knowledgeSetVersion: str):
        return KnowledgeCatalog(knowledgeSetVersion).document(knowledgeSetVersion, documentKey)
