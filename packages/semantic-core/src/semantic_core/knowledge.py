"""Immutable Fabric-owned reviewed knowledge. No Graph dependency or inferred mappings."""

import base64
import hashlib
import json
import os
import re
from pathlib import Path


def hash_value(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def store_root():
    """Fabric-published v6 knowledge sets; packaged archives stay read-only."""
    return Path(os.getenv("FABRIC_KNOWLEDGE_STORE", "var/fabric-knowledge"))


def current_path():
    from battlefield_ontology.declaration import profile6

    if profile6():
        pointer = store_root() / "current.json"
        if pointer.exists():
            version = json.loads(pointer.read_text(encoding="utf-8"))["knowledgeSetVersion"]
            return store_root() / "sets" / (version + ".json")
        return Path(__file__).with_name("knowledge_documents_v6.json")
    return Path(__file__).with_name(
        "knowledge_documents_v5.json"
        if os.getenv("C4I_CONTRACT_VERSION") == "5"
        else "knowledge_documents.json"
    )


class KnowledgeCatalog:
    def __init__(self, version=None):
        if version is not None and not re.fullmatch(r"knowledge-[0-9a-f]{24}", version):
            raise KeyError("knowledge set not found")
        path = (
            Path(__file__).with_name("knowledge_sets") / (version + ".json")
            if version
            else current_path()
        )
        if version and not path.exists():
            path = store_root() / "sets" / (version + ".json")
        if not path.exists():
            raise KeyError("knowledge set not found")
        self.documents = json.loads(path.read_text(encoding="utf-8"))
        for item in self.documents:
            doc = item["document"]
            if hash_value({k: v for k, v in doc.items() if k != "hash"}) != doc["hash"]:
                raise ValueError("knowledge document hash mismatch")
        self.hash = hash_value(self.documents)
        self.version = "knowledge-" + self.hash[:24]
        if version is not None and version != self.version:
            raise ValueError("knowledge archive hash mismatch")

    def require(self, version):
        if version != self.version:
            raise KeyError("knowledge set not found")

    def manifest(self):
        return {
            "knowledgeSetVersion": self.version,
            "knowledgeSetHash": self.hash,
            "reviewRevision": "review-1",
            "documents": [self.metadata(d) for d in self.documents],
        }

    @staticmethod
    def metadata(item):
        return {k: v for k, v in item.items() if k != "document"} | {
            k: v for k, v in item["document"].items() if k not in ("text", "declaration")
        }

    def page(self, version, q="", cursor="", limit=20):
        self.require(version)
        offset = 0
        if cursor:
            try:
                body = json.loads(base64.urlsafe_b64decode(cursor))
                if (
                    body["version"] != version
                    or body["q"] != q
                    or type(body["offset"]) is not int
                    or body["offset"] < 0
                ):
                    raise ValueError()
                offset = body["offset"]
            except Exception as exc:
                raise ValueError("knowledge cursor mismatch") from exc
        items = sorted(
            [
                d
                for d in self.documents
                if q.casefold() in json.dumps(d, ensure_ascii=False).casefold()
            ],
            key=lambda d: d["documentKey"],
        )
        end = offset + limit
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps({"version": version, "q": q, "offset": end}).encode()
            ).decode()
            if end < len(items)
            else None
        )
        return {
            "knowledgeSetVersion": version,
            "knowledgeSetHash": self.hash,
            "items": [self.metadata(d) for d in items[offset:end]],
            "nextCursor": next_cursor,
            "total": len(items),
            "completeness": "partial" if next_cursor else "complete",
        }

    def document(self, version, key):
        self.require(version)
        item = next((d for d in self.documents if d["documentKey"] == key), None)
        if item is None:
            raise KeyError(key)
        return {
            "knowledgeSetVersion": version,
            "knowledgeSetHash": self.hash,
            **item,
            "completeness": "complete",
        }

    def validate(self, manifest):
        if (
            not isinstance(manifest, dict)
            or manifest != KnowledgeCatalog(manifest.get("knowledgeSetVersion")).manifest()
        ):
            raise ValueError("unreviewed or mismatched knowledge manifest")
