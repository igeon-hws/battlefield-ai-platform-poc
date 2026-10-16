import pytest
from battlefield_ontology import Observation, RelationType, SourceRef, System, Unit
from pydantic import ValidationError


def test_common_ontology_models_are_explicit_and_validate_evidence():
    ref = SourceRef(systemId="atcis", datasetId="d", epochId="e", recordType="unit", nativeId="D1")
    unit = Unit(canonicalId="atcis:D1", name="모의 1사단", sourceRef=ref)
    assert unit.public()["canonicalId"] == "atcis:D1"
    assert System(systemId="atcis", name="Mock ATCIS").synthetic is True
    with pytest.raises(ValidationError):
        Observation(
            observationId="obs",
            assertionType=RelationType.ASSIGNED_TO,
            sourceRefs=[],
            ruleId="r",
            ruleVersion="1",
            payloadHash="h",
        )
    with pytest.raises(ValueError):
        RelationType("LLM_GUESSED_RELATION")
