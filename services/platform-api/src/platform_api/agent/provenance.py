"""Server-derived citation provenance; does not judge natural-language truth."""

import re

from platform_contracts.models import ProvenancedAnalysisResult


def rule_ids(value):
    if isinstance(value, dict):
        found = {value["ruleId"]} if isinstance(value.get("ruleId"), str) else set()
        for child in value.values():
            found.update(rule_ids(child))
        return found
    if isinstance(value, list):
        return {rule for child in value for rule in rule_ids(child)}
    return set()


def annotate_result(result, evidence, mode):
    cited = set(result["evidenceIds"])
    for item in result["findings"] + (result["courses"] or []):
        cited.update(item["evidenceIds"])
    for claim in result["claims"]:
        cited.update(claim["evidenceRefs"])
    for ref in cited:
        system = evidence[ref].get("systemId")
        if system == "semantic" and mode != "structured":
            raise ValueError("Semantic evidence forbidden in this knowledge mode")
        if system == "knowledge" and mode == "native":
            raise ValueError("Knowledge evidence forbidden in native mode")
    warnings = []
    for claim in result["claims"]:
        reported = claim["kind"]
        # Compatibility with old model responses. This is a conservative model
        # interpretation label, never a claim that the assertion is correct.
        if reported == "semantic":
            claim["kind"] = "inference"
        if claim["kind"] != "inference" and not claim["evidenceRefs"]:
            raise ValueError("grounded claim requires evidence")
        sources: set[str] = set()
        documents = []
        verified: set[str] = set()
        mentions: set[str] = set()
        requested = set(claim["ruleRefs"])
        for ref in claim["evidenceRefs"]:
            item = evidence[ref]
            system = item.get("systemId")
            data = item["data"]
            sources.add(
                {"knowledge": "document", "semantic": "semantic", "computed": "calculation"}.get(
                    system, "source"
                )
            )
            if system in ("semantic", "computed") and mode == "structured":
                verified.update(rule_ids(data))
            if system == "knowledge" and isinstance(data.get("document"), dict):
                doc = data["document"]
                text = doc.get("text", "")
                mentions.update(
                    rule
                    for rule in requested
                    if re.search(r"(?<![\w-])" + re.escape(rule) + r"(?![\w-])", text)
                )
                documents.append(
                    {
                        "evidenceId": ref,
                        "documentKey": data.get("documentKey"),
                        "knowledgeSetVersion": data.get("knowledgeSetVersion"),
                        "version": doc.get("version"),
                        "hash": doc.get("hash"),
                    }
                )
        unknown = requested - verified - mentions
        claim["ruleRefs"] = sorted(requested & verified)
        claim["provenance"] = {
            "version": "1",
            "reportedKind": reported,
            "sources": sorted(sources),
            "documents": documents,
            "documentRuleRefs": sorted(mentions),
            "unverifiedRuleRefs": sorted(unknown),
        }
        if unknown:
            warnings.append(
                "주장에 인용한 규칙 표기를 확인하지 못했습니다: " + ", ".join(sorted(unknown))
            )
    result["provenanceVersion"] = "1"
    if warnings:
        result["limitations"].extend(dict.fromkeys(warnings))
        if result["outcome"] == "answer":
            result["outcome"] = "partial"
    ProvenancedAnalysisResult.model_validate(result)
