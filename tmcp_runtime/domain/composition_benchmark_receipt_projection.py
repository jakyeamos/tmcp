"""Safe benchmark receipt projections and their advisory provenance bindings."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.composition_benchmark_boundaries import _finite_number
from tmcp_runtime.domain.composition_benchmark_projection import (
    _receipt_quality_metrics,
)
from tmcp_runtime.domain.composition_phase_bindings import (
    PhaseCapsuleBindingError,
    validate_phase_capsule_binding,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.receipts import (
    BENCHMARK_RECEIPT_PROVENANCE_FIELD,
    RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
    RECEIPT_TRUST,
)


BENCHMARK_RECEIPT_PROVENANCE_SCHEMA = (
    "tmcp-composition-benchmark-receipt-provenance-v0.1"
)
_PROVENANCE_FIELDS = frozenset(
    {
        "schema",
        "provenance_id",
        "fixture_id",
        "fixture_digest",
        "control_plan_id",
        "control_plan_digest",
        "composition_plan_id",
        "composition_plan_digest",
        "phase_capsule_binding_digest",
        "graph_digest",
        "control_input_digest",
        "execution_recipe_digest",
        "context_execution_mode",
        "host_artifact_digest",
        "host_receipt_digest",
        "receipt_projection_digest",
        "evidence_trust",
        "provenance_digest",
    }
)
_PROVENANCE_ID_RE = re.compile(r"benchmark-receipt-[a-f0-9]{20}")
_CONTROL_PLAN_ID_RE = re.compile(r"benchmark-control-[a-f0-9]{20}")
_COMPOSITION_PLAN_ID_RE = re.compile(r"composition-[a-f0-9]{20}")
_DIGEST_RE = re.compile(r"[a-f0-9]{64}")
_GRAPH_DIGEST_RE = re.compile(r"[a-f0-9]{32}")
_CONTEXT_EXECUTION_MODES = frozenset(
    {"isolated_phase_capsule", "same_host_transcript"}
)
_RAW_HOST_ONLY_FIELDS = frozenset(
    {
        "execution_context",
        "benchmark_host_receipt",
        "host_artifact_digest",
        "host_receipt_digest",
    }
)


def _nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string.")
    return value.strip()


def _digest(value: object, *, field: str, graph: bool = False) -> str:
    result = _nonempty(value, field=field)
    pattern = _GRAPH_DIGEST_RE if graph else _DIGEST_RE
    if pattern.fullmatch(result) is None:
        raise ValueError(f"{field} must be a sha256 digest.")
    return result


def _receipt_projection_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact safe receipt payload that a provenance digest binds."""

    return {
        str(key): deepcopy(value)
        for key, value in receipt.items()
        if key != BENCHMARK_RECEIPT_PROVENANCE_FIELD
    }


def _provenance_payload(provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(provenance[key])
        for key in sorted(_PROVENANCE_FIELDS - {"provenance_id", "provenance_digest"})
    }


def build_benchmark_receipt_provenance(
    receipt_projection: Mapping[str, Any],
    *,
    fixture_digest: str,
    control_plan_id: str,
    control_plan_digest: str,
    host_artifact_digest: str,
    host_receipt_digest: str,
) -> dict[str, Any]:
    """Build the closed advisory provenance for one safe benchmark receipt.

    This deliberately binds only digests, IDs, and the safe projected receipt.
    It never carries host context-instance identifiers or raw host artifacts.
    The binding proves deterministic consistency of supplied evidence, not
    cryptographic origin or actual provider-side context isolation.
    """

    if not isinstance(receipt_projection, Mapping):
        raise ValueError("receipt_projection must be an object.")
    if BENCHMARK_RECEIPT_PROVENANCE_FIELD in receipt_projection:
        raise ValueError("receipt_projection must not already contain provenance.")
    forbidden = sorted(_RAW_HOST_ONLY_FIELDS.intersection(receipt_projection))
    if forbidden:
        raise ValueError(
            "receipt_projection must not contain raw host-only fields: "
            + ", ".join(forbidden)
            + "."
        )
    mode = _nonempty(
        receipt_projection.get("context_execution_mode"),
        field="receipt_projection.context_execution_mode",
    )
    if mode not in _CONTEXT_EXECUTION_MODES:
        raise ValueError("receipt_projection.context_execution_mode is invalid.")
    composition_plan_id = _nonempty(
        receipt_projection.get("recipe_id"), field="receipt_projection.recipe_id"
    )
    if _COMPOSITION_PLAN_ID_RE.fullmatch(composition_plan_id) is None:
        raise ValueError("receipt_projection.recipe_id is not a composition plan id.")
    payload: dict[str, Any] = {
        "schema": BENCHMARK_RECEIPT_PROVENANCE_SCHEMA,
        "fixture_id": _nonempty(
            receipt_projection.get("composition_fixture_id"),
            field="receipt_projection.composition_fixture_id",
        ),
        "fixture_digest": _digest(fixture_digest, field="fixture_digest"),
        "control_plan_id": _nonempty(control_plan_id, field="control_plan_id"),
        "control_plan_digest": _digest(
            control_plan_digest, field="control_plan_digest"
        ),
        "composition_plan_id": composition_plan_id,
        "composition_plan_digest": _digest(
            receipt_projection.get("composition_plan_digest"),
            field="receipt_projection.composition_plan_digest",
        ),
        "phase_capsule_binding_digest": _digest(
            receipt_projection.get("phase_capsule_binding_digest"),
            field="receipt_projection.phase_capsule_binding_digest",
        ),
        "graph_digest": _digest(
            receipt_projection.get("graph_digest"),
            field="receipt_projection.graph_digest",
            graph=True,
        ),
        "control_input_digest": _digest(
            receipt_projection.get("benchmark_control_input_digest"),
            field="receipt_projection.benchmark_control_input_digest",
        ),
        "execution_recipe_digest": _digest(
            receipt_projection.get("benchmark_execution_recipe_digest"),
            field="receipt_projection.benchmark_execution_recipe_digest",
        ),
        "context_execution_mode": mode,
        "host_artifact_digest": _digest(
            host_artifact_digest, field="host_artifact_digest"
        ),
        "host_receipt_digest": _digest(
            host_receipt_digest, field="host_receipt_digest"
        ),
        "receipt_projection_digest": stable_digest(
            _receipt_projection_payload(receipt_projection)
        ),
        "evidence_trust": RECEIPT_TRUST,
    }
    if _CONTROL_PLAN_ID_RE.fullmatch(payload["control_plan_id"]) is None:
        raise ValueError("control_plan_id is invalid.")
    provenance_digest = stable_digest(payload)
    return {
        **payload,
        "provenance_id": "benchmark-receipt-" + provenance_digest[:20],
        "provenance_digest": provenance_digest,
    }


def validate_benchmark_receipt_provenance(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a safe receipt's closed, self-consistent provenance projection."""

    if not isinstance(receipt, Mapping):
        raise ValueError("benchmark receipt must be an object.")
    forbidden = sorted(_RAW_HOST_ONLY_FIELDS.intersection(receipt))
    if forbidden:
        raise ValueError(
            "benchmark receipt must not contain raw host-only fields: "
            + ", ".join(forbidden)
            + "."
        )
    raw = receipt.get(BENCHMARK_RECEIPT_PROVENANCE_FIELD)
    if not isinstance(raw, Mapping):
        raise ValueError("benchmark_receipt_provenance is required.")
    if set(raw) != _PROVENANCE_FIELDS:
        raise ValueError("benchmark_receipt_provenance has invalid fields.")
    provenance = {key: deepcopy(raw[key]) for key in _PROVENANCE_FIELDS}
    if provenance.get("schema") != BENCHMARK_RECEIPT_PROVENANCE_SCHEMA:
        raise ValueError("benchmark_receipt_provenance.schema is invalid.")
    fixture_id = _nonempty(
        provenance.get("fixture_id"), field="benchmark_receipt_provenance.fixture_id"
    )
    if fixture_id != _nonempty(
        receipt.get("composition_fixture_id"),
        field="receipt.composition_fixture_id",
    ):
        raise ValueError("benchmark receipt provenance fixture does not match receipt.")
    for key in (
        "fixture_digest",
        "control_plan_digest",
        "composition_plan_digest",
        "phase_capsule_binding_digest",
        "control_input_digest",
        "execution_recipe_digest",
        "host_artifact_digest",
        "host_receipt_digest",
        "receipt_projection_digest",
        "provenance_digest",
    ):
        _digest(provenance.get(key), field=f"benchmark_receipt_provenance.{key}")
    graph_digest = _digest(
        provenance.get("graph_digest"),
        field="benchmark_receipt_provenance.graph_digest",
        graph=True,
    )
    if graph_digest != _digest(receipt.get("graph_digest"), field="receipt.graph_digest", graph=True):
        raise ValueError("benchmark receipt provenance graph does not match receipt.")
    control_plan_id = _nonempty(
        provenance.get("control_plan_id"),
        field="benchmark_receipt_provenance.control_plan_id",
    )
    if _CONTROL_PLAN_ID_RE.fullmatch(control_plan_id) is None:
        raise ValueError("benchmark_receipt_provenance.control_plan_id is invalid.")
    composition_plan_id = _nonempty(
        provenance.get("composition_plan_id"),
        field="benchmark_receipt_provenance.composition_plan_id",
    )
    if _COMPOSITION_PLAN_ID_RE.fullmatch(composition_plan_id) is None:
        raise ValueError("benchmark_receipt_provenance.composition_plan_id is invalid.")
    if composition_plan_id != _nonempty(receipt.get("recipe_id"), field="receipt.recipe_id"):
        raise ValueError("benchmark receipt provenance plan does not match receipt.")
    for provenance_key, receipt_key in (
        ("composition_plan_digest", "composition_plan_digest"),
        ("phase_capsule_binding_digest", "phase_capsule_binding_digest"),
        ("control_input_digest", "benchmark_control_input_digest"),
        ("execution_recipe_digest", "benchmark_execution_recipe_digest"),
        ("context_execution_mode", "context_execution_mode"),
    ):
        if provenance.get(provenance_key) != receipt.get(receipt_key):
            raise ValueError(
                "benchmark receipt provenance "
                f"{provenance_key} does not match receipt."
            )
    mode = _nonempty(
        provenance.get("context_execution_mode"),
        field="benchmark_receipt_provenance.context_execution_mode",
    )
    if mode not in _CONTEXT_EXECUTION_MODES:
        raise ValueError(
            "benchmark_receipt_provenance.context_execution_mode is invalid."
        )
    if provenance.get("evidence_trust") != RECEIPT_TRUST:
        raise ValueError("benchmark_receipt_provenance.evidence_trust is invalid.")
    if stable_digest(_receipt_projection_payload(receipt)) != provenance.get(
        "receipt_projection_digest"
    ):
        raise ValueError("benchmark receipt provenance projection digest is invalid.")
    payload = _provenance_payload(provenance)
    expected_digest = stable_digest(payload)
    if provenance.get("provenance_digest") != expected_digest:
        raise ValueError("benchmark receipt provenance digest is invalid.")
    expected_id = "benchmark-receipt-" + expected_digest[:20]
    provenance_id = _nonempty(
        provenance.get("provenance_id"),
        field="benchmark_receipt_provenance.provenance_id",
    )
    if (
        _PROVENANCE_ID_RE.fullmatch(provenance_id) is None
        or provenance_id != expected_id
    ):
        raise ValueError("benchmark receipt provenance id is invalid.")
    return provenance


def benchmark_provenance_matches_phase_capsule_binding(
    receipt: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> bool:
    """Return whether self-validating benchmark provenance matches one compiler binding."""

    try:
        provenance = validate_benchmark_receipt_provenance(receipt)
        expected = validate_phase_capsule_binding(binding)
    except (PhaseCapsuleBindingError, ValueError):
        return False
    return (
        provenance["composition_plan_id"] == expected["composition_plan_id"]
        and provenance["composition_plan_digest"]
        == expected["composition_plan_digest"]
        and provenance["phase_capsule_binding_digest"] == expected["binding_digest"]
        and provenance["graph_digest"] == expected["graph_digest"]
    )


def _receipt_projection(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    fixture_digest: str,
    control_plan_id: str,
    control_plan_digest: str,
    projection: Mapping[str, Any],
    receipt_validation: Mapping[str, Any],
    quality_scores: Mapping[str, Any],
    full_artifact_digest: str,
) -> dict[str, Any]:
    """Persist compiler-derived receipt fields plus closed benchmark provenance."""

    gates = receipt_validation["gates"]
    handoffs = receipt_validation["handoffs"]
    if not isinstance(gates, Mapping) or not isinstance(handoffs, Mapping):
        raise ValueError("Receipt validation did not produce structured runtime evidence.")
    expected_ref = f"artifact:{full_artifact_digest}"
    expected_quality = _receipt_quality_metrics(quality_scores)
    execution_context = receipt_validation.get("execution_context")
    if not isinstance(execution_context, Mapping):
        raise ValueError("Receipt validation did not produce execution-context evidence.")
    try:
        phase_capsule_binding = validate_phase_capsule_binding(
            projection.get("plan", {}).get("phase_capsule_binding"),
            composition_plan=projection.get("plan"),
        )
    except (AttributeError, PhaseCapsuleBindingError) as exc:
        raise ValueError("Replay composition plan is missing a valid phase binding.") from exc
    for key in (
        "context_accounting_digest",
        "preflight_capsule_digest",
        "phase_capsule_trace",
    ):
        if execution_context.get(key) != phase_capsule_binding.get(key):
            raise ValueError(
                "Benchmark execution context does not match the compiler phase binding."
            )
    compiled = _finite_number(
        projection.get("compiled_context_tokens"), field="projection.compiled_context"
    )
    naive = _finite_number(
        projection.get("naive_context_tokens"), field="projection.naive_context"
    )
    source_node_by_skill: dict[str, str] = {}
    for source in projection["source_slices"]:
        skill_id = str(source["skill_id"])
        source_node_id = str(source["source_node_id"])
        existing = source_node_by_skill.setdefault(skill_id, source_node_id)
        if existing != source_node_id:
            raise ValueError("A selected skill must retain one source node identity.")
    persisted: dict[str, Any] = {
        "schema": "tmcp-run-receipt-v0.1",
        "created_at": receipt["created_at"],
        "packet_id": receipt["packet_id"],
        "activated_atoms": list(receipt_validation["activated_atoms"]),
        "ignored_atoms": [],
        "commands_run": [],
        "verification_results": [],
        "user_overrides": [],
        "outcome": "passed",
        "trust": RECEIPT_TRUST,
        "instruction_override_policy": RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
        "recipe_id": projection["composition_plan_id"],
        "task_identity": dict(projection["task_identity"]),
        "graph_digest": projection["graph_digest"],
        "composition_plan_digest": phase_capsule_binding[
            "composition_plan_digest"
        ],
        "phase_capsule_binding_digest": phase_capsule_binding["binding_digest"],
        "content_digests": sorted(
            {item["content_digest"] for item in projection["source_slices"]}
        ),
        "selected_skill_ids": [
            source_node_by_skill[skill_id]
            for skill_id in projection["selected_skill_ids"]
        ],
        "phase_trace": list(receipt_validation["phase_trace"]),
        "gate_results": [
            {"gate_id": item["gate_id"], "status": item["status"]}
            for item in gates["evaluated_gates"]
        ],
        "handoff_results": [
            {
                "handoff_id": item["handoff_id"],
                "producer_node_id": item["producer_node_id"],
                "consumer_node_id": item["consumer_node_id"],
                "status": item["status"],
                "consumed_inputs": list(item["consumed_inputs"]),
                "produced_outputs": list(item["produced_outputs"]),
                "evidence_refs": [expected_ref],
            }
            for item in handoffs["evaluated_handoffs"]
        ],
        "quality_metrics": expected_quality,
        "cost_metrics": {
            "context_tokens": compiled,
            "context_ratio": round(compiled / naive, 4),
        },
        "context_execution_mode": execution_context["execution_context_mode"],
        "context_accounting_digest": execution_context["context_accounting_digest"],
        "preflight_capsule_digest": execution_context["preflight_capsule_digest"],
        "phase_capsule_trace": list(execution_context["phase_capsule_trace"]),
        "composition_fixture_id": fixture_id,
        "benchmark_control_input_digest": projection["full_variant"]["input_packet_digest"],
        "benchmark_execution_recipe_digest": projection["full_variant"][
            "execution_recipe_digest"
        ],
    }
    persisted[BENCHMARK_RECEIPT_PROVENANCE_FIELD] = (
        build_benchmark_receipt_provenance(
            persisted,
            fixture_digest=fixture_digest,
            control_plan_id=control_plan_id,
            control_plan_digest=control_plan_digest,
            host_artifact_digest=full_artifact_digest,
            host_receipt_digest=stable_digest(dict(receipt)),
        )
    )
    validate_benchmark_receipt_provenance(persisted)
    return persisted
