"""A/B/C capabilities over the existing single native tool loop."""

from platform_api.agent.domain_tools import DomainToolRunner
from platform_api.mcp.schema import native_definition, normalize_arguments
from semantic_core.knowledge import hash_value

KNOWLEDGE_TOOLS = {
    "list_knowledge_documents",
    "search_knowledge_documents",
    "get_knowledge_document",
}


class KnowledgeToolRunner(DomainToolRunner):
    def __init__(self, clients, snapshots, mode, graph_info=None, knowledge=None):
        if mode not in ("native", "documents", "structured"):
            raise ValueError("explicit knowledgeMode required")
        if mode != "native" and not knowledge:
            raise ValueError("pinned knowledge manifest required")
        if (
            mode == "structured"
            and (graph_info or {}).get("knowledgeSetHash") != knowledge["knowledgeSetHash"]
        ):
            raise ValueError("graph/knowledge mismatch")
        super().__init__(clients, snapshots, "on" if mode == "structured" else "off", graph_info)
        self.knowledge_mode = mode
        self.knowledge = knowledge if mode != "native" else None
        if mode != "native" and "knowledge" in clients:
            self.clients["knowledge"] = clients["knowledge"]
        self.snapshot.pop("semanticMode", None)
        self.snapshot.update(knowledgeMode=mode, semanticPolicyVersion="4-knowledge-abc")
        if self.knowledge:
            self.snapshot.update(
                {k: knowledge[k] for k in ("knowledgeSetVersion", "knowledgeSetHash")}
            )

    async def prepare(self):
        if self.prepared:
            return
        client = self.clients.pop("knowledge", None)
        await super().prepare()
        # A malicious/legacy source discovery must not reintroduce source documents.
        forbidden = {n for n, b in self.registry.items() if b["originalName"] == "list_documents"}
        self.registry = {n: b for n, b in self.registry.items() if n not in forbidden}
        self.definitions = [d for d in self.definitions if d["name"] not in forbidden]
        if self.knowledge and client:
            self.clients["knowledge"] = client
            try:
                for tool in await client.list_tools():
                    if tool["name"] in KNOWLEDGE_TOOLS:
                        name = "knowledge__" + tool["name"]
                        self.registry[name] = {
                            "serverId": "knowledge",
                            "originalName": tool["name"],
                            "definition": tool,
                        }
                        self.definitions.append(native_definition({**tool, "name": name}))
            except Exception as exc:  # noqa: BLE001 - preserve per-run/discovery failure
                self.discovery_error = (
                    (self.discovery_error or "") + "; knowledge: " + type(exc).__name__
                )
        elif self.knowledge:
            self.discovery_error = (self.discovery_error or "") + "; knowledge MCP unavailable"
        self.registry_hash = hash_value(self.definitions)

    async def execute(self, name, arguments):
        await self.prepare()
        if name.startswith("knowledge__"):
            if not self.knowledge or name not in self.registry:
                raise ValueError("knowledge tool forbidden")
            binding = self.registry[name]
            version = self.knowledge["knowledgeSetVersion"]
            if arguments.get("knowledgeSetVersion") not in (None, version):
                raise ValueError("knowledge version mismatch")
            args = normalize_arguments(
                binding["definition"]["inputSchema"], {**arguments, "knowledgeSetVersion": version}
            )
            data = await self.clients["knowledge"].call(binding["originalName"], args)
            if (
                data.get("knowledgeSetVersion") != version
                or data.get("knowledgeSetHash") != self.knowledge["knowledgeSetHash"]
            ):
                raise ValueError("knowledge response mismatch")
            if "document" in data:
                doc = data["document"]
                known = next(
                    (
                        d
                        for d in self.knowledge["documents"]
                        if d["documentKey"] == data["documentKey"]
                    ),
                    None,
                )
                if (
                    not known
                    or doc["hash"] != known["hash"]
                    or hash_value({k: v for k, v in doc.items() if k != "hash"}) != known["hash"]
                ):
                    raise ValueError("document hash mismatch")
            evidence = self.put(name, args, data)
            evidence.update(systemId="knowledge", originalTool=binding["originalName"])
            return evidence
        return await super().execute(name, arguments)
