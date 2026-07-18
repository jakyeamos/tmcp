"""Shared normalization helpers for deterministic phase capsules."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .composition_preflight import stable_digest
from .harvest_nodes import estimate_tokens


class PhaseCapsuleError(ValueError):
    """Raised when phase capsule input is not deterministic JSON data."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_value(value: object, *, field: str) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PhaseCapsuleError(f"{field} must not contain a non-finite number.")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PhaseCapsuleError(f"{field} must use string object keys.")
            result[key] = _json_value(item, field=f"{field}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [
            _json_value(item, field=f"{field}[{index}]")
            for index, item in enumerate(value)
        ]
    raise PhaseCapsuleError(f"{field} must contain only JSON-compatible values.")


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise PhaseCapsuleError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise PhaseCapsuleError(f"{field} must contain only objects.")
    return result


def _string_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise PhaseCapsuleError(f"{field} must be a sequence of strings.")
    result = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    if len(result) != len(value):
        raise PhaseCapsuleError(f"{field} must contain only nonempty strings.")
    if len(result) != len(set(result)):
        raise PhaseCapsuleError(f"{field} must not contain duplicate strings.")
    return result


def _nonempty(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise PhaseCapsuleError(f"{field} is required.")
    return result


def _capsule_record(capsule: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _json_value(capsule, field="capsule")
    serialized = _canonical_json(normalized)
    return {
        "capsule": normalized,
        "canonical_json": serialized,
        "capsule_digest": stable_digest(normalized),
        "estimated_tokens": estimate_tokens(serialized),
    }


def _agent_objective(
    runtime_envelope: Mapping[str, Any], *, preflight: Mapping[str, Any]
) -> str:
    """Return the one controller field that must enter an isolated agent phase."""

    for value in (runtime_envelope.get("objective"), preflight.get("objective")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
