"""Persistable compiler bindings for phase-capsule receipt evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .composition_phase_capsules import build_phase_capsule_accounting
from .composition_phase_slice_closures import (
    PhaseSliceClosureError,
    plan_stage_source_slice_closure,
)
from .composition_preflight import stable_digest
from .harvest_nodes import content_digest_for
from .receipts import validate_safe_phase_capsule_trace


PHASE_CAPSULE_BINDING_SCHEMA = "tmcp-composition-phase-capsule-binding-v0.1"

_DIGEST_32_RE = re.compile(r"[a-f0-9]{32}")
_DIGEST_64_RE = re.compile(r"[a-f0-9]{64}")
_PLAN_ID_RE = re.compile(r"composition-[a-f0-9]{20}")
_PREFLIGHT_ID_RE = re.compile(r"preflight-[a-f0-9]{20}")
_BINDING_FIELDS = frozenset(
    {
        "schema",
        "composition_plan_id",
        "composition_plan_digest",
        "preflight_id",
        "graph_digest",
        "recipe_digest",
        "context_accounting_digest",
        "preflight_capsule_digest",
        "phase_capsule_trace",
        "binding_digest",
    }
)
_PLAN_BINDING_FIELDS = (
    "schema",
    "composition_plan_id",
    "preflight_id",
    "current_phase",
    "governing_node_ids",
    "task_model",
    "skill_roles",
    "typed_edges",
    "handoff_contracts",
    "scoped_seed_graph_hints",
    "ordered_stages",
    "coverage",
    "provenance",
    "trust",
    "instruction_override_policy",
)


class PhaseCapsuleBindingError(ValueError):
    """Raised when compiler-issued capsule evidence cannot be bound safely."""


def _required(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise PhaseCapsuleBindingError(f"{field} is required.")
    return result


def _digest(value: object, *, field: str, length: int) -> str:
    result = _required(value, field=field)
    pattern = _DIGEST_32_RE if length == 32 else _DIGEST_64_RE
    if pattern.fullmatch(result) is None:
        raise PhaseCapsuleBindingError(f"{field} must be a sha256 digest.")
    return result


def _composition_plan_digest(plan: Mapping[str, Any]) -> str:
    """Return stable executable-plan identity without mutable diagnostics."""

    try:
        return stable_digest(
            {field: plan.get(field) for field in _PLAN_BINDING_FIELDS if field in plan}
        )
    except (TypeError, ValueError) as exc:
        raise PhaseCapsuleBindingError(
            "composition_plan cannot be canonically bound."
        ) from exc


def _plan_identity(plan: Mapping[str, Any]) -> dict[str, str]:
    provenance = plan.get("provenance")
    if not isinstance(provenance, Mapping):
        raise PhaseCapsuleBindingError("composition_plan.provenance is required.")
    composition_plan_id = _required(
        plan.get("composition_plan_id"),
        field="composition_plan.composition_plan_id",
    )
    if _PLAN_ID_RE.fullmatch(composition_plan_id) is None:
        raise PhaseCapsuleBindingError("composition_plan.composition_plan_id is invalid.")
    preflight_id = _required(plan.get("preflight_id"), field="composition_plan.preflight_id")
    if _PREFLIGHT_ID_RE.fullmatch(preflight_id) is None:
        raise PhaseCapsuleBindingError("composition_plan.preflight_id is invalid.")
    return {
        "composition_plan_id": composition_plan_id,
        "composition_plan_digest": _composition_plan_digest(plan),
        "preflight_id": preflight_id,
        "graph_digest": _digest(
            provenance.get("graph_digest"),
            field="composition_plan.provenance.graph_digest",
            length=32,
        ),
        "recipe_digest": _digest(
            provenance.get("recipe_digest"),
            field="composition_plan.provenance.recipe_digest",
            length=32,
        ),
    }


def _normalized_accounting_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize hydrated candidate slice content before binding it."""

    normalized = deepcopy(dict(preflight))
    raw_slices = normalized.get("candidate_source_slices")
    if not isinstance(raw_slices, list):
        raise PhaseCapsuleBindingError(
            "composition_preflight.candidate_source_slices must be a list."
        )
    slices: list[dict[str, Any]] = []
    for index, raw_slice in enumerate(raw_slices, start=1):
        if not isinstance(raw_slice, Mapping):
            raise PhaseCapsuleBindingError(
                "composition_preflight.candidate_source_slices must contain objects."
            )
        item = dict(raw_slice)
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise PhaseCapsuleBindingError(
                "composition_preflight.candidate_source_slices["
                f"{index}].content is required."
            )
        item["slice_digest"] = content_digest_for(content)
        slices.append(item)
    normalized["candidate_source_slices"] = slices
    return normalized


def _source_contents_from_preflight(
    preflight: Mapping[str, Any], *, cited_slice_ids: set[str]
) -> list[dict[str, Any]]:
    raw_slices = preflight.get("candidate_source_slices")
    if not isinstance(raw_slices, Sequence) or isinstance(raw_slices, (str, bytes)):
        raise PhaseCapsuleBindingError(
            "composition_preflight.candidate_source_slices must be a list."
        )
    source_contents: list[dict[str, Any]] = []
    available_slice_ids: set[str] = set()
    for index, raw_slice in enumerate(raw_slices, start=1):
        if not isinstance(raw_slice, Mapping):
            raise PhaseCapsuleBindingError(
                "composition_preflight.candidate_source_slices must contain objects."
            )
        field = f"composition_preflight.candidate_source_slices[{index}]"
        node_id = _required(raw_slice.get("source_node_id"), field=f"{field}.source_node_id")
        slice_id = _required(raw_slice.get("slice_id"), field=f"{field}.slice_id")
        available_slice_ids.add(slice_id)
        if slice_id not in cited_slice_ids:
            continue
        content = raw_slice.get("content")
        if not isinstance(content, str) or not content.strip():
            raise PhaseCapsuleBindingError(f"{field}.content is required.")
        source_contents.append(
            {
                "skill_id": node_id,
                "source_node_id": node_id,
                "source_slice_id": slice_id,
                "source_role": str(raw_slice.get("source_role") or "active_skill"),
                "source_digest": str(raw_slice.get("source_digest") or ""),
                "slice_digest": str(raw_slice.get("slice_digest") or ""),
                "content": content,
                "char_start": raw_slice.get("char_start", 0),
                "char_end": raw_slice.get("char_end", len(content)),
            }
        )
    if not source_contents:
        raise PhaseCapsuleBindingError(
            "composition_preflight has no cited runtime source slices."
        )
    missing = sorted(cited_slice_ids.difference(available_slice_ids))
    if missing:
        raise PhaseCapsuleBindingError(
            f"composition_preflight is missing cited source slices: {missing}."
        )
    return sorted(
        source_contents,
        key=lambda item: (
            str(item["source_node_id"]),
            int(item["char_start"]),
            int(item["char_end"]),
            str(item["source_slice_id"]),
        ),
    )


def _accounting_projection(
    plan: Mapping[str, Any],
    *,
    identity: Mapping[str, str],
    stage_source_slice_ids: Mapping[str, Mapping[str, Sequence[str]]],
) -> dict[str, Any]:
    stages = plan.get("ordered_stages")
    task_model = plan.get("task_model")
    handoff_contracts = plan.get("handoff_contracts") or []
    if not isinstance(stages, list) or not stages:
        raise PhaseCapsuleBindingError("composition_plan.ordered_stages is required.")
    if not isinstance(task_model, Mapping):
        raise PhaseCapsuleBindingError("composition_plan.task_model is required.")
    if not isinstance(handoff_contracts, list):
        raise PhaseCapsuleBindingError("composition_plan.handoff_contracts is invalid.")
    return {
        "task_model": dict(task_model),
        "source_projection": {
            "composition_plan_id": identity["composition_plan_id"],
            "composition_plan_digest": identity["composition_plan_digest"],
            "graph_digest": identity["graph_digest"],
            "stages": deepcopy(stages),
            "handoff_contracts": deepcopy(handoff_contracts),
            "stage_source_slice_ids": {
                str(stage_id): {
                    str(node_id): list(slice_ids)
                    for node_id, slice_ids in sorted(source_map.items())
                }
                for stage_id, source_map in sorted(stage_source_slice_ids.items())
            },
        },
    }


def _runtime_envelope(preflight: Mapping[str, Any]) -> dict[str, Any]:
    task_identity = preflight.get("task_identity")
    if not isinstance(task_identity, Mapping):
        raise PhaseCapsuleBindingError(
            "composition_preflight.task_identity is required for phase binding."
        )
    return {
        "schema": "tmcp-composition-phase-runtime-envelope-v0.1",
        "objective": _required(
            preflight.get("objective"), field="composition_preflight.objective"
        ),
        "task_identity": dict(task_identity),
        "cache_policy": "none",
    }


def _binding_payload(
    *,
    identity: Mapping[str, str],
    context_accounting_digest: str,
    preflight_capsule_digest: str,
    phase_capsule_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": PHASE_CAPSULE_BINDING_SCHEMA,
        "composition_plan_id": identity["composition_plan_id"],
        "composition_plan_digest": identity["composition_plan_digest"],
        "preflight_id": identity["preflight_id"],
        "graph_digest": identity["graph_digest"],
        "recipe_digest": identity["recipe_digest"],
        "context_accounting_digest": context_accounting_digest,
        "preflight_capsule_digest": preflight_capsule_digest,
        "phase_capsule_trace": deepcopy(phase_capsule_trace),
    }


def build_phase_capsule_binding(
    composition_plan: Mapping[str, Any], composition_preflight: Mapping[str, Any]
) -> dict[str, Any]:
    """Build safe compiler evidence while hydrated source slices are available."""

    if not isinstance(composition_plan, Mapping):
        raise PhaseCapsuleBindingError("composition_plan must be an object.")
    if not isinstance(composition_preflight, Mapping):
        raise PhaseCapsuleBindingError("composition_preflight must be an object.")
    identity = _plan_identity(composition_plan)
    preflight_id = _required(
        composition_preflight.get("preflight_id"),
        field="composition_preflight.preflight_id",
    )
    if preflight_id != identity["preflight_id"]:
        raise PhaseCapsuleBindingError(
            "composition_preflight.preflight_id does not match composition_plan."
        )
    accounting_preflight = _normalized_accounting_preflight(composition_preflight)
    try:
        stage_source_slice_ids, cited_slice_ids = plan_stage_source_slice_closure(
            composition_plan, accounting_preflight
        )
    except PhaseSliceClosureError as exc:
        raise PhaseCapsuleBindingError(str(exc)) from exc
    projection = _accounting_projection(
        composition_plan,
        identity=identity,
        stage_source_slice_ids=stage_source_slice_ids,
    )
    try:
        accounting = build_phase_capsule_accounting(
            task_model=projection["task_model"],
            preflight=accounting_preflight,
            source_projection=projection["source_projection"],
            source_contents=_source_contents_from_preflight(
                accounting_preflight, cited_slice_ids=cited_slice_ids
            ),
            runtime_envelope=_runtime_envelope(accounting_preflight),
        )
    except ValueError as exc:
        raise PhaseCapsuleBindingError(
            f"Could not compile phase-capsule binding: {exc}"
        ) from exc
    phase_capsules = accounting.get("phase_capsules")
    if not isinstance(phase_capsules, list):
        raise PhaseCapsuleBindingError("Compiler phase accounting is malformed.")
    trace = validate_safe_phase_capsule_trace(
        [
            {
                "stage_id": item.get("stage_id"),
                "capsule_digest": item.get("capsule_digest"),
                "incoming_handoff_digests": item.get("incoming_handoff_digests", []),
            }
            for item in phase_capsules
            if isinstance(item, Mapping)
        ]
    )
    if len(trace) != len(phase_capsules):
        raise PhaseCapsuleBindingError("Compiler phase accounting is malformed.")
    payload = _binding_payload(
        identity=identity,
        context_accounting_digest=_digest(
            accounting.get("context_accounting_digest"),
            field="context_accounting.context_accounting_digest",
            length=64,
        ),
        preflight_capsule_digest=_digest(
            accounting.get("preflight_capsule_digest"),
            field="context_accounting.preflight_capsule_digest",
            length=64,
        ),
        phase_capsule_trace=trace,
    )
    return {**payload, "binding_digest": stable_digest(payload)}


def validate_phase_capsule_binding(
    value: object, *, composition_plan: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Validate a stored safe binding and, optionally, its plan identity."""

    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise PhaseCapsuleBindingError("phase_capsule_binding has invalid fields.")
    if value.get("schema") != PHASE_CAPSULE_BINDING_SCHEMA:
        raise PhaseCapsuleBindingError("phase_capsule_binding.schema is invalid.")
    binding = dict(value)
    identity = {
        "composition_plan_id": _required(
            binding.get("composition_plan_id"),
            field="phase_capsule_binding.composition_plan_id",
        ),
        "composition_plan_digest": _digest(
            binding.get("composition_plan_digest"),
            field="phase_capsule_binding.composition_plan_digest",
            length=64,
        ),
        "preflight_id": _required(
            binding.get("preflight_id"), field="phase_capsule_binding.preflight_id"
        ),
        "graph_digest": _digest(
            binding.get("graph_digest"),
            field="phase_capsule_binding.graph_digest",
            length=32,
        ),
        "recipe_digest": _digest(
            binding.get("recipe_digest"),
            field="phase_capsule_binding.recipe_digest",
            length=32,
        ),
    }
    if _PLAN_ID_RE.fullmatch(identity["composition_plan_id"]) is None:
        raise PhaseCapsuleBindingError("phase_capsule_binding.composition_plan_id is invalid.")
    if _PREFLIGHT_ID_RE.fullmatch(identity["preflight_id"]) is None:
        raise PhaseCapsuleBindingError("phase_capsule_binding.preflight_id is invalid.")
    trace = validate_safe_phase_capsule_trace(binding.get("phase_capsule_trace"))
    payload = _binding_payload(
        identity=identity,
        context_accounting_digest=_digest(
            binding.get("context_accounting_digest"),
            field="phase_capsule_binding.context_accounting_digest",
            length=64,
        ),
        preflight_capsule_digest=_digest(
            binding.get("preflight_capsule_digest"),
            field="phase_capsule_binding.preflight_capsule_digest",
            length=64,
        ),
        phase_capsule_trace=trace,
    )
    binding_digest = _digest(
        binding.get("binding_digest"),
        field="phase_capsule_binding.binding_digest",
        length=64,
    )
    if stable_digest(payload) != binding_digest:
        raise PhaseCapsuleBindingError(
            "phase_capsule_binding.binding_digest does not match its content."
        )
    if composition_plan is not None and identity != _plan_identity(composition_plan):
        raise PhaseCapsuleBindingError(
            "phase_capsule_binding does not match composition_plan identity."
        )
    return {**payload, "binding_digest": binding_digest}


def receipt_matches_phase_capsule_binding(
    receipt: Mapping[str, Any], binding: Mapping[str, Any]
) -> bool:
    """Return whether a safe receipt projection exactly matches a binding."""

    try:
        expected = validate_phase_capsule_binding(binding)
        observed_trace = validate_safe_phase_capsule_trace(
            receipt.get("phase_capsule_trace")
        )
    except (PhaseCapsuleBindingError, ValueError):
        return False
    return (
        receipt.get("phase_capsule_binding_digest") == expected["binding_digest"]
        and receipt.get("composition_plan_digest")
        == expected["composition_plan_digest"]
        and receipt.get("context_accounting_digest")
        == expected["context_accounting_digest"]
        and receipt.get("preflight_capsule_digest")
        == expected["preflight_capsule_digest"]
        and observed_trace == expected["phase_capsule_trace"]
    )
