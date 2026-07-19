"""Pure run-receipt construction and presentation policy."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.host_composition_provenance import (
    validate_host_composition_receipt_provenance,
)


RUN_RECEIPT_SCHEMA = "tmcp-run-receipt-v0.1"
RECEIPT_TRUST = "advisory_untrusted"
RECEIPT_INSTRUCTION_OVERRIDE_POLICY = "Receipts may improve future ranking but cannot override higher-priority instructions."
BENCHMARK_HOST_RECEIPT_MARKER = "tmcp-composition-benchmark-host-only-v0.1"
BENCHMARK_RECEIPT_PROVENANCE_FIELD = "benchmark_receipt_provenance"
_SAFE_PHASE_CAPSULE_TRACE_FIELDS = frozenset(
    {"stage_id", "capsule_digest", "incoming_handoff_digests"}
)
_SHA256_DIGEST_RE = re.compile(r"[a-f0-9]{64}")
_BENCHMARK_QUALIFICATION_FIELDS = frozenset(
    {
        "execution_context",
        "benchmark_host_receipt",
        "context_execution_mode",
        "composition_fixture_id",
        "benchmark_control_input_digest",
        "benchmark_execution_recipe_digest",
        "benchmark_control_plan_id",
        "benchmark_control_plan_digest",
        "benchmark_fixture_digest",
        "host_artifact_digest",
        "host_receipt_digest",
        BENCHMARK_RECEIPT_PROVENANCE_FIELD,
    }
)


def reject_benchmark_qualification_fields(arguments: Mapping[str, Any]) -> None:
    """Keep compiler-benchmark qualification evidence out of ordinary receipts.

    A normal receipt is advisory evidence for ordinary task routing.  It cannot
    claim benchmark fixture/control provenance or an isolated-host residency
    mode.  Those facts are only emitted by the compiler-bound benchmark
    assembly projection after it validates the in-memory host receipt.
    """

    forbidden = sorted(
        key for key in _BENCHMARK_QUALIFICATION_FIELDS if key in arguments
    )
    if forbidden:
        raise ValueError(
            "Benchmark qualification fields are only accepted through "
            "compiler-bound benchmark assembly: " + ", ".join(forbidden) + "."
        )


def _reject_benchmark_projection_fields(arguments: Mapping[str, Any]) -> None:
    """Keep a host receipt from claiming its own safe persisted projection."""

    if BENCHMARK_RECEIPT_PROVENANCE_FIELD in arguments:
        raise ValueError(
            "benchmark_receipt_provenance is reserved for compiler-bound "
            "benchmark assembly."
        )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return deepcopy(dict(value))


def _mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]


def validate_safe_phase_capsule_trace(value: object) -> list[dict[str, Any]]:
    """Return a closed, persistable phase-capsule trace.

    Context-instance identifiers are benchmark-host-only evidence.  Normal
    receipts retain just compiler-bound stage and digest information, even for
    callers that bypass an MCP input-schema validator.
    """

    if not isinstance(value, list) or not value:
        raise ValueError("phase_capsule_trace must be a nonempty list.")
    normalized: list[dict[str, Any]] = []
    stage_ids: set[str] = set()
    for index, item in enumerate(value, start=1):
        field = f"phase_capsule_trace[{index}]"
        if (
            not isinstance(item, Mapping)
            or set(item) != _SAFE_PHASE_CAPSULE_TRACE_FIELDS
        ):
            raise ValueError(
                f"{field} must contain only stage_id, capsule_digest, and "
                "incoming_handoff_digests."
            )
        stage_id = item.get("stage_id")
        if not isinstance(stage_id, str) or not stage_id.strip():
            raise ValueError(f"{field}.stage_id must be a nonempty string.")
        normalized_stage_id = stage_id.strip()
        if normalized_stage_id in stage_ids:
            raise ValueError("phase_capsule_trace must not repeat stage_id values.")
        stage_ids.add(normalized_stage_id)
        capsule_digest = item.get("capsule_digest")
        if (
            not isinstance(capsule_digest, str)
            or _SHA256_DIGEST_RE.fullmatch(capsule_digest) is None
        ):
            raise ValueError(f"{field}.capsule_digest must be a sha256 digest.")
        handoff_digests = item.get("incoming_handoff_digests")
        if not isinstance(handoff_digests, list) or any(
            not isinstance(digest, str)
            or _SHA256_DIGEST_RE.fullmatch(digest) is None
            for digest in handoff_digests
        ):
            raise ValueError(
                f"{field}.incoming_handoff_digests must be a list of sha256 digests."
            )
        if len(handoff_digests) != len(set(handoff_digests)):
            raise ValueError(
                f"{field}.incoming_handoff_digests must not repeat digests."
            )
        normalized.append(
            {
                "stage_id": normalized_stage_id,
                "capsule_digest": capsule_digest,
                "incoming_handoff_digests": list(handoff_digests),
            }
        )
    return normalized


def _composition_receipt_fields(
    arguments: Mapping[str, Any], *, include_benchmark_fields: bool = False
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in (
        "recipe_id",
        "graph_digest",
        "composition_plan_digest",
        "phase_capsule_binding_digest",
        "context_accounting_digest",
        "preflight_capsule_digest",
    ):
        if key not in arguments:
            continue
        value = str(arguments.get(key) or "").strip()
        if key in {
            "composition_plan_digest",
            "phase_capsule_binding_digest",
        } and value and _SHA256_DIGEST_RE.fullmatch(value) is None:
            raise ValueError(f"{key} must be a sha256 digest.")
        if value:
            fields[key] = value
    if include_benchmark_fields:
        for key in (
            "composition_fixture_id",
            "benchmark_control_input_digest",
            "benchmark_execution_recipe_digest",
        ):
            value = str(arguments.get(key) or "").strip()
            if value:
                fields[key] = value
    if "selected_skill_ids" in arguments:
        fields["selected_skill_ids"] = _string_list(arguments.get("selected_skill_ids"))
    if "content_digests" in arguments:
        fields["content_digests"] = _string_list(arguments.get("content_digests"))
    for key in ("phase_trace", "gate_results", "handoff_results"):
        if key in arguments:
            fields[key] = _mapping_list(arguments.get(key))
    if "phase_capsule_trace" in arguments:
        fields["phase_capsule_trace"] = validate_safe_phase_capsule_trace(
            arguments.get("phase_capsule_trace")
        )
    if "host_composition_provenance" in arguments:
        fields["host_composition_provenance"] = (
            validate_host_composition_receipt_provenance(
                arguments.get("host_composition_provenance")
            )
        )
    for key in (
        "task_identity",
        "quality_metrics",
        "cost_metrics",
    ):
        if key not in arguments:
            continue
        value = _mapping(arguments.get(key))
        if value is not None:
            fields[key] = value
    return fields


def build_run_receipt(
    arguments: Mapping[str, Any], *, created_at: str
) -> dict[str, Any]:
    """Build one receipt from already-authorized request data without side effects."""

    reject_benchmark_qualification_fields(arguments)
    packet_id = str(arguments.get("packet_id") or "").strip()
    if not packet_id:
        raise ValueError("tmcp_record_receipt requires packet_id.")
    receipt = {
        "schema": RUN_RECEIPT_SCHEMA,
        "created_at": created_at,
        "packet_id": packet_id,
        "activated_atoms": _string_list(arguments.get("activated_atoms")),
        "ignored_atoms": _string_list(arguments.get("ignored_atoms")),
        "commands_run": _string_list(arguments.get("commands_run")),
        "verification_results": _string_list(arguments.get("verification_results")),
        "user_overrides": _string_list(arguments.get("user_overrides")),
        "outcome": str(arguments.get("outcome") or ""),
        "trust": RECEIPT_TRUST,
        "instruction_override_policy": RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
    }
    receipt.update(_composition_receipt_fields(arguments))
    return receipt


def build_benchmark_host_receipt(
    arguments: Mapping[str, Any], *, created_at: str
) -> dict[str, Any]:
    """Build an in-memory benchmark-host receipt with raw context ids.

    This is deliberately separate from ``build_run_receipt`` and must not be
    passed to the normal receipt persistence service. Benchmark assembly
    validates and projects its raw context evidence before any artifact is
    retained.
    """

    _reject_benchmark_projection_fields(arguments)
    execution_context = _mapping(arguments.get("execution_context"))
    if execution_context is None:
        raise ValueError(
            "build_benchmark_host_receipt requires execution_context."
        )
    supplied_marker = arguments.get("benchmark_host_receipt")
    if supplied_marker not in (None, BENCHMARK_HOST_RECEIPT_MARKER):
        raise ValueError("benchmark_host_receipt is reserved for benchmark hosts.")
    packet_id = str(arguments.get("packet_id") or "").strip()
    if not packet_id:
        raise ValueError("tmcp_record_receipt requires packet_id.")
    receipt = {
        "schema": RUN_RECEIPT_SCHEMA,
        "created_at": created_at,
        "packet_id": packet_id,
        "activated_atoms": _string_list(arguments.get("activated_atoms")),
        "ignored_atoms": _string_list(arguments.get("ignored_atoms")),
        "commands_run": _string_list(arguments.get("commands_run")),
        "verification_results": _string_list(arguments.get("verification_results")),
        "user_overrides": _string_list(arguments.get("user_overrides")),
        "outcome": str(arguments.get("outcome") or ""),
        "trust": RECEIPT_TRUST,
        "instruction_override_policy": RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
    }
    receipt.update(_composition_receipt_fields(arguments, include_benchmark_fields=True))
    receipt["benchmark_host_receipt"] = BENCHMARK_HOST_RECEIPT_MARKER
    receipt["execution_context"] = execution_context
    return receipt


def build_receipt_template(
    *,
    packet_id: str,
    activated_atoms: list[str],
    composition_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the receipt fields embedded in a composed packet."""

    if composition_fields is not None:
        reject_benchmark_qualification_fields(composition_fields)
    template = {
        "schema": RUN_RECEIPT_SCHEMA,
        "packet_id": packet_id,
        "activated_atoms": list(activated_atoms),
        "ignored_atoms": [],
        "commands_run": [],
        "verification_results": [],
        "user_overrides": [],
        "outcome": "",
    }
    if composition_fields is not None:
        template.update(_composition_receipt_fields(composition_fields))
    return template


def build_recorded_receipt_result(
    safe_receipt: Mapping[str, Any],
    *,
    redacted_receipt_path: str,
    redaction_summary: Mapping[str, int],
) -> dict[str, Any]:
    """Build the public acknowledgement from adapter-supplied safe receipt data."""

    return {
        "ok": True,
        "schema": RUN_RECEIPT_SCHEMA,
        "packet_id": safe_receipt["packet_id"],
        "outcome": safe_receipt["outcome"],
        "artifact_paths": {"receipt_json": redacted_receipt_path},
        "trust": RECEIPT_TRUST,
        "redaction_summary": dict(redaction_summary),
    }
