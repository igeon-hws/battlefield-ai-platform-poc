"""Render the reviewed v6 ontology declaration into the packaged v6 knowledge set.

Run after editing packages/ontology/.../ontology_v6.json. Published Fabric versions are
written by the Fabric API, not by this script.
"""

import json
from pathlib import Path

from battlefield_ontology.declaration import knowledge_item, load_base
from semantic_core.knowledge import hash_value

ROOT = Path("packages/semantic-core/src/semantic_core")


def main():
    documents = json.loads((ROOT / "knowledge_documents_v5.json").read_text(encoding="utf-8"))
    documents = [*documents, knowledge_item(load_base())]
    text = json.dumps(documents, ensure_ascii=False, indent=1) + "\n"
    (ROOT / "knowledge_documents_v6.json").write_text(text, encoding="utf-8")
    version = "knowledge-" + hash_value(documents)[:24]
    (ROOT / "knowledge_sets" / (version + ".json")).write_text(text, encoding="utf-8")
    print(version)


if __name__ == "__main__":
    main()
