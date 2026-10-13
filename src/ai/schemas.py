"""JSON schema definitions and recursive validation for structured AI outputs."""
from src.exceptions import ProviderError


def object_schema(properties: dict) -> dict:
    """Create strict JSON schema dictionary for an object with required properties."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


STRING = {"type": "string"}

ANALYSIS_SCHEMA = object_schema({
    "status": {"type": "string", "enum": ["ready", "clarification", "split", "unsupported"]},
    "section_id": STRING,
    "question": STRING,
    "proposals": {
        "type": "array",
        "items": object_schema({
            "section_id": STRING,
            "instruction": STRING,
        }),
    },
})

EDIT_SCHEMA = object_schema({
    "status": {"type": "string", "enum": ["ready", "clarification", "unsupported"]},
    "text": STRING,
    "question": STRING,
})

REPAIR_SCHEMA = object_schema({
    "patches": {
        "type": "array",
        "items": object_schema({
            "file": STRING,
            "old_text": STRING,
            "new_text": STRING,
        }),
    },
})


def validate_json(value, schema: dict):
    """Validate JSON payload against a subset of JSON schema."""
    kind = schema["type"]
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str)}.get(kind, False)
    if not valid or ("enum" in schema and value not in schema["enum"]):
        raise ProviderError("The model returned an invalid structured response.")
    if kind == "object":
        if set(value) != set(schema["required"]):
            raise ProviderError("The model returned incomplete or unexpected fields.")
        for name, child in schema["properties"].items():
            validate_json(value[name], child)
    elif kind == "array":
        for item in value:
            validate_json(item, schema["items"])
