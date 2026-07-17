"""Validate advisory host evidence for compiler-derived phase capsules."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.composition_benchmark_boundaries import (
    MAX_METADATA_CHARS,
    _bounded_text,
    _mapping_list,
    _nonempty,
    _string_list,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.composition_phase_capsules import (
    CONTEXT_ACCOUNTING_POLICY,
    CONTEXT_ACCOUNTING_SCHEMA,
)


EXECUTION_CONTEXT_SCHEMA = "tmcp-composition-benchmark-execution-context-v0.1"
CONTEXT_EXECUTION_MODES = frozenset(
    {"isolated_phase_capsule", "same_host_transcript"}
)
_DIGEST_RE = re.compile(r"[a-f0-9]{64}")


def _digest(value: object, *, field: str) -> str:
    result = _nonempty(value, field=field)
    if _DIGEST_RE.fullmatch(result) is None:
        raise ValueError(f"{field} must be a sha256 digest.")
    return result


def _expected_phase_capsules(accounting: Mapping[str, Any]) -> list[dict[str, Any]]:
    capsules = _mapping_list(
        accounting.get("phase_capsules"), field="context_accounting.phase_capsules"
    )
    if not capsules:
        raise ValueError("context_accounting.phase_capsules must not be empty.")
    expected: list[dict[str, Any]] = []
    for index, capsule in enumerate(capsules, start=1):
        expected.append(
            {
                "stage_id": _nonempty(
                    capsule.get("stage_id"),
                    field=f"context_accounting.phase_capsules[{index}].stage_id",
                ),
                "capsule_digest": _digest(
                    capsule.get("capsule_digest"),
                    field=(
                        "context_accounting.phase_capsules["
                        f"{index}].capsule_digest"
                    ),
                ),
                "incoming_handoff_digests": _string_list(
                    capsule.get("incoming_handoff_digests", []),
                    field=(
                        "context_accounting.phase_capsules["
                        f"{index}].incoming_handoff_digests"
                    ),
                    allow_empty=True,
                ),
            }
        )
    if len({item["stage_id"] for item in expected}) != len(expected):
        raise ValueError("context_accounting.phase_capsules repeats a stage.")
    return expected


def _validate_accounting_identity(accounting: Mapping[str, Any]) -> None:
    if accounting.get("schema") != CONTEXT_ACCOUNTING_SCHEMA:
        raise ValueError("context_accounting.schema is invalid.")
    if accounting.get("policy") != CONTEXT_ACCOUNTING_POLICY:
        raise ValueError("context_accounting.policy is invalid.")
    accounting_digest = _digest(
        accounting.get("context_accounting_digest"),
        field="context_accounting.context_accounting_digest",
    )
    identity = {
        key: value
        for key, value in accounting.items()
        if key not in {"context_accounting_digest", "context_digest"}
    }
    if stable_digest(identity) != accounting_digest:
        raise ValueError("context_accounting digest does not match its content.")
    if accounting.get("context_digest") != accounting_digest:
        raise ValueError("context_accounting compatibility digest is invalid.")


def validate_execution_context(
    execution_context: Mapping[str, Any],
    *,
    context_accounting: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an advisory isolation claim against compiler-derived capsules.

    The host supplies opaque context-instance identifiers only. They provide
    structural evidence of the claimed residency model, not authenticated
    proof that a model provider actually discarded prior context.
    """

    _validate_accounting_identity(context_accounting)
    expected_accounting_digest = str(context_accounting["context_accounting_digest"])
    expected_preflight_digest = _digest(
        context_accounting.get("preflight_capsule_digest"),
        field="context_accounting.preflight_capsule_digest",
    )
    expected_capsules = _expected_phase_capsules(context_accounting)
    required = {
        "schema",
        "execution_context_mode",
        "context_accounting_digest",
        "preflight_capsule_digest",
        "preflight_context_instance_id",
        "phase_capsule_trace",
    }
    observed = set(execution_context)
    missing = sorted(required.difference(observed))
    unexpected = sorted(observed.difference(required))
    if missing or unexpected:
        raise ValueError(
            "execution_context has invalid fields; "
            f"missing={missing}, unexpected={unexpected}."
        )
    if execution_context.get("schema") != EXECUTION_CONTEXT_SCHEMA:
        raise ValueError("execution_context.schema is invalid.")
    mode = _nonempty(
        execution_context.get("execution_context_mode"),
        field="execution_context.execution_context_mode",
    )
    if mode not in CONTEXT_EXECUTION_MODES:
        raise ValueError("execution_context.execution_context_mode is invalid.")
    if _digest(
        execution_context.get("context_accounting_digest"),
        field="execution_context.context_accounting_digest",
    ) != expected_accounting_digest:
        raise ValueError("execution_context does not bind compiler accounting.")
    if _digest(
        execution_context.get("preflight_capsule_digest"),
        field="execution_context.preflight_capsule_digest",
    ) != expected_preflight_digest:
        raise ValueError("execution_context preflight capsule does not match compiler.")
    preflight_instance_id = _bounded_text(
        execution_context.get("preflight_context_instance_id"),
        field="execution_context.preflight_context_instance_id",
        maximum=MAX_METADATA_CHARS,
    )
    trace = _mapping_list(
        execution_context.get("phase_capsule_trace"),
        field="execution_context.phase_capsule_trace",
    )
    if len(trace) != len(expected_capsules):
        raise ValueError("execution_context must cover each compiler phase capsule.")
    normalized_trace: list[dict[str, Any]] = []
    for index, (item, expected) in enumerate(
        zip(trace, expected_capsules, strict=True), start=1
    ):
        expected_fields = {
            "stage_id",
            "capsule_digest",
            "context_instance_id",
            "incoming_handoff_digests",
        }
        if set(item) != expected_fields:
            raise ValueError(
                "execution_context.phase_capsule_trace["
                f"{index}] has invalid fields."
            )
        stage_id = _nonempty(
            item.get("stage_id"),
            field=f"execution_context.phase_capsule_trace[{index}].stage_id",
        )
        if stage_id != expected["stage_id"]:
            raise ValueError("execution_context phase capsules are out of compiler order.")
        capsule_digest = _digest(
            item.get("capsule_digest"),
            field=f"execution_context.phase_capsule_trace[{index}].capsule_digest",
        )
        if capsule_digest != expected["capsule_digest"]:
            raise ValueError("execution_context phase capsule digest does not match compiler.")
        handoff_digests = _string_list(
            item.get("incoming_handoff_digests"),
            field=(
                "execution_context.phase_capsule_trace["
                f"{index}].incoming_handoff_digests"
            ),
            allow_empty=True,
        )
        if handoff_digests != expected["incoming_handoff_digests"]:
            raise ValueError("execution_context handoff inputs do not match compiler.")
        normalized_trace.append(
            {
                "stage_id": stage_id,
                "capsule_digest": capsule_digest,
                "context_instance_id": _bounded_text(
                    item.get("context_instance_id"),
                    field=(
                        "execution_context.phase_capsule_trace["
                        f"{index}].context_instance_id"
                    ),
                    maximum=MAX_METADATA_CHARS,
                ),
                "incoming_handoff_digests": handoff_digests,
            }
        )
    instance_ids = [preflight_instance_id] + [
        item["context_instance_id"] for item in normalized_trace
    ]
    if mode == "isolated_phase_capsule" and len(set(instance_ids)) != len(
        instance_ids
    ):
        raise ValueError("isolated phase capsules must use distinct context instances.")
    if mode == "same_host_transcript" and len(set(instance_ids)) != 1:
        raise ValueError("same-host transcript must use one context instance.")
    return {
        "execution_context_mode": mode,
        "context_accounting_digest": expected_accounting_digest,
        "preflight_capsule_digest": expected_preflight_digest,
        "phase_capsule_trace": [
            {
                key: value
                for key, value in item.items()
                if key != "context_instance_id"
            }
            for item in normalized_trace
        ],
        "qualified": mode == "isolated_phase_capsule",
        "evidence_trust": "advisory_untrusted",
    }


def validate_projected_execution_context(
    receipt: Mapping[str, Any],
    *,
    context_accounting: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the safe receipt projection without recovering host instance ids."""

    _validate_accounting_identity(context_accounting)
    expected_accounting_digest = str(context_accounting["context_accounting_digest"])
    expected_preflight_digest = _digest(
        context_accounting.get("preflight_capsule_digest"),
        field="context_accounting.preflight_capsule_digest",
    )
    expected_capsules = _expected_phase_capsules(context_accounting)
    mode = _nonempty(
        receipt.get("context_execution_mode"),
        field="run_receipt.context_execution_mode",
    )
    if mode not in CONTEXT_EXECUTION_MODES:
        raise ValueError("run_receipt.context_execution_mode is invalid.")
    if _digest(
        receipt.get("context_accounting_digest"),
        field="run_receipt.context_accounting_digest",
    ) != expected_accounting_digest:
        raise ValueError("run_receipt context accounting does not match compiler.")
    if _digest(
        receipt.get("preflight_capsule_digest"),
        field="run_receipt.preflight_capsule_digest",
    ) != expected_preflight_digest:
        raise ValueError("run_receipt preflight capsule does not match compiler.")
    trace = _mapping_list(
        receipt.get("phase_capsule_trace"),
        field="run_receipt.phase_capsule_trace",
    )
    expected_trace = [
        {
            "stage_id": capsule["stage_id"],
            "capsule_digest": capsule["capsule_digest"],
            "incoming_handoff_digests": capsule["incoming_handoff_digests"],
        }
        for capsule in expected_capsules
    ]
    if [dict(item) for item in trace] != expected_trace:
        raise ValueError("run_receipt phase capsule trace does not match compiler.")
    return {
        "execution_context_mode": mode,
        "qualified": mode == "isolated_phase_capsule",
    }


def execution_context_digest(execution_context: Mapping[str, Any]) -> str:
    """Return the stable identity of validated, safe execution-context evidence."""

    return stable_digest(dict(execution_context))
