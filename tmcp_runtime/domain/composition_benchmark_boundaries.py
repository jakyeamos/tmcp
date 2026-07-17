"""Shared bounded-input validation for composition benchmark assembly."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.receipts import RECEIPT_TRUST
from tmcp_runtime.safety.redaction import redact_sensitive_text


HOST_RESULTS_SCHEMA = "tmcp-composition-benchmark-host-results-v0.1"
EVALUATOR_ARTIFACTS_SCHEMA = "tmcp-composition-benchmark-evaluator-artifacts-v0.1"
BENCHMARK_BINDING_SCHEMA = "tmcp-composition-benchmark-binding-v0.1"
OBSERVATIONS_SCHEMA = "tmcp-composition-benchmark-observations-v0.1"
# One cap applies to every persisted or replayed benchmark JSON artifact. The
# item boundaries below keep the assembled projection comfortably inside it.
MAX_BENCHMARK_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_CHARS = 16_000
MAX_EVIDENCE_CHARS = 8_000
MAX_METADATA_CHARS = 512
MAX_SOURCE_SLICE_CHARS = 48_000
MAX_EVIDENCE_ITEMS = 16
UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _nonempty(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required.")
    return result


def _bounded_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty string.")
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds the {maximum}-character boundary.")
    return value


def _untrusted_text(
    value: object,
    *,
    field: str,
    maximum: int,
    allowed_literals: Sequence[str] = (),
) -> str:
    """Reject secrets before untrusted host/evaluator text reaches persistence.

    Compiler-derived hashes legitimately occur in execution artifacts. Protect
    only those exact, independently derived literals while checking the rest of
    the free text with TMCP's standard secret/high-entropy detector. This is a
    fail-closed boundary: callers must redact unsafe evidence before submitting
    it so evaluator bindings remain reproducible.
    """

    text = _bounded_text(value, field=field, maximum=maximum)
    protected = text
    replacements: list[tuple[str, str]] = []
    for index, literal in enumerate(
        sorted({item for item in allowed_literals if item}, key=len, reverse=True)
    ):
        marker = f"TMCPBENCHMARKSAFE{index}"
        protected = protected.replace(literal, marker)
        replacements.append((marker, literal))
    _redacted, redactions = redact_sensitive_text(protected, enabled=True)
    if redactions:
        labels = ", ".join(sorted(redactions))
        raise ValueError(
            f"{field} contains sensitive or high-entropy text ({labels}); "
            "redact it before benchmark assembly."
        )
    for marker, literal in replacements:
        protected = protected.replace(marker, literal)
    return text


def _serialized_size(value: Mapping[str, Any], *, field: str) -> int:
    try:
        serialized = json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON-serializable.") from exc
    size = len(serialized.encode())
    if size > MAX_BENCHMARK_ARTIFACT_BYTES:
        raise ValueError(f"{field} exceeds {MAX_BENCHMARK_ARTIFACT_BYTES} bytes.")
    return size


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric.")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")
    return number


def _string_list(
    value: object,
    *,
    field: str,
    allow_empty: bool = False,
) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of strings.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain nonempty strings.")
        result.append(item.strip())
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must not contain duplicate strings.")
    if not result and not allow_empty:
        raise ValueError(f"{field} must not be empty.")
    return result


def _assert_keys(
    value: Mapping[str, Any],
    *,
    field: str,
    required: set[str],
    optional: set[str] = frozenset(),
) -> None:
    observed = set(value)
    missing = sorted(required.difference(observed))
    unexpected = sorted(observed.difference(required | optional))
    if missing or unexpected:
        raise ValueError(
            f"{field} has invalid fields; missing={missing}, unexpected={unexpected}."
        )


def _indexed(
    records: Sequence[Mapping[str, Any]],
    *,
    field: str,
    id_field: str,
    expected: set[str],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records, start=1):
        record_id = _nonempty(
            record.get(id_field), field=f"{field}[{index}].{id_field}"
        )
        if record_id in result:
            raise ValueError(f"{field} has duplicate {id_field} {record_id}.")
        result[record_id] = record
    observed = set(result)
    if observed != expected:
        raise ValueError(
            f"{field} must cover the compiler controls exactly; "
            f"missing={sorted(expected - observed)}, "
            f"unexpected={sorted(observed - expected)}."
        )
    return result


def _control_indexes(
    control_plan: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    routing = _indexed(
        _mapping_list(control_plan.get("routing_controls"), field="control.routing"),
        field="control.routing",
        id_field="case_id",
        expected={
            _nonempty(item.get("case_id"), field="control.routing.case_id")
            for item in _mapping_list(
                control_plan.get("routing_controls"), field="control.routing"
            )
        },
    )
    behavioral = _indexed(
        _mapping_list(
            control_plan.get("behavioral_controls"), field="control.behavioral"
        ),
        field="control.behavioral",
        id_field="fixture_id",
        expected={
            _nonempty(item.get("fixture_id"), field="control.behavioral.fixture_id")
            for item in _mapping_list(
                control_plan.get("behavioral_controls"), field="control.behavioral"
            )
        },
    )
    return routing, behavioral


def _control_literals(control: Mapping[str, Any]) -> list[str]:
    """Return only compiler-derived opaque values allowed in host text."""

    values = [
        control.get("input_digest"),
        control.get("input_packet_digest"),
        control.get("execution_recipe_digest"),
        control.get("replay_packet_id"),
    ]
    return [item for item in values if isinstance(item, str) and item]


def _validate_header(
    bundle: Mapping[str, Any],
    *,
    field: str,
    schema: str,
    control_plan: Mapping[str, Any],
    collections: set[str],
) -> None:
    _assert_keys(
        bundle,
        field=field,
        required={
            "schema",
            "run_manifest_id",
            "run_manifest_digest",
            "control_plan_id",
            "control_plan_digest",
            *collections,
        },
    )
    if bundle.get("schema") != schema:
        raise ValueError(f"{field}.schema must be {schema}.")
    for key in (
        "run_manifest_id",
        "run_manifest_digest",
        "control_plan_id",
        "control_plan_digest",
    ):
        if bundle.get(key) != control_plan.get(key):
            raise ValueError(f"{field}.{key} must match the compiler control plan.")


def _binding(
    *,
    run_plan: Mapping[str, Any],
    semantic_proposals: Mapping[str, Any],
    control_plan: Mapping[str, Any],
    host_results: Mapping[str, Any],
    evaluator_artifacts: Mapping[str, Any],
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    runtime = run_plan.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("Benchmark run plan is missing runtime identity.")
    binding: dict[str, Any] = {
        "schema": BENCHMARK_BINDING_SCHEMA,
        "run_manifest_id": run_plan["run_manifest_id"],
        "run_manifest_digest": run_plan["run_manifest_digest"],
        "semantic_proposals_digest": stable_digest(dict(semantic_proposals)),
        "control_plan_id": control_plan["control_plan_id"],
        "control_plan_digest": control_plan["control_plan_digest"],
        "host_results_digest": stable_digest(dict(host_results)),
        "evaluator_artifacts_digest": stable_digest(dict(evaluator_artifacts)),
        "compiler_release": _nonempty(runtime.get("release"), field="runtime.release"),
        "compiler_contract_digest": _nonempty(
            runtime.get("compiler_contract_digest"),
            field="runtime.compiler_contract_digest",
        ),
        "evidence_trust": RECEIPT_TRUST,
        "observation_payload_digest": stable_digest(dict(observations)),
    }
    binding["binding_digest"] = stable_digest(binding)
    return binding
