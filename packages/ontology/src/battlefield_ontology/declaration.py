"""v6 declarative ontology: validate, render B documents, apply reviewed edits, impact.

The declaration is the single source of semantic definitions. B reads the rendered text,
C compiles the same declaration into Graph rules and business queries.
"""

import copy
import json
import os
from pathlib import Path

from battlefield_ontology import digest

DOCUMENT_KEY = "fabric:ONTOLOGY-01"
OPERATORS = {"asset_status_summary", "asset_dependency_chain", "part_supply_status"}


def profile6():
    return os.getenv("C4I_CONTRACT_VERSION") == "5" and os.getenv("C4I_ONTOLOGY_PROFILE") == "6"


def comparison_policy(contract="5"):
    if contract == "5":
        return "6-ontology-abc" if profile6() else "5-logistics-abc"
    return "4-knowledge-abc"


def load_base():
    return json.loads(Path(__file__).with_name("ontology_v6.json").read_text(encoding="utf-8"))


def declaration_version(decl):
    return f"{decl['version']}-r{decl['revision']}"


def rule_map(decl):
    return {r["ruleId"]: r for r in decl["rules"]}


def validate(decl):
    rules = rule_map(decl)
    if len(rules) != len(decl["rules"]):
        raise ValueError("duplicate rule id")
    relations = {r["id"] for r in decl["relationTypes"]}
    if len(relations) != len(decl["relationTypes"]):
        raise ValueError("duplicate relation type")
    queries = [q["queryId"] for q in decl["businessQueries"]]
    if len(set(queries)) != len(queries):
        raise ValueError("duplicate business query")
    for rule in decl["rules"]:
        for dep in rule["dependsOn"]:
            if dep not in rules:
                raise ValueError("undefined rule dependency: " + dep)
    for relation in decl["relationTypes"]:
        if relation["rule"] not in rules:
            raise ValueError("undefined rule on relation: " + relation["id"])
    for term, ids in decl["terms"].items():
        for rule_id in ids:
            if rule_id not in rules:
                raise ValueError("undefined rule for term: " + term)
    for query in decl["businessQueries"]:
        if query["operator"] not in OPERATORS:
            raise ValueError("unsupported operator: " + query["operator"])
        for rule_id in query["rules"]:
            if rule_id not in rules:
                raise ValueError("undefined rule in business query: " + rule_id)
        for relation in query["relations"]:
            if relation not in relations:
                raise ValueError("undefined relation in business query: " + relation)
    for screen in decl["screens"]:
        for rule_id in screen["rules"]:
            if rule_id not in rules:
                raise ValueError("undefined rule on screen: " + rule_id)
    for item in decl["editable"]:
        value = get_path(decl, item["path"])
        if item["type"] == "enum" and value not in item["options"]:
            raise ValueError("editable value outside options: " + item["path"])
    # Dependency cycles would make expansion and impact analysis ambiguous.
    state: dict[str, str] = {}

    def visit(rule_id):
        if state.get(rule_id) == "active":
            raise ValueError("rule dependency cycle at " + rule_id)
        if state.get(rule_id) == "done":
            return
        state[rule_id] = "active"
        for dep in rules[rule_id]["dependsOn"]:
            visit(dep)
        state[rule_id] = "done"

    for rule_id in rules:
        visit(rule_id)
    return decl


def get_path(decl, path):
    head, rest = path.split(".", 1)
    if head != "rules":
        raise ValueError("unsupported declaration path")
    rule_id, field_path = rest.split(".", 1)
    value = rule_map(decl)[rule_id]
    for part in field_path.split("."):
        value = value[part]
    return value


def set_path(decl, path, value):
    _, rest = path.split(".", 1)
    rule_id, field_path = rest.split(".", 1)
    target = rule_map(decl)[rule_id]
    parts = field_path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def apply_edits(decl, edits):
    editable = {item["path"]: item for item in decl["editable"]}
    changed = copy.deepcopy(decl)
    for path, value in edits.items():
        item = editable.get(path)
        if item is None:
            raise ValueError("path is not editable: " + path)
        if item["type"] == "enum" and value not in item["options"]:
            raise ValueError("value is not an allowed option: " + str(value))
        set_path(changed, path, value)
    changed["revision"] = decl["revision"] + 1
    return validate(changed)


def diff(old, new):
    labels = {item["path"]: item["label"] for item in new["editable"]}
    return [
        {"path": path, "label": label, "before": get_path(old, path), "after": get_path(new, path)}
        for path, label in labels.items()
        if get_path(old, path) != get_path(new, path)
    ]


def impact(old, new):
    """Deterministic reach of an edit through declared dependencies; no model involved."""
    changed = sorted(r["ruleId"] for r in new["rules"] if rule_map(old).get(r["ruleId"]) != r)
    reach = set(changed)
    grew = True
    while grew:
        grew = False
        for rule in new["rules"]:
            if rule["ruleId"] not in reach and reach & set(rule["dependsOn"]):
                reach.add(rule["ruleId"])
                grew = True
    return {
        "rules": changed,
        "dependentRules": sorted(reach - set(changed)),
        "businessQueries": [
            q["queryId"] for q in new["businessQueries"] if reach & set(q["rules"])
        ],
        "screens": [s["screenId"] for s in new["screens"] if reach & set(s["rules"])],
        "terms": sorted(t for t, ids in new["terms"].items() if reach & set(ids)),
    }


def compiled_ids(decl):
    return {
        "rules": sorted(r["ruleId"] for r in decl["rules"]),
        "businessQueries": sorted(q["queryId"] for q in decl["businessQueries"]),
    }


def render(decl):
    """Human/LLM-readable document with the same definitions C executes."""
    rules = rule_map(decl)
    policy = rules["AGGREGATION-POLICY-01"]["definition"]
    lines = [
        f"{decl['title']} — 선언 {declaration_version(decl)} (ontologyId {decl['ontologyId']}).",
        "이 문서는 Fabric이 검토·발행한 온톨로지 선언을 그대로 풀어 쓴 것이며, 구조화 지식 조건이 실행하는 정의와 같다.",
        (
            f"기본 가용 집계 기준: {policy['defaultAvailablePolicy']} "
            f"({'가용+제한(PMC) 포함' if policy['defaultAvailablePolicy'] == 'P2' else '가용(FMC)만'}). "
            "질문이 기준을 명시하지 않으면 이 기준으로 '가용' 수를 답하고, 원래 상태 분류(available/limited/unavailable/unknown)는 바꾸지 않는다."
        ),
        "",
        "[개념]",
    ]
    for concept in decl["concepts"]:
        identity = f", 동일성 규칙 {concept['identity']}" if concept.get("identity") else ""
        lines.append(
            f"- {concept['id']}({concept['label']}): 원천 {', '.join(concept['sources'])}{identity}"
        )
    lines += ["", "[관계 유형]"]
    for relation in decl["relationTypes"]:
        lines.append(
            f"- {relation['id']}: {relation['from']} → {relation['to']} ({relation['label']}), 규칙 {relation['rule']}"
        )
    lines += ["", "[규칙]"]
    for rule in decl["rules"]:
        deps = f"; 의존 {', '.join(rule['dependsOn'])}" if rule["dependsOn"] else ""
        lines.append(
            f"- {rule['ruleId']} {rule['title']} (출처 {rule['documentKey']}{deps}): "
            + json.dumps(rule["definition"], ensure_ascii=False, sort_keys=True)
        )
    lines += ["", "[용어]"]
    for term, ids in decl["terms"].items():
        lines.append(f"- {term}: {', '.join(ids)}")
    lines += ["", "[업무 질의 정의]"]
    for query in decl["businessQueries"]:
        params = ", ".join(
            f"{name}{'' if spec.get('required') else '?'}" for name, spec in query["params"].items()
        )
        lines.append(
            f"- {query['queryId']} {query['title']}({params}): {query['description']} "
            f"규칙 {', '.join(query['rules'])}; 관계 {', '.join(query['relations'])}"
        )
    return "\n".join(lines)


def knowledge_item(decl):
    validate(decl)
    document = {
        "documentId": "ONTOLOGY-01",
        "version": declaration_version(decl),
        "issuer": "Fabric 온톨로지 검토",
        "section": "ontology",
        "knownAt": decl["knownAt"],
        "effectiveFrom": decl["effectiveFrom"],
        "text": render(decl),
        "declaration": decl,
    }
    document["hash"] = digest(document)
    return {
        "documentKey": DOCUMENT_KEY,
        "namespace": "fabric",
        "appliesTo": ["atcis", "knccs", "logistics"],
        "reviewRevision": f"ontology-r{decl['revision']}",
        "document": document,
    }


def from_documents(documents):
    item = next((d for d in documents or [] if d["documentKey"] == DOCUMENT_KEY), None)
    return validate(copy.deepcopy(item["document"]["declaration"])) if item else None
