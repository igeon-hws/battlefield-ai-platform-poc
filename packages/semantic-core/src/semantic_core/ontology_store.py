"""Fabric ontology drafts, review and immutable publication (v6 demo capability)."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from battlefield_ontology.declaration import (
    DOCUMENT_KEY,
    apply_edits,
    declaration_version,
    diff,
    from_documents,
    impact,
    knowledge_item,
)

from semantic_core.knowledge import KnowledgeCatalog, hash_value, store_root


class OntologyStore:
    def __init__(self):
        self.root = store_root()

    def current(self):
        catalog = KnowledgeCatalog()
        declaration = from_documents(catalog.documents)
        if declaration is None:
            raise ValueError("current knowledge set has no ontology declaration")
        return catalog, declaration

    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        temp.replace(path)

    def create_draft(self, edits, author):
        if not author:
            raise ValueError("author required")
        catalog, declaration = self.current()
        changed = apply_edits(declaration, edits)
        draft = {
            "draftId": uuid4().hex,
            "status": "validated",
            "author": author,
            "createdAt": datetime.now(UTC).isoformat(),
            "baseKnowledgeSetVersion": catalog.version,
            "baseDeclarationVersion": declaration_version(declaration),
            "declarationVersion": declaration_version(changed),
            "edits": edits,
            "diff": diff(declaration, changed),
            "impact": impact(declaration, changed),
            "declaration": changed,
        }
        if not draft["diff"]:
            raise ValueError("draft does not change the declaration")
        self._write(self.root / "drafts" / (draft["draftId"] + ".json"), draft)
        return draft

    def draft(self, draft_id):
        path = self.root / "drafts" / (draft_id + ".json")
        if not draft_id.isalnum() or not path.exists():
            raise KeyError(draft_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def approve(self, draft_id, approver):
        draft = self.draft(draft_id)
        if draft["status"] != "validated":
            raise ValueError("draft is not awaiting approval")
        if not approver or approver == draft["author"]:
            raise ValueError("approver must differ from author")
        catalog, _ = self.current()
        if catalog.version != draft["baseKnowledgeSetVersion"]:
            raise ValueError("stale draft: current knowledge set changed")
        documents = [
            knowledge_item(draft["declaration"]) if d["documentKey"] == DOCUMENT_KEY else d
            for d in catalog.documents
        ]
        version = "knowledge-" + hash_value(documents)[:24]
        self._write(self.root / "sets" / (version + ".json"), documents)
        # The new set must load through the same verified catalog path before it becomes current.
        KnowledgeCatalog(version)
        entry = {
            "knowledgeSetVersion": version,
            "previousKnowledgeSetVersion": catalog.version,
            "declarationVersion": draft["declarationVersion"],
            "draftId": draft_id,
            "author": draft["author"],
            "approver": approver,
            "publishedAt": datetime.now(UTC).isoformat(),
            "diff": draft["diff"],
            "impact": draft["impact"],
        }
        history = self.history()
        self._write(self.root / "history.json", [*history, entry])
        self._write(self.root / "current.json", {"knowledgeSetVersion": version})
        self._write(
            self.root / "drafts" / (draft_id + ".json"),
            {**draft, "status": "published", "approver": approver, **entry},
        )
        return entry

    def history(self):
        path = self.root / "history.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
