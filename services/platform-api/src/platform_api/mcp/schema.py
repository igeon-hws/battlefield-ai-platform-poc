"""Convert discovered MCP input schemas; do not maintain a second C4I schema registry."""

from copy import deepcopy

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


def native_definition(tool: dict) -> dict:
    schema = deepcopy(tool["inputSchema"])
    Draft202012Validator.check_schema(schema)
    if schema.get("type") != "object":
        raise ValueError("tool inputSchema must be an object")

    def walk(node):
        if not isinstance(node, dict):
            raise TypeError("unsupported boolean schema")
        supported = {
            "type",
            "description",
            "title",
            "enum",
            "$defs",
            "$ref",
            "properties",
            "required",
            "additionalProperties",
            "items",
            "anyOf",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "multipleOf",
            "minItems",
            "maxItems",
            "minLength",
            "maxLength",
            "pattern",
            "default",
            "$schema",
        }
        unsupported = set(node) - supported
        if unsupported:
            raise ValueError(f"unsupported strict schema: {sorted(unsupported)}")
        node.pop("default", None)
        if "$ref" in node and not node["$ref"].startswith("#/$defs/"):
            raise ValueError("only local $defs references are supported")
        if node.get("type") == "object":
            if node.get("additionalProperties", False) is not False:
                raise ValueError("open object schemas cannot be converted to strict tools")
            props = node.setdefault("properties", {})
            required = set(node.get("required", []))
            for key, value in props.items():
                walk(value)
                if key not in required:
                    props[key] = {"anyOf": [value, {"type": "null"}]}
            node["required"] = list(props)
            node["additionalProperties"] = False
        for value in node.get("$defs", {}).values():
            walk(value)
        for value in node.get("anyOf", []):
            walk(value)
        if "items" in node:
            walk(node["items"])

    walk(schema)
    return {
        "type": "function",
        "name": tool["name"],
        "description": tool.get("description", ""),
        "strict": True,
        "parameters": schema,
    }


def normalize_arguments(schema: dict, arguments: dict) -> dict:
    """Map nullable strict optionals back to omission/defaults in the discovered schema."""

    def resolve(node):
        if "$ref" in node:
            return schema["$defs"][node["$ref"].split("/")[-1]]
        return node

    def normalize(node, value):
        node = resolve(node)
        if "anyOf" in node:
            for branch in node["anyOf"]:
                branch = resolve(branch)
                if (isinstance(value, dict) and branch.get("type") == "object") or (
                    isinstance(value, list) and branch.get("type") == "array"
                ):
                    return normalize(branch, value)
        if isinstance(value, dict) and node.get("type") == "object":
            props = node.get("properties", {})
            if value.keys() - props.keys():
                raise ValueError("unknown tool argument")
            required = node.get("required", [])
            result = {}
            for key, item in value.items():
                field = resolve(props[key])
                if item is None and key not in required:
                    if "default" in field:
                        result[key] = deepcopy(field["default"])
                    continue
                result[key] = normalize(field, item)
            return result
        if isinstance(value, list) and "items" in node:
            return [normalize(node["items"], item) for item in value]
        return value

    result = normalize(schema, deepcopy(arguments))
    try:
        Draft202012Validator(schema).validate(result)
    except ValidationError as exc:
        raise ValueError(f"invalid MCP tool arguments: {exc.message}") from exc
    return result
