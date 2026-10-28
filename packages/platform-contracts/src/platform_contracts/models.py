from typing import Literal

from c4i_contracts import Model
from pydantic import Field


class Finding(Model):
    text: str
    category: Literal["fact", "inference", "assumption"]
    evidence_ids: list[str]


class Course(Model):
    id: str
    title: str
    summary: str
    evidence_ids: list[str]
    expected_effects: list[str]
    risks_and_constraints: list[str]


class Claim(Model):
    kind: Literal["observation", "inference", "semantic", "calculation"]
    text: str = Field(min_length=1)
    evidence_refs: list[str]
    rule_refs: list[str] = Field(default_factory=list)


class AnalysisResultBody(Model):
    outcome: Literal["answer", "partial", "clarification"]
    answer: str = Field(min_length=1)
    findings: list[Finding]
    evidence_ids: list[str]
    limitations: list[str]
    courses: list[Course] | None = Field(min_length=3, max_length=3)


class AnalysisResult(AnalysisResultBody):
    claims: list[Claim] = Field(default_factory=list)


class DocumentCitation(Model):
    evidence_id: str
    document_key: str | None
    knowledge_set_version: str | None
    version: str | None
    hash: str | None


class ClaimProvenance(Model):
    version: Literal["1"]
    reported_kind: Literal["observation", "inference", "semantic", "calculation"]
    sources: list[Literal["source", "document", "semantic", "calculation"]]
    documents: list[DocumentCitation]
    document_rule_refs: list[str]
    unverified_rule_refs: list[str]


class ProvenancedClaim(Claim):
    provenance: ClaimProvenance


class ProvenancedAnalysisResult(AnalysisResultBody):
    provenance_version: Literal["1"]
    claims: list[ProvenancedClaim]


def strict_schema(schema: dict) -> dict:
    """Convert exported Pydantic optional fields to OpenAI's required-nullable convention."""
    import copy

    result = copy.deepcopy(schema)

    def walk(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if value.get("type") == "object":
                value["additionalProperties"] = False
                value["required"] = list(value.get("properties", {}))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    return result
