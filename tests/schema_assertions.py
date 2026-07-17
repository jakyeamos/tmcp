"""Small dependency-free JSON Schema subset used by contract instance tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SchemaAssertionError(AssertionError):
    pass


def _document(path: Path, cache: dict[Path, dict[str, Any]]) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved not in cache:
        value = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SchemaAssertionError(f"{resolved} is not a schema object")
        cache[resolved] = value
    return cache[resolved]


def _pointer(document: Any, fragment: str) -> Any:
    value = document
    if not fragment:
        return value
    if not fragment.startswith("/"):
        raise SchemaAssertionError(f"unsupported schema fragment #{fragment}")
    for raw_part in fragment[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or part not in value:
            raise SchemaAssertionError(f"unresolved schema fragment #{fragment}")
        value = value[part]
    return value


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def _validate(
    value: Any,
    schema: dict[str, Any],
    *,
    schema_path: Path,
    root: dict[str, Any],
    cache: dict[Path, dict[str, Any]],
    instance_path: str,
) -> None:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        path_part, _, fragment = reference.partition("#")
        target_path = schema_path if not path_part else schema_path.parent / path_part
        target_root = _document(target_path, cache)
        target = _pointer(target_root, fragment)
        if not isinstance(target, dict):
            raise SchemaAssertionError(f"{reference} does not resolve to an object")
        _validate(
            value,
            target,
            schema_path=target_path.resolve(),
            root=target_root,
            cache=cache,
            instance_path=instance_path,
        )

    for item in schema.get("allOf", []):
        if isinstance(item, dict):
            _validate(
                value,
                item,
                schema_path=schema_path,
                root=root,
                cache=cache,
                instance_path=instance_path,
            )
    any_of = [item for item in schema.get("anyOf", []) if isinstance(item, dict)]
    if any_of:
        errors: list[str] = []
        for item in any_of:
            try:
                _validate(
                    value,
                    item,
                    schema_path=schema_path,
                    root=root,
                    cache=cache,
                    instance_path=instance_path,
                )
                break
            except SchemaAssertionError as exc:
                errors.append(str(exc))
        else:
            raise SchemaAssertionError(
                f"{instance_path} does not match anyOf: {'; '.join(errors)}"
            )

    if "const" in schema and value != schema["const"]:
        raise SchemaAssertionError(
            f"{instance_path} expected const {schema['const']!r}, got {value!r}"
        )
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaAssertionError(f"{instance_path} is not in enum")
    raw_type = schema.get("type")
    expected_types = raw_type if isinstance(raw_type, list) else [raw_type]
    expected_types = [item for item in expected_types if isinstance(item, str)]
    if expected_types and not any(
        _matches_type(value, item) for item in expected_types
    ):
        raise SchemaAssertionError(
            f"{instance_path} expected {expected_types}, got {type(value).__name__}"
        )

    if isinstance(value, dict):
        required = [
            item for item in schema.get("required", []) if isinstance(item, str)
        ]
        missing = [item for item in required if item not in value]
        if missing:
            raise SchemaAssertionError(f"{instance_path} missing required {missing}")
        properties = schema.get("properties")
        property_map = properties if isinstance(properties, dict) else {}
        for key, item in value.items():
            child_schema = property_map.get(key)
            if isinstance(child_schema, dict):
                _validate(
                    item,
                    child_schema,
                    schema_path=schema_path,
                    root=root,
                    cache=cache,
                    instance_path=f"{instance_path}.{key}",
                )
            elif schema.get("additionalProperties") is False:
                raise SchemaAssertionError(
                    f"{instance_path} contains additional property {key!r}"
                )
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate(
                    item,
                    schema["additionalProperties"],
                    schema_path=schema_path,
                    root=root,
                    cache=cache,
                    instance_path=f"{instance_path}.{key}",
                )
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise SchemaAssertionError(f"{instance_path} has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise SchemaAssertionError(f"{instance_path} has too many items")
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                raise SchemaAssertionError(f"{instance_path} items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(
                    item,
                    item_schema,
                    schema_path=schema_path,
                    root=root,
                    cache=cache,
                    instance_path=f"{instance_path}[{index}]",
                )
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise SchemaAssertionError(f"{instance_path} is too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise SchemaAssertionError(f"{instance_path} is too long")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise SchemaAssertionError(f"{instance_path} does not match {pattern}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaAssertionError(f"{instance_path} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaAssertionError(f"{instance_path} is above maximum")


def assert_matches_schema(instance: Any, schema_path: Path) -> None:
    cache: dict[Path, dict[str, Any]] = {}
    resolved = schema_path.resolve()
    root = _document(resolved, cache)
    _validate(
        instance,
        root,
        schema_path=resolved,
        root=root,
        cache=cache,
        instance_path="$",
    )
