"""Closed source rehydration capsules for persisted semantic compositions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .composition_phase_bindings import (
    PhaseCapsuleBindingError,
    validate_phase_capsule_binding,
)
from .composition_phase_slice_closures import (
    PhaseSliceClosureError,
    plan_stage_source_slice_closure,
)
from .composition_preflight import ACTIVE_SOURCE_ROLES, PHASE_ORDER, stable_digest
from .harvest_nodes import content_digest_for, normalized_source_content


RUNTIME_CAPSULE_SCHEMA = "tmcp-composition-runtime-capsule-v0.1"
PREPARATION_CONTROLS_SCHEMA = "tmcp-composition-preparation-controls-v0.1"
RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD = "composition_provenance_status"
RUNTIME_CAPSULE_INVALID_PROVENANCE_STATUS = "runtime_capsule_invalid"
MAX_RUNTIME_CAPSULE_SLICES = 48
MAX_RUNTIME_CAPSULE_ATOMS_PER_SOURCE = 24
MAX_RUNTIME_CAPSULE_ATOM_CHARS = 240
MAX_RUNTIME_CAPSULE_RELATIVE_PATH_CHARS = 1024
PREPARATION_CONTROL_ARGUMENT_FIELDS = (
    "candidate_limit",
    "max_excerpt_chars",
    "max_total_chars",
    "max_total_tokens",
    "include_all_active_source_slices",
    "explicitly_scoped_paths",
)

_DIGEST_32_RE = re.compile(r"[a-f0-9]{32}")
_DIGEST_64_RE = re.compile(r"[a-f0-9]{64}")
_PLAN_ID_RE = re.compile(r"composition-[a-f0-9]{20}")
_PREFLIGHT_ID_RE = re.compile(r"preflight-[a-f0-9]{20}")
_CAPSULE_FIELDS = frozenset(
    {
        "schema",
        "composition_plan_id",
        "composition_plan_digest",
        "preflight_id",
        "compiler_phase",
        "graph_digest",
        "phase_capsule_binding_digest",
        "objective_digest",
        "task_identity_digest",
        "preparation_controls",
        "preparation_controls_digest",
        "cited_source_slices",
        "capsule_digest",
    }
)
_CONTROL_FIELDS = frozenset(
    {
        "schema",
        "candidate_limit",
        "max_excerpt_chars",
        "max_total_chars",
        "max_total_tokens",
        "include_all_active_source_slices",
        "explicitly_scoped_paths",
    }
)
_SLICE_FIELDS = frozenset(
    {
        "original_node_id",
        "source_role",
        "source_digest",
        "slice_digest",
        "char_start",
        "char_end",
        "relative_path",
        "behavior_atoms",
    }
)
_TASK_IDENTITY_SCALAR_FIELDS = (
    "primary",
    "routing_status",
    "route_catalog_version",
)
_TASK_IDENTITY_LIST_FIELDS = (
    "secondary",
    "active_routes",
    "validated_routes",
    "intent_facets",
)
_RECEIPT_RUNTIME_CAPSULE_PROVENANCE_FIELDS = frozenset(
    {
        "phase_capsule_binding_digest",
        "context_accounting_digest",
        "preflight_capsule_digest",
        "phase_capsule_trace",
    }
)


class RuntimeCapsuleError(ValueError):
    """Raised when a persisted composition cannot be safely rehydrated."""


def packet_has_runtime_capsule_provenance(
    packet: Mapping[str, Any], *, plan: Mapping[str, Any] | None = None
) -> bool:
    """Identify a packet that must never downgrade into legacy rebinding."""

    if (
        packet.get(RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD)
        == RUNTIME_CAPSULE_INVALID_PROVENANCE_STATUS
    ):
        return True
    candidate_plan = plan if isinstance(plan, Mapping) else packet.get("composition_plan")
    if isinstance(candidate_plan, Mapping) and any(
        field in candidate_plan
        for field in ("phase_capsule_binding", "runtime_capsule")
    ):
        return True
    receipt = packet.get("receipt_template")
    return isinstance(receipt, Mapping) and any(
        field in receipt for field in _RECEIPT_RUNTIME_CAPSULE_PROVENANCE_FIELDS
    )


def _required(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise RuntimeCapsuleError(f"{field} is required.")
    return result


def _digest(value: object, *, field: str, length: int = 64) -> str:
    result = _required(value, field=field)
    pattern = _DIGEST_32_RE if length == 32 else _DIGEST_64_RE
    if pattern.fullmatch(result) is None:
        raise RuntimeCapsuleError(f"{field} must be a sha256 digest.")
    return result


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RuntimeCapsuleError(f"{field} must be an integer >= {minimum}.")
    return value


def _bounded_strings(
    value: object,
    *,
    field: str,
    maximum_items: int,
    maximum_chars: int,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise RuntimeCapsuleError(f"{field} must contain at most {maximum_items} strings.")
    items = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip() and len(item.strip()) <= maximum_chars
    ]
    if len(items) != len(value) or len(items) != len(set(items)):
        raise RuntimeCapsuleError(f"{field} must contain unique bounded strings.")
    return items


def _compiler_phase(value: object, *, field: str) -> str:
    phase = _required(value, field=field)
    if phase not in PHASE_ORDER:
        raise RuntimeCapsuleError(f"{field} is not a supported compiler phase.")
    return phase


def _task_identity_projection(value: object) -> dict[str, Any]:
    """Bind semantic routing identity, not volatile scoring evidence."""

    if not isinstance(value, Mapping):
        raise RuntimeCapsuleError("task_identity must be an object.")
    projection: dict[str, Any] = {}
    for field in _TASK_IDENTITY_SCALAR_FIELDS:
        if field not in value:
            continue
        item = value[field]
        if not isinstance(item, str) or not item.strip():
            raise RuntimeCapsuleError(f"task_identity.{field} must be a string.")
        projection[field] = item.strip()
    for field in _TASK_IDENTITY_LIST_FIELDS:
        if field not in value:
            continue
        items = value[field]
        if not isinstance(items, list) or any(
            not isinstance(item, str) or not item.strip() for item in items
        ):
            raise RuntimeCapsuleError(f"task_identity.{field} must be string values.")
        projection[field] = sorted({item.strip() for item in items})
    return projection


def _controls(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONTROL_FIELDS:
        raise RuntimeCapsuleError("preparation_controls has invalid fields.")
    if value.get("schema") != PREPARATION_CONTROLS_SCHEMA:
        raise RuntimeCapsuleError("preparation_controls.schema is invalid.")
    paths = value.get("explicitly_scoped_paths")
    if not isinstance(paths, list) or any(
        not isinstance(item, str) or not item.strip() for item in paths
    ):
        raise RuntimeCapsuleError(
            "preparation_controls.explicitly_scoped_paths must be strings."
        )
    normalized_paths = sorted({item.strip() for item in paths})
    if normalized_paths != paths:
        raise RuntimeCapsuleError(
            "preparation_controls.explicitly_scoped_paths must be sorted and unique."
        )
    include_all = value.get("include_all_active_source_slices")
    if not isinstance(include_all, bool):
        raise RuntimeCapsuleError(
            "preparation_controls.include_all_active_source_slices must be boolean."
        )
    controls = {
        "schema": PREPARATION_CONTROLS_SCHEMA,
        "candidate_limit": _integer(
            value.get("candidate_limit"),
            field="preparation_controls.candidate_limit",
            minimum=1,
        ),
        "max_excerpt_chars": _integer(
            value.get("max_excerpt_chars"),
            field="preparation_controls.max_excerpt_chars",
            minimum=64,
        ),
        "max_total_chars": _integer(
            value.get("max_total_chars"),
            field="preparation_controls.max_total_chars",
            minimum=64,
        ),
        "max_total_tokens": _integer(
            value.get("max_total_tokens"),
            field="preparation_controls.max_total_tokens",
            minimum=16,
        ),
        "include_all_active_source_slices": include_all,
        "explicitly_scoped_paths": normalized_paths,
    }
    if controls["candidate_limit"] > 24:
        raise RuntimeCapsuleError("preparation_controls.candidate_limit is too large.")
    return controls


def _slice_descriptor(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SLICE_FIELDS:
        raise RuntimeCapsuleError(f"{field} has invalid fields.")
    role = _required(value.get("source_role"), field=f"{field}.source_role")
    if role not in ACTIVE_SOURCE_ROLES:
        raise RuntimeCapsuleError(f"{field}.source_role is not activation eligible.")
    start = _integer(value.get("char_start"), field=f"{field}.char_start")
    end = _integer(value.get("char_end"), field=f"{field}.char_end", minimum=1)
    if end <= start:
        raise RuntimeCapsuleError(f"{field} has an invalid source range.")
    relative_path = _required(
        value.get("relative_path"), field=f"{field}.relative_path"
    )
    if len(relative_path) > MAX_RUNTIME_CAPSULE_RELATIVE_PATH_CHARS:
        raise RuntimeCapsuleError(f"{field}.relative_path is too long.")
    return {
        "original_node_id": _required(
            value.get("original_node_id"), field=f"{field}.original_node_id"
        ),
        "source_role": role,
        "source_digest": _digest(
            value.get("source_digest"), field=f"{field}.source_digest"
        ),
        "slice_digest": _digest(
            value.get("slice_digest"), field=f"{field}.slice_digest"
        ),
        "char_start": start,
        "char_end": end,
        "relative_path": relative_path,
        "behavior_atoms": _bounded_strings(
            value.get("behavior_atoms"),
            field=f"{field}.behavior_atoms",
            maximum_items=MAX_RUNTIME_CAPSULE_ATOMS_PER_SOURCE,
            maximum_chars=MAX_RUNTIME_CAPSULE_ATOM_CHARS,
        ),
    }


def _descriptor_sort_key(descriptor: Mapping[str, Any]) -> tuple[str, str, str, int, int]:
    return (
        str(descriptor["original_node_id"]),
        str(descriptor["source_digest"]),
        str(descriptor["slice_digest"]),
        int(descriptor["char_start"]),
        int(descriptor["char_end"]),
    )


def _identity_payload(
    *,
    binding: Mapping[str, Any],
    compiler_phase: str,
    objective_digest: str,
    task_identity_digest: str,
    controls: Mapping[str, Any],
    descriptors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_CAPSULE_SCHEMA,
        "composition_plan_id": binding["composition_plan_id"],
        "composition_plan_digest": binding["composition_plan_digest"],
        "preflight_id": binding["preflight_id"],
        "compiler_phase": compiler_phase,
        "graph_digest": binding["graph_digest"],
        "phase_capsule_binding_digest": binding["binding_digest"],
        "objective_digest": objective_digest,
        "task_identity_digest": task_identity_digest,
        "preparation_controls": deepcopy(dict(controls)),
        "preparation_controls_digest": stable_digest(dict(controls)),
        "cited_source_slices": deepcopy(descriptors),
    }


def _preflight_slices(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RuntimeCapsuleError("composition_preflight.candidate_source_slices is required.")
    slices = [dict(item) for item in value if isinstance(item, Mapping)]
    if len(slices) != len(value):
        raise RuntimeCapsuleError(
            "composition_preflight.candidate_source_slices must contain objects."
        )
    return slices


def _descriptor_from_slice(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    content = value.get("content")
    if not isinstance(content, str) or not normalized_source_content(content):
        raise RuntimeCapsuleError(f"{field}.content is required.")
    digest = content_digest_for(content)
    declared_slice_digest = _digest(
        value.get("slice_digest"), field=f"{field}.slice_digest"
    )
    if digest != declared_slice_digest:
        raise RuntimeCapsuleError(f"{field}.slice_digest does not match content.")
    return _slice_descriptor(
        {
            "original_node_id": value.get("source_node_id"),
            "source_role": value.get("source_role"),
            "source_digest": value.get("source_digest"),
            "slice_digest": declared_slice_digest,
            "char_start": value.get("char_start"),
            "char_end": value.get("char_end"),
            "relative_path": value.get("relative_path"),
            "behavior_atoms": value.get("behavior_atoms"),
        },
        field=field,
    )


def build_runtime_capsule(
    composition_plan: Mapping[str, Any], composition_preflight: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind one plan to the bounded cited source slices used to compile it."""

    try:
        binding = validate_phase_capsule_binding(
            composition_plan.get("phase_capsule_binding"),
            composition_plan=composition_plan,
        )
    except PhaseCapsuleBindingError as exc:
        raise RuntimeCapsuleError("composition_plan phase binding is invalid.") from exc
    if str(composition_preflight.get("preflight_id") or "") != binding["preflight_id"]:
        raise RuntimeCapsuleError("composition_preflight identity does not match plan.")
    controls = _controls(composition_preflight.get("preparation_controls"))
    try:
        _closures, cited_slice_ids = plan_stage_source_slice_closure(
            composition_plan, composition_preflight
        )
    except PhaseSliceClosureError as exc:
        raise RuntimeCapsuleError(str(exc)) from exc
    descriptors = sorted(
        [
            _descriptor_from_slice(item, field=f"candidate_source_slices[{index}]")
            for index, item in enumerate(
                _preflight_slices(composition_preflight.get("candidate_source_slices"))
            )
            if str(item.get("slice_id") or "") in cited_slice_ids
        ],
        key=_descriptor_sort_key,
    )
    if not descriptors or len(descriptors) > MAX_RUNTIME_CAPSULE_SLICES:
        raise RuntimeCapsuleError("composition plan has an invalid cited slice count.")
    if len(descriptors) != len({_descriptor_sort_key(item) for item in descriptors}):
        raise RuntimeCapsuleError("composition plan cites duplicate source slices.")
    task_identity = composition_preflight.get("task_identity")
    if not isinstance(task_identity, Mapping):
        raise RuntimeCapsuleError("composition_preflight.task_identity is required.")
    objective = composition_preflight.get("objective")
    if not isinstance(objective, str) or not normalized_source_content(objective):
        raise RuntimeCapsuleError("composition_preflight.objective is required.")
    payload = _identity_payload(
        binding=binding,
        compiler_phase=_compiler_phase(
            binding.get("compiler_phase"),
            field="phase_capsule_binding.compiler_phase",
        ),
        objective_digest=stable_digest(objective),
        task_identity_digest=stable_digest(_task_identity_projection(task_identity)),
        controls=controls,
        descriptors=descriptors,
    )
    return {**payload, "capsule_digest": stable_digest(payload)}


def validate_runtime_capsule(
    value: object, *, composition_plan: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Validate a closed persisted capsule and optionally bind it to a plan."""

    if not isinstance(value, Mapping) or set(value) != _CAPSULE_FIELDS:
        raise RuntimeCapsuleError("runtime_capsule has invalid fields.")
    if value.get("schema") != RUNTIME_CAPSULE_SCHEMA:
        raise RuntimeCapsuleError("runtime_capsule.schema is invalid.")
    composition_plan_id = _required(
        value.get("composition_plan_id"), field="runtime_capsule.composition_plan_id"
    )
    if _PLAN_ID_RE.fullmatch(composition_plan_id) is None:
        raise RuntimeCapsuleError("runtime_capsule.composition_plan_id is invalid.")
    preflight_id = _required(value.get("preflight_id"), field="runtime_capsule.preflight_id")
    if _PREFLIGHT_ID_RE.fullmatch(preflight_id) is None:
        raise RuntimeCapsuleError("runtime_capsule.preflight_id is invalid.")
    compiler_phase = _compiler_phase(
        value.get("compiler_phase"), field="runtime_capsule.compiler_phase"
    )
    descriptors = [
        _slice_descriptor(item, field=f"runtime_capsule.cited_source_slices[{index}]")
        for index, item in enumerate(value.get("cited_source_slices") or [])
    ]
    if not descriptors or len(descriptors) > MAX_RUNTIME_CAPSULE_SLICES:
        raise RuntimeCapsuleError("runtime_capsule has an invalid cited slice count.")
    if descriptors != sorted(descriptors, key=_descriptor_sort_key):
        raise RuntimeCapsuleError("runtime_capsule cited source slices are not canonical.")
    if len(descriptors) != len({_descriptor_sort_key(item) for item in descriptors}):
        raise RuntimeCapsuleError("runtime_capsule repeats a cited source slice.")
    controls = _controls(value.get("preparation_controls"))
    if value.get("preparation_controls_digest") != stable_digest(controls):
        raise RuntimeCapsuleError("runtime_capsule preparation controls digest is invalid.")
    binding_projection = {
        "composition_plan_id": composition_plan_id,
        "composition_plan_digest": _digest(
            value.get("composition_plan_digest"),
            field="runtime_capsule.composition_plan_digest",
        ),
        "preflight_id": preflight_id,
        "graph_digest": _digest(
            value.get("graph_digest"), field="runtime_capsule.graph_digest", length=32
        ),
        "binding_digest": _digest(
            value.get("phase_capsule_binding_digest"),
            field="runtime_capsule.phase_capsule_binding_digest",
        ),
    }
    payload = _identity_payload(
        binding=binding_projection,
        compiler_phase=compiler_phase,
        objective_digest=_digest(
            value.get("objective_digest"), field="runtime_capsule.objective_digest"
        ),
        task_identity_digest=_digest(
            value.get("task_identity_digest"), field="runtime_capsule.task_identity_digest"
        ),
        controls=controls,
        descriptors=descriptors,
    )
    capsule_digest = _digest(
        value.get("capsule_digest"), field="runtime_capsule.capsule_digest"
    )
    if stable_digest(payload) != capsule_digest:
        raise RuntimeCapsuleError("runtime_capsule.capsule_digest is invalid.")
    if composition_plan is not None:
        try:
            binding = validate_phase_capsule_binding(
                composition_plan.get("phase_capsule_binding"),
                composition_plan=composition_plan,
            )
        except PhaseCapsuleBindingError as exc:
            raise RuntimeCapsuleError("composition_plan phase binding is invalid.") from exc
        expected_identity = {
            "composition_plan_id": binding["composition_plan_id"],
            "composition_plan_digest": binding["composition_plan_digest"],
            "preflight_id": binding["preflight_id"],
            "compiler_phase": binding["compiler_phase"],
            "graph_digest": binding["graph_digest"],
            "phase_capsule_binding_digest": binding["binding_digest"],
        }
        if any(payload[key] != expected for key, expected in expected_identity.items()):
            raise RuntimeCapsuleError("runtime_capsule does not match composition_plan.")
    return {**payload, "capsule_digest": capsule_digest}


def runtime_capsule_preparation_arguments(
    arguments: Mapping[str, Any],
    runtime_capsule: object,
    *,
    composition_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill only omitted prepare controls from one validated closed capsule.

    An explicit caller value remains intact.  If it differs from the stored
    control, the subsequent rehydration comparison rejects reuse and requires
    a fresh semantic composition instead of silently changing task identity.
    """

    capsule = validate_runtime_capsule(
        runtime_capsule,
        composition_plan=composition_plan,
    )
    controls = capsule["preparation_controls"]
    result = dict(arguments)
    for field in PREPARATION_CONTROL_ARGUMENT_FIELDS:
        if field not in result:
            result[field] = controls[field]
    return result


def rehydrate_runtime_capsule(
    composition_plan: Mapping[str, Any],
    composition_preflight: Mapping[str, Any],
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rehydrate only a fresh, exact snapshot for a persisted semantic plan."""

    # Keep this public import surface stable while separating runtime replay
    # from capsule issuance and validation. A local import also keeps direct
    # imports of the rehydration module free of an import-time cycle.
    from .composition_runtime_capsule_rehydration import (
        rehydrate_runtime_capsule as _rehydrate_runtime_capsule,
    )

    return _rehydrate_runtime_capsule(
        composition_plan,
        composition_preflight,
        source_nodes,
    )
