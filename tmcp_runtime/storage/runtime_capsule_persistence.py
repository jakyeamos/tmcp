"""Closed runtime-capsule restoration for protected local artifacts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.composition_runtime_capsules import (
    RuntimeCapsuleError,
    validate_runtime_capsule,
)


RUNTIME_CAPSULE_HASH_FIELDS = (
    "composition_plan_digest",
    "phase_capsule_binding_digest",
    "objective_digest",
    "task_identity_digest",
    "preparation_controls_digest",
    "capsule_digest",
)
_SHA256_DIGEST_PATTERN = re.compile(r"[a-f0-9]{64}")


def runtime_capsule_hash_paths(
    prefix: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    """Return the fixed same-read digest paths required by one capsule."""

    return (
        *(prefix + (field,) for field in RUNTIME_CAPSULE_HASH_FIELDS),
        *(
            prefix + ("cited_source_slices", "*", field)
            for field in ("source_digest", "slice_digest")
        ),
    )


def runtime_capsule_sha256_literals(
    value: Mapping[str, Any], *, prefix: tuple[str | int, ...]
) -> dict[tuple[str | int, ...], str]:
    """Project only closed capsule hashes from an in-memory compiler result."""

    result: dict[tuple[str | int, ...], str] = {}

    def add(path: tuple[str | int, ...], item: object) -> None:
        if isinstance(item, str) and _SHA256_DIGEST_PATTERN.fullmatch(item):
            result[path] = item

    for field in RUNTIME_CAPSULE_HASH_FIELDS:
        add(prefix + (field,), value.get(field))
    descriptors = value.get("cited_source_slices")
    if isinstance(descriptors, list):
        for index, descriptor in enumerate(descriptors):
            if not isinstance(descriptor, Mapping):
                continue
            descriptor_prefix = prefix + ("cited_source_slices", index)
            for field in ("source_digest", "slice_digest"):
                add(descriptor_prefix + (field,), descriptor.get(field))
    return result


def runtime_capsule_restored_literal_count(
    value: Mapping[str, Any],
    *,
    prefix: tuple[str | int, ...],
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> int:
    """Count known digest leaves that a safe same-read projection restores."""

    if literals is None:
        return 0
    restored = 0
    for field in RUNTIME_CAPSULE_HASH_FIELDS:
        literal = literals.get(prefix + (field,))
        if literal is not None and value.get(field) != literal:
            restored += 1
    descriptors = value.get("cited_source_slices")
    if not isinstance(descriptors, list):
        return restored
    for index, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, Mapping):
            continue
        descriptor_prefix = prefix + ("cited_source_slices", index)
        for field in ("source_digest", "slice_digest"):
            literal = literals.get(descriptor_prefix + (field,))
            if literal is not None and descriptor.get(field) != literal:
                restored += 1
    return restored


def _literal(
    value: object,
    *,
    path: tuple[str | int, ...],
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> object:
    if literals is None:
        return value
    restored = literals.get(path)
    if restored is None or _SHA256_DIGEST_PATTERN.fullmatch(restored) is None:
        return value
    return restored


def _restored_candidate(
    value: Mapping[str, Any],
    *,
    prefix: tuple[str, ...],
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> dict[str, Any]:
    candidate = deepcopy(dict(value))
    for field in RUNTIME_CAPSULE_HASH_FIELDS:
        candidate[field] = _literal(
            candidate.get(field), path=prefix + (field,), literals=literals
        )
    descriptors = candidate.get("cited_source_slices")
    if not isinstance(descriptors, list):
        return candidate
    for index, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, dict):
            continue
        descriptor_prefix = prefix + ("cited_source_slices", index)
        for field in ("source_digest", "slice_digest"):
            descriptor[field] = _literal(
                descriptor.get(field),
                path=descriptor_prefix + (field,),
                literals=literals,
            )
    return candidate


def runtime_capsule_matches_phase_binding(
    capsule: Mapping[str, Any], binding: Mapping[str, Any]
) -> bool:
    return all(
        capsule.get(capsule_field) == binding.get(binding_field)
        for capsule_field, binding_field in (
            ("composition_plan_id", "composition_plan_id"),
            ("composition_plan_digest", "composition_plan_digest"),
            ("preflight_id", "preflight_id"),
            ("compiler_phase", "compiler_phase"),
            ("graph_digest", "graph_digest"),
            ("phase_capsule_binding_digest", "binding_digest"),
        )
    )


def restore_runtime_capsule(
    value: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    prefix: tuple[str, ...],
    literals: Mapping[tuple[str | int, ...], str] | None,
    composition_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return only a closed capsule that remains bound to the phase binding."""

    raw_capsule = value.get("runtime_capsule")
    if not isinstance(raw_capsule, Mapping):
        return None
    try:
        capsule = validate_runtime_capsule(
            _restored_candidate(raw_capsule, prefix=prefix, literals=literals),
            composition_plan=composition_plan,
        )
    except RuntimeCapsuleError:
        return None
    return capsule if runtime_capsule_matches_phase_binding(capsule, binding) else None
