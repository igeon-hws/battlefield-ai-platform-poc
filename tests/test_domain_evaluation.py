import importlib.util
from pathlib import Path


def grader():
    spec = importlib.util.spec_from_file_location(
        "grade_domain", Path(__file__).resolve().parents[1] / "scripts/grade_domain.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_completed_run_is_not_automatically_a_correct_answer():
    grade = grader()
    record = {
        "scenario": "F7",
        "mode": "on",
        "state": {
            "status": "completed",
            "toolCalls": [],
            "result": {"claims": []},
            "evidence": [
                {
                    "evidenceId": "e1",
                    "systemId": "computed",
                    "originalTool": "aggregate_evidence",
                    "data": {
                        "interpretation": "semantic_evidence",
                        "counts": {"available": 99},
                        "items": [],
                    },
                }
            ],
        },
    }
    result = grade.grade_record(
        record,
        {"counts": {"available": 4}, "includedIds": ["expected"], "ruleIds": ["AVAIL-LAND-01"]},
    )
    assert result["executionCompleted"] is True
    assert result["deterministicFactsMatch"] is False
    assert result["answerReviewRequired"] is True
    assert result["missingRuleIds"] == ["AVAIL-LAND-01"]


def test_off_poisoned_semantic_tool_is_a_boundary_failure():
    grade = grader()
    record = {
        "scenario": "F1",
        "mode": "off",
        "state": {
            "status": "completed",
            "toolCalls": [{"name": "semantic__resolve_entity"}],
            "result": {"claims": []},
            "evidence": [],
        },
    }
    assert grade.grade_record(record, {"ruleIds": []})["offBoundaryValid"] is False
