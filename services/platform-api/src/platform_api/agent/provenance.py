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


QUANTITY = re.compile(r"(\d+)\s*(대|개|척|건|명)")
HOURS = re.compile(r"(\d+)\s*(h|시간)(?![가-힣])")
CLOCK = re.compile(r"(?<!\d)(\d{2}:\d{2})(?!\d)")
# ASCII boundaries: Korean particles ("L-T02는") count as \w in Python and must not block a match.
IDENT = re.compile(r"(?<![A-Za-z0-9-])([A-Z]{1,4}-[A-Z]?\d{2,4})(?![A-Za-z0-9-])")
# Integers under these keys are counts a "N대/개" claim may restate; laborHours etc. are not.
COUNT_KEYS = {
    "total",
    "available",
    "quantity",
    "onHand",
    "reserved",
    "unreserved",
    "required",
    "shortfall",
    "reservedForThisWork",
    "unreservedAvailable",
    "allocatedFromUnreserved",
    "allocatedFromIncoming",
}


# Display-only or definition fields: their numbers (step counts, maxDepth) are not answer values.
SKIP_KEYS = {
    "steps",
    "excluded",
    "graphNodes",
    "graphEvidence",
    "relationLabels",
    "roleLabels",
    "appliedRules",
}


def _scan(value, key=None, under_counts=False, out=None):
    out = out if out is not None else {"counts": set(), "hours": set(), "text": []}
    if isinstance(value, dict):
        for k, v in value.items():
            if k in SKIP_KEYS:
                continue
            _scan(v, k, under_counts or k in ("counts", "byStatus", "byKindStatus"), out)
    elif isinstance(value, list):
        for v in value:
            _scan(v, key, under_counts, out)
    elif isinstance(value, bool):
        pass
    elif isinstance(value, int):
        if under_counts or key in COUNT_KEYS:
            out["counts"].add(value)
        if key == "laborHours":
            out["hours"].add(value)
    elif isinstance(value, str):
        out["text"].append(value)
    return out


def claim_class(claim, cited):
    """Deterministic: a fact restates values present in cited computed evidence."""
    if claim["kind"] == "inference":
        return "judgment", "모델이 추론으로 분류한 주장"
    computed = [e for e in cited if e.get("systemId") in ("semantic", "computed")]
    if not computed:
        return "judgment", "업무 질의·계산 도구 근거 없이 쓴 주장"
    found = _scan([e["data"] for e in cited])
    text = " ".join(found["text"])
    claim_text = claim["text"]
    missing = [
        m.group(0) for m in QUANTITY.finditer(claim_text) if int(m[1]) not in found["counts"]
    ]
    missing += [m.group(0) for m in HOURS.finditer(claim_text) if int(m[1]) not in found["hours"]]
    missing += [m[1] for m in CLOCK.finditer(claim_text) if m[1] not in text]
    missing += [m[1] for m in IDENT.finditer(claim_text) if m[1] not in text]
    if missing:
        return "judgment", "근거에 없는 값: " + ", ".join(dict.fromkeys(missing))
    checked = (
        QUANTITY.search(claim_text)
        or HOURS.search(claim_text)
        or CLOCK.search(claim_text)
        or IDENT.search(claim_text)
    )
    if not checked:
        return "judgment", "근거 값으로 확인할 수치·식별자가 없는 주장"
    return "fact", "인용한 업무 질의·계산 근거의 값과 일치"


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
        if mode == "structured":
            kind, reason = claim_class(claim, [evidence[r] for r in claim["evidenceRefs"]])
            claim["provenance"] |= {"claimClass": kind, "classReason": reason}
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
