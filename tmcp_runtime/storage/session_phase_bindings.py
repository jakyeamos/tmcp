"""Internal phase-binding persistence for protected packet sessions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.composition_phase_bindings import (
    PhaseCapsuleBindingError,
    validate_phase_capsule_binding,
)
from tmcp_runtime.domain.composition_runtime_capsules import (
    RUNTIME_CAPSULE_INVALID_PROVENANCE_STATUS,
    RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD,
    packet_has_runtime_capsule_provenance,
)
from tmcp_runtime.domain.composition_runtime_continuations import (
    restore_runtime_continuation,
    runtime_continuation_hash_paths,
)
from tmcp_runtime.storage.runtime_capsule_persistence import (
    restore_runtime_capsule,
    runtime_capsule_hash_paths,
)


_SHA256_DIGEST_PATTERN = re.compile(r"[a-f0-9]{64}")
_PHASE_STAGE_ID_PATTERN = re.compile(r"stage-[0-9]+")
_PHASE_BINDING_HASH_FIELDS = (
    "composition_plan_digest",
    "context_accounting_digest",
    "preflight_capsule_digest",
    "binding_digest",
)
_RECEIPT_BINDING_HASHES = (
    "composition_plan_digest",
    "phase_capsule_binding_digest",
    "context_accounting_digest",
    "preflight_capsule_digest",
)
_RECEIPT_PHASE_BINDING_FIELDS = (
    *_RECEIPT_BINDING_HASHES,
    "phase_capsule_trace",
)

SESSION_HASH_PATHS = (
    (
        "packet",
        "composition_plan",
        "provenance",
        "content_digests",
        "*",
    ),
    *(
        ("packet", "composition_plan", "phase_capsule_binding", field)
        for field in _PHASE_BINDING_HASH_FIELDS
    ),
    (
        "packet",
        "composition_plan",
        "phase_capsule_binding",
        "phase_capsule_trace",
        "*",
        "capsule_digest",
    ),
    (
        "packet",
        "composition_plan",
        "phase_capsule_binding",
        "phase_capsule_trace",
        "*",
        "incoming_handoff_digests",
        "*",
    ),
    *runtime_capsule_hash_paths(("packet", "composition_plan", "runtime_capsule")),
    *runtime_continuation_hash_paths(
        ("packet", "composition_plan", "runtime_continuation")
    ),
    *(
        ("packet", "receipt_template", field)
        for field in _RECEIPT_PHASE_BINDING_FIELDS
        if field != "phase_capsule_trace"
    ),
    (
        "packet",
        "receipt_template",
        "phase_capsule_trace",
        "*",
        "capsule_digest",
    ),
    (
        "packet",
        "receipt_template",
        "phase_capsule_trace",
        "*",
        "incoming_handoff_digests",
        "*",
    ),
)


def _preserved_sha256(
    value: object,
    *,
    path: tuple[str | int, ...],
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> object:
    """Use an allowlisted literal captured in the protected JSON read.

    ``read_json_input`` returns only exact 64-character lowercase SHA-256
    values for requested paths.  Keeping this helper local prevents a session
    restore from becoming a generic high-entropy-value bypass.
    """

    if literals is None:
        return value
    restored = literals.get(path)
    if restored is None or _SHA256_DIGEST_PATTERN.fullmatch(restored) is None:
        return value
    return restored


def _with_preserved_phase_hashes(
    value: Mapping[str, Any],
    *,
    base_path: tuple[str | int, ...],
    hash_fields: tuple[str, ...],
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> dict[str, Any]:
    """Return a closed phase projection with only approved hashes restored."""

    candidate = deepcopy(dict(value))
    for field in hash_fields:
        candidate[field] = _preserved_sha256(
            candidate.get(field),
            path=(*base_path, field),
            literals=literals,
        )
    trace = candidate.get("phase_capsule_trace")
    if not isinstance(trace, list):
        return candidate
    for index, stage in enumerate(trace):
        if not isinstance(stage, dict):
            continue
        stage_path = (*base_path, "phase_capsule_trace", index)
        stage["capsule_digest"] = _preserved_sha256(
            stage.get("capsule_digest"),
            path=(*stage_path, "capsule_digest"),
            literals=literals,
        )
        handoffs = stage.get("incoming_handoff_digests")
        if not isinstance(handoffs, list):
            continue
        stage["incoming_handoff_digests"] = [
            _preserved_sha256(
                value,
                path=(*stage_path, "incoming_handoff_digests", handoff_index),
                literals=literals,
            )
            for handoff_index, value in enumerate(handoffs)
        ]
    return candidate


def _restore_plan_content_digests(
    source_packet: Mapping[str, Any],
    safe_plan: dict[str, Any],
    *,
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> None:
    """Restore the closed provenance digest list needed by the graph binding.

    These values are the plan's declared SHA-256 source-content identities, not
    source text.  They are restored only at their fixed schema path and are
    subsequently checked by ``validate_phase_capsule_binding`` against the
    compiler-issued plan identity.  No arbitrary redacted value is reinstated.
    """

    source_plan = source_packet.get("composition_plan")
    if not isinstance(source_plan, Mapping):
        return
    source_provenance = source_plan.get("provenance")
    safe_provenance = safe_plan.get("provenance")
    if not isinstance(source_provenance, Mapping) or not isinstance(
        safe_provenance, dict
    ):
        return
    source_digests = source_provenance.get("content_digests")
    safe_digests = safe_provenance.get("content_digests")
    if (
        not isinstance(source_digests, list)
        or not isinstance(safe_digests, list)
        or len(source_digests) != len(safe_digests)
    ):
        return
    restored: list[object] = []
    for index, digest in enumerate(source_digests):
        value = _preserved_sha256(
            digest,
            path=(
                "packet",
                "composition_plan",
                "provenance",
                "content_digests",
                index,
            ),
            literals=literals,
        )
        if not isinstance(value, str) or _SHA256_DIGEST_PATTERN.fullmatch(value) is None:
            return
        restored.append(value)
    safe_provenance["content_digests"] = restored


def _phase_binding_projections(
    packet: Mapping[str, Any],
    *,
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Validate the only compiler-bound fields a session may restore."""

    plan = packet.get("composition_plan")
    if not isinstance(plan, Mapping):
        return None, None, None
    raw_binding = plan.get("phase_capsule_binding")
    if not isinstance(raw_binding, Mapping):
        return None, None, None
    binding_candidate = _with_preserved_phase_hashes(
        raw_binding,
        base_path=("packet", "composition_plan", "phase_capsule_binding"),
        hash_fields=_PHASE_BINDING_HASH_FIELDS,
        literals=literals,
    )
    try:
        binding = validate_phase_capsule_binding(
            binding_candidate,
            composition_plan=plan,
        )
    except PhaseCapsuleBindingError:
        return None, None, None
    raw_stages = plan.get("ordered_stages")
    if not isinstance(raw_stages, list):
        return None, None, None
    expected_stage_ids: list[str] = []
    for stage in raw_stages:
        if not isinstance(stage, Mapping):
            return None, None, None
        stage_id = stage.get("stage_id")
        if (
            not isinstance(stage_id, str)
            or _PHASE_STAGE_ID_PATTERN.fullmatch(stage_id) is None
        ):
            return None, None, None
        expected_stage_ids.append(stage_id)
    if [item["stage_id"] for item in binding["phase_capsule_trace"]] != expected_stage_ids:
        return None, None, None
    plan_with_binding = dict(plan)
    plan_with_binding["phase_capsule_binding"] = binding
    capsule = restore_runtime_capsule(
        plan_with_binding,
        binding,
        prefix=("packet", "composition_plan", "runtime_capsule"),
        literals=literals,
        composition_plan=plan_with_binding,
    )
    receipt = packet.get("receipt_template")
    if not isinstance(receipt, Mapping):
        return binding, capsule, None
    receipt_candidate = _with_preserved_phase_hashes(
        receipt,
        base_path=("packet", "receipt_template"),
        hash_fields=_RECEIPT_BINDING_HASHES,
        literals=literals,
    )
    expected_receipt = {
        "composition_plan_digest": binding["composition_plan_digest"],
        "phase_capsule_binding_digest": binding["binding_digest"],
        "context_accounting_digest": binding["context_accounting_digest"],
        "preflight_capsule_digest": binding["preflight_capsule_digest"],
        "phase_capsule_trace": deepcopy(binding["phase_capsule_trace"]),
    }
    if all(
        receipt_candidate.get(field) == value
        for field, value in expected_receipt.items()
    ):
        return binding, capsule, expected_receipt
    return binding, capsule, None


def restore_session_phase_binding_fields(
    source_packet: Mapping[str, Any],
    safe_record: dict[str, Any],
    *,
    literals: Mapping[tuple[str | int, ...], str] | None = None,
) -> None:
    """Restore verified phase identities after generic sensitive-text redaction.

    Session persistence intentionally keeps the ordinary redactor as the
    default.  The narrow exception here is a compiler-issued phase binding:
    it has a closed schema, is revalidated, and contains only IDs, SHA-256
    identities, and the safe stage trace.  Source prose, unapproved hashes,
    and benchmark host context are never copied back.
    """

    source_has_capsule_provenance = packet_has_runtime_capsule_provenance(
        source_packet
    )
    safe_packet = safe_record.get("packet")
    if not isinstance(safe_packet, dict):
        return
    safe_plan = safe_packet.get("composition_plan")
    if isinstance(safe_plan, dict):
        _restore_plan_content_digests(
            source_packet,
            safe_plan,
            literals=literals,
        )
    binding, capsule, receipt_fields = _phase_binding_projections(
        source_packet,
        literals=literals,
    )
    continuation = None
    source_plan = source_packet.get("composition_plan")
    if (
        binding is not None
        and capsule is not None
        and isinstance(source_plan, Mapping)
    ):
        source_plan_with_capsules = dict(source_plan)
        source_plan_with_capsules["phase_capsule_binding"] = binding
        source_plan_with_capsules["runtime_capsule"] = capsule
        continuation = restore_runtime_continuation(
            source_plan,
            composition_plan=source_plan_with_capsules,
            prefix=("packet", "composition_plan", "runtime_continuation"),
            literals=literals,
        )
    safe_packet.pop("execution_context", None)
    safe_packet.pop("benchmark_host_receipt", None)
    safe_packet.pop("composition_preflight", None)
    safe_packet.pop("runtime_preflight", None)
    safe_packet.pop("source_nodes", None)
    safe_packet.pop(RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD, None)
    if isinstance(safe_plan, dict):
        safe_plan.pop("phase_capsule_binding", None)
        safe_plan.pop("runtime_capsule", None)
        safe_plan.pop("composition_preflight", None)
        safe_plan.pop("runtime_preflight", None)
        safe_plan.pop("source_nodes", None)
        safe_plan.pop("execution_context", None)
        safe_plan.pop("runtime_continuation", None)
    safe_receipt = safe_packet.get("receipt_template")
    if isinstance(safe_receipt, dict):
        safe_receipt.pop("execution_context", None)
        safe_receipt.pop("benchmark_host_receipt", None)
        for field in _RECEIPT_PHASE_BINDING_FIELDS:
            safe_receipt.pop(field, None)
    if binding is not None and isinstance(safe_plan, dict):
        safe_plan["phase_capsule_binding"] = binding
    if capsule is not None and isinstance(safe_plan, dict):
        safe_plan["runtime_capsule"] = capsule
    if continuation is not None and isinstance(safe_plan, dict):
        safe_plan["runtime_continuation"] = continuation
    if receipt_fields is not None and isinstance(safe_receipt, dict):
        safe_receipt.update(receipt_fields)
    if source_has_capsule_provenance and (binding is None or capsule is None):
        safe_packet[RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD] = (
            RUNTIME_CAPSULE_INVALID_PROVENANCE_STATUS
        )
