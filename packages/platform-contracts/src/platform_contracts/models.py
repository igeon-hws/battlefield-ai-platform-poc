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


class AnalysisResult(Model):
    outcome: Literal["answer", "partial", "clarification"]
    answer: str = Field(min_length=1)
    findings: list[Finding]
    evidence_ids: list[str]
    limitations: list[str]
    courses: list[Course] | None = Field(min_length=3, max_length=3)


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
