"""Reviewed display metadata is a representation of the B/C shared document."""

import json

from semantic_core.knowledge import KnowledgeCatalog


class MetadataCatalog:
    def __init__(self, version):
        self.knowledge = KnowledgeCatalog(version)
        self.document = self.knowledge.document(version, "fabric:DISPLAY-01")
        self.payload = json.loads(self.document["document"]["text"])
        if self.payload["schemaVersion"] != "display-1" or self.payload["locale"] != "ko-KR":
            raise ValueError("unsupported display metadata")
        if self.payload.get("reviewRevision") not in ("review-display-1", "review-display-2"):
            raise ValueError("unsupported metadata review revision")

    def field(self, system, resource, key):
        return next(
            (
                f
                for f in self.payload["fields"]
                if (f["systemId"], f["recordType"], f["field"]) == (system, resource, key)
            ),
            None,
        )

    def value(self, system, resource, key, value):
        definition = self.field(system, resource, key)
        if value is None:
            return "정보 없음"
        code = str(value).lower() if isinstance(value, bool) else str(value)
        return (
            definition["values"].get(code, "미확인")
            if definition and definition["values"]
            else str(value)
        )

    def public(self):
        return {
            **self.payload,
            "knowledgeSetVersion": self.knowledge.version,
            "knowledgeSetHash": self.knowledge.hash,
            "metadataVersion": self.document["document"]["hash"],
            "documentRef": {k: self.document[k] for k in ("documentKey", "knowledgeSetVersion")},
            "available": True,
        }
