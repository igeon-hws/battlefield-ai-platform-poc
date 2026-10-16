from copy import deepcopy

from battlefield_ontology import MAPPING_VERSION, ONTOLOGY_VERSION

SOURCE_MAPPINGS = {
    "atcis": {
        "unitField": "ownerUnitCode",
        "availabilityField": "readyCode",
        "observedAtField": "observedAt",
        "typeField": "classCode",
        "availabilityValues": {"R": "available", "N": "unavailable", "U": "unknown"},
        "typeValues": {
            "TANK": "tank",
            "APC": "armored_vehicle",
            "SUPPORT": "support_vehicle",
            "UAV": "uav",
        },
    },
    "knccs": {
        "unitField": "orgRef",
        "availabilityField": "serviceability",
        "observedAtField": "reportTime",
        "typeField": "platformCategory",
        "availabilityValues": {
            "READY": "available",
            "NOT_READY": "unavailable",
            "UNCONFIRMED": "unknown",
        },
        "typeValues": {"SURFACE": "naval_vessel", "AIR": "unknown"},
        "uavCondition": {"platformCategory": "AIR", "aircraftType": "UNMANNED"},
    },
}

CONCEPTS = {
    "availability": {"concept": "availability", "value": "available"},
    "가용성": {"concept": "availability", "value": "available"},
    "available": {"concept": "availability", "value": "available"},
    "탱크": {"concept": "Equipment", "kind": "tank"},
    "tank": {"concept": "Equipment", "kind": "tank"},
    "함정": {"concept": "Equipment", "kind": "naval_vessel"},
    "무인기": {"concept": "Equipment", "kind": "uav"},
    "가용": {
        "concept": "availability",
        "value": "available",
        "meaning": "원천이 명시한 모의 가용 상태. 정비/이동 여부에서 추정하지 않음",
    },
    "전력": {"concept": "Equipment", "meaning": "모의 장비 목록 및 유형별 수량. 전투력 점수 아님"},
}


class SemanticService:
    """Reusable read API over the repository; neither LLM nor source-state access."""

    def __init__(self, repository):
        self.repository = repository

    def envelope(self, version, data):
        info = self.repository.require_ready(version)
        complete = data.get("complete", True)
        return {
            "graphVersion": version,
            "ontologyVersion": info["ontologyVersion"],
            "mappingVersion": info["mappingVersion"],
            "resolutionRuleVersion": info["resolutionRuleVersion"],
            "inputStableHashes": info["inputStableHashes"],
            "items": [],
            "paths": [],
            "sourceRefs": [],
            "evidenceRefs": [],
            "warnings": [] if complete else ["조회 범위가 완결되지 않았습니다."],
            "completeness": "complete" if complete else "partial",
            **data,
        }

    def interpret_concept(self, version, term):
        info = self.repository.require_ready(version)
        if info["ontologyVersion"] != ONTOLOGY_VERSION or info["mappingVersion"] != MAPPING_VERSION:
            raise ValueError("unsupported interpretation versions; prepare a current Graph build")
        item = CONCEPTS.get(term)
        return self.envelope(
            version,
            {
                "status": "resolved" if item else "unresolved",
                "supportedTerms": sorted(CONCEPTS),
                "sourceMappings": deepcopy(SOURCE_MAPPINGS) if item else {},
                "mappingRule": {
                    "ruleId": "SOURCE-CODE-INTERPRETATION",
                    "ruleVersion": MAPPING_VERSION,
                },
                "items": [
                    {
                        **item,
                        "term": term,
                        "ruleId": "CONCEPT-ALIAS",
                        "ruleVersion": ONTOLOGY_VERSION,
                    }
                ]
                if item
                else [],
            },
        )

    def resolve_unit_scope(self, version, term, max_depth=8):
        result = self.repository.unit_scope(version, term, max_depth)
        result["evidenceRefs"] = sorted(
            {e for path in result.get("paths", []) for e in path["evidenceRefs"]}
        )
        return self.envelope(version, result)

    def find_equipment_refs(self, version, unit_ids, kind=None, limit=100, cursor=0):
        return self.envelope(
            version, self.repository.equipment_refs(version, unit_ids, kind, limit, cursor)
        )

    def resolve_entity(self, version, system, native_id):
        return self.envelope(version, self.repository.resolve_entity(version, system, native_id))

    def get_semantic_evidence(self, version, evidence_id):
        item = self.repository.evidence(version, evidence_id)
        return self.envelope(
            version, {"item": item, "sourceRefs": item["sourceRefs"], "evidenceRefs": [evidence_id]}
        )
