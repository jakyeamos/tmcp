"""Bind benchmark execution evidence to compiler-replayed composition controls."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.composition_benchmark_manifests import (
    behavioral_input_digest,
    evidence_record_digest,
    execution_record_digest,
    execution_result_digest,
    required_behavioral_variants,
    routing_input_digest,
)
from tmcp_runtime.domain.composition_benchmark_protocol import (
    fixture_workspace_relative_path,
    validate_benchmark_run_plan,
)
from tmcp_runtime.domain.composition_benchmark_replay import (
    BENCHMARK_CONTROL_PLAN_SCHEMA,
    validate_benchmark_control_plan,
)
from tmcp_runtime.domain.composition_benchmarks import score_composition_benchmark
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.composition_runtime_evidence import (
    COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
    composition_gate_catalog,
    composition_handoff_catalog,
    evaluate_composition_gates,
    evaluate_composition_handoffs,
)
from tmcp_runtime.domain.composition_benchmark_sources import (
    graph_digest_for_observation,
)
from tmcp_runtime.domain.receipts import (
    RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
    RECEIPT_TRUST,
)
from tmcp_runtime.safety.redaction import redact_sensitive_text


HOST_RESULTS_SCHEMA = "tmcp-composition-benchmark-host-results-v0.1"
EVALUATOR_ARTIFACTS_SCHEMA = "tmcp-composition-benchmark-evaluator-artifacts-v0.1"
BENCHMARK_BINDING_SCHEMA = "tmcp-composition-benchmark-binding-v0.1"
OBSERVATIONS_SCHEMA = "tmcp-composition-benchmark-observations-v0.1"
# One cap applies to every persisted or replayed benchmark JSON artifact.  The
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

    Compiler-derived hashes legitimately occur in execution artifacts.  Protect
    only those exact, independently derived literals while checking the rest of
    the free text with TMCP's standard secret/high-entropy detector.  This is a
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


def _raw_evidence(
    value: object,
    *,
    field: str,
    require_ids: bool = False,
    allowed_literals: Sequence[str] = (),
) -> list[dict[str, str]]:
    evidence = _mapping_list(value, field=field)
    if not evidence:
        raise ValueError(f"{field} must not be empty.")
    if len(evidence) > MAX_EVIDENCE_ITEMS:
        raise ValueError(
            f"{field} exceeds the {MAX_EVIDENCE_ITEMS}-item evidence boundary."
        )
    result: list[dict[str, str]] = []
    for index, item in enumerate(evidence, start=1):
        item_field = f"{field}[{index}]"
        _assert_keys(
            item,
            field=item_field,
            required=(
                {"evidence_id", "media_type", "content"}
                if require_ids
                else {"media_type", "content"}
            ),
        )
        normalized = {
            "media_type": _untrusted_text(
                item.get("media_type"),
                field=f"{item_field}.media_type",
                maximum=MAX_METADATA_CHARS,
            ),
            "content": _untrusted_text(
                item.get("content"),
                field=f"{item_field}.content",
                maximum=MAX_EVIDENCE_CHARS,
                allowed_literals=allowed_literals,
            ),
        }
        if require_ids:
            normalized["evidence_id"] = _untrusted_text(
                item.get("evidence_id"),
                field=f"{item_field}.evidence_id",
                maximum=MAX_METADATA_CHARS,
            )
        result.append(normalized)
    if require_ids:
        evidence_ids = [item["evidence_id"] for item in result]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(f"{field} must not contain duplicate evidence_id values.")
    return result


def _dimension_evidence_bindings(
    value: object,
    *,
    expected_requirements: Mapping[str, Sequence[str]],
    evidence_ids: set[str],
    field: str,
) -> dict[str, list[dict[str, Any]]]:
    """Require every rubric evidence need to point to a concrete evaluator fact."""

    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must map every rubric dimension to evidence.")
    if set(value) != set(expected_requirements):
        raise ValueError(
            f"{field} must cover every rubric dimension exactly; "
            f"missing={sorted(set(expected_requirements) - set(value))}, "
            f"unexpected={sorted(set(value) - set(expected_requirements))}."
        )
    result: dict[str, list[dict[str, Any]]] = {}
    for dimension_id, required in expected_requirements.items():
        entries = _mapping_list(value.get(dimension_id), field=f"{field}.{dimension_id}")
        if not entries:
            raise ValueError(f"{field}.{dimension_id} must not be empty.")
        normalized: list[dict[str, Any]] = []
        observed_requirements: list[str] = []
        for index, entry in enumerate(entries, start=1):
            entry_field = f"{field}.{dimension_id}[{index}]"
            _assert_keys(
                entry,
                field=entry_field,
                required={"requirement", "evidence_ids", "claim"},
            )
            requirement = _nonempty(
                entry.get("requirement"), field=f"{entry_field}.requirement"
            )
            refs = _string_list(
                entry.get("evidence_ids"), field=f"{entry_field}.evidence_ids"
            )
            if not set(refs).issubset(evidence_ids):
                raise ValueError(
                    f"{entry_field}.evidence_ids must reference evaluator evidence."
                )
            normalized.append(
                {
                    "requirement": requirement,
                    "evidence_ids": refs,
                    "claim": _untrusted_text(
                        entry.get("claim"),
                        field=f"{entry_field}.claim",
                        maximum=MAX_EVIDENCE_CHARS,
                    ),
                }
            )
            observed_requirements.append(requirement)
        if observed_requirements != list(required):
            raise ValueError(
                f"{field}.{dimension_id} must bind every required evidence item "
                "in rubric order."
            )
        result[dimension_id] = normalized
    return result


def _validate_host_results(
    host_results: Mapping[str, Any],
    *,
    control_plan: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, dict[str, Mapping[str, Any]]]]:
    _validate_header(
        host_results,
        field="host_results",
        schema=HOST_RESULTS_SCHEMA,
        control_plan=control_plan,
        collections={"routing_runs", "behavioral_runs"},
    )
    routing_controls, behavioral_controls = _control_indexes(control_plan)
    routing_runs = _indexed(
        _mapping_list(
            host_results.get("routing_runs"), field="host_results.routing_runs"
        ),
        field="host_results.routing_runs",
        id_field="case_id",
        expected=set(routing_controls),
    )
    for case_id, run in routing_runs.items():
        field = f"host_results.routing_runs.{case_id}"
        _assert_keys(
            run,
            field=field,
            required={
                "case_id",
                "request_id",
                "input_digest",
                "selected_skill_ids",
                "run_id",
                "outcome",
                "artifact",
                "evidence",
            },
        )
        control = routing_controls[case_id]
        for key in ("request_id", "input_digest"):
            if run.get(key) != control.get(key):
                raise ValueError(f"{field}.{key} must match the routing control.")
        selected = _string_list(
            run.get("selected_skill_ids"), field=f"{field}.selected_skill_ids"
        )
        if selected != list(control.get("selected_skill_ids") or []):
            raise ValueError(f"{field}.selected_skill_ids must match compiler replay.")
        if run.get("outcome") != "passed":
            raise ValueError(f"{field}.outcome must be passed.")
        literals = _control_literals(control)
        _bounded_text(
            run.get("run_id"), field=f"{field}.run_id", maximum=MAX_METADATA_CHARS
        )
        _untrusted_text(
            run.get("artifact"),
            field=f"{field}.artifact",
            maximum=MAX_ARTIFACT_CHARS,
            allowed_literals=literals,
        )
        _raw_evidence(
            run.get("evidence"),
            field=f"{field}.evidence",
            allowed_literals=literals,
        )

    behavioral_runs = _indexed(
        _mapping_list(
            host_results.get("behavioral_runs"), field="host_results.behavioral_runs"
        ),
        field="host_results.behavioral_runs",
        id_field="fixture_id",
        expected=set(behavioral_controls),
    )
    variants_by_fixture: dict[str, dict[str, Mapping[str, Any]]] = {}
    for fixture_id, run in behavioral_runs.items():
        field = f"host_results.behavioral_runs.{fixture_id}"
        _assert_keys(
            run,
            field=field,
            required={"fixture_id", "request_id", "variants"},
        )
        control = behavioral_controls[fixture_id]
        if run.get("request_id") != control.get("request_id"):
            raise ValueError(f"{field}.request_id must match the behavioral control.")
        controls_by_variant = _indexed(
            _mapping_list(
                control.get("variants"), field=f"control.{fixture_id}.variants"
            ),
            field=f"control.{fixture_id}.variants",
            id_field="variant_id",
            expected={
                _nonempty(item.get("variant_id"), field="control.variant_id")
                for item in _mapping_list(
                    control.get("variants"), field=f"control.{fixture_id}.variants"
                )
            },
        )
        runs_by_variant = _indexed(
            _mapping_list(run.get("variants"), field=f"{field}.variants"),
            field=f"{field}.variants",
            id_field="variant_id",
            expected=set(controls_by_variant),
        )
        for variant_id, variant_run in runs_by_variant.items():
            variant_field = f"{field}.variants.{variant_id}"
            optional = (
                {"tmcp_run_receipt"} if variant_id == "full_composition" else set()
            )
            _assert_keys(
                variant_run,
                field=variant_field,
                required={
                    "variant_id",
                    "input_packet_digest",
                    "execution_recipe_digest",
                    "run_id",
                    "outcome",
                    "artifact",
                },
                optional=optional,
            )
            control_variant = controls_by_variant[variant_id]
            for key in ("input_packet_digest", "execution_recipe_digest"):
                if variant_run.get(key) != control_variant.get(key):
                    raise ValueError(
                        f"{variant_field}.{key} must match the compiler control."
                    )
            if variant_run.get("outcome") != "passed":
                raise ValueError(f"{variant_field}.outcome must be passed.")
            literals = _control_literals(control_variant)
            _bounded_text(
                variant_run.get("run_id"),
                field=f"{variant_field}.run_id",
                maximum=MAX_METADATA_CHARS,
            )
            _untrusted_text(
                variant_run.get("artifact"),
                field=f"{variant_field}.artifact",
                maximum=MAX_ARTIFACT_CHARS,
                allowed_literals=literals,
            )
            receipt = variant_run.get("tmcp_run_receipt")
            if variant_id == "full_composition" and not isinstance(receipt, Mapping):
                raise ValueError(f"{variant_field}.tmcp_run_receipt is required.")
            if isinstance(receipt, Mapping):
                _validate_full_receipt_shape(receipt, field=variant_field)
            if variant_id != "full_composition" and receipt is not None:
                raise ValueError(
                    f"{variant_field}.tmcp_run_receipt is only valid for full composition."
                )
        variants_by_fixture[fixture_id] = runs_by_variant
    return routing_runs, variants_by_fixture


def _rubric(fixture: Mapping[str, Any], *, field: str) -> Mapping[str, Any]:
    rubric = fixture.get("quality_rubric")
    if not isinstance(rubric, Mapping):
        raise ValueError(f"{field}.quality_rubric is required.")
    return rubric


def _validate_evaluator_artifacts(
    evaluator_artifacts: Mapping[str, Any],
    *,
    control_plan: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
    host_variants: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, tuple[Mapping[str, Any], dict[str, Mapping[str, Any]]]]:
    _validate_header(
        evaluator_artifacts,
        field="evaluator_artifacts",
        schema=EVALUATOR_ARTIFACTS_SCHEMA,
        control_plan=control_plan,
        collections={"fixture_evaluations"},
    )
    fixtures = _indexed(
        _mapping_list(behavioral_fixtures.get("fixtures"), field="fixtures"),
        field="fixtures",
        id_field="fixture_id",
        expected={
            _nonempty(item.get("fixture_id"), field="fixture.fixture_id")
            for item in _mapping_list(
                behavioral_fixtures.get("fixtures"), field="fixtures"
            )
        },
    )
    _routing, controls = _control_indexes(control_plan)
    evaluations = _indexed(
        _mapping_list(
            evaluator_artifacts.get("fixture_evaluations"),
            field="evaluator_artifacts.fixture_evaluations",
        ),
        field="evaluator_artifacts.fixture_evaluations",
        id_field="fixture_id",
        expected=set(controls),
    )
    result: dict[str, tuple[Mapping[str, Any], dict[str, Mapping[str, Any]]]] = {}
    for fixture_id, evaluation in evaluations.items():
        field = f"evaluator_artifacts.fixture_evaluations.{fixture_id}"
        _assert_keys(
            evaluation,
            field=field,
            required={
                "fixture_id",
                "evaluator_id",
                "evaluator_version",
                "evaluation_run_id",
                "evaluated_at",
                "method",
                "rubric_id",
                "rubric_version",
                "rubric_digest",
                "variants",
            },
        )
        fixture = fixtures[fixture_id]
        rubric = _rubric(fixture, field=fixture_id)
        expected_rubric = {
            "rubric_id": str(rubric.get("rubric_id") or ""),
            "rubric_version": str(rubric.get("version") or ""),
            "rubric_digest": stable_digest(dict(rubric)),
        }
        for key, expected in expected_rubric.items():
            if evaluation.get(key) != expected:
                raise ValueError(f"{field}.{key} must match the fixture rubric.")
        for key in (
            "evaluator_id",
            "evaluator_version",
            "evaluation_run_id",
            "evaluated_at",
            "method",
        ):
            _untrusted_text(
                evaluation.get(key),
                field=f"{field}.{key}",
                maximum=MAX_METADATA_CHARS,
            )
        control = controls[fixture_id]
        control_variants = _indexed(
            _mapping_list(
                control.get("variants"), field=f"control.{fixture_id}.variants"
            ),
            field=f"control.{fixture_id}.variants",
            id_field="variant_id",
            expected={
                _nonempty(item.get("variant_id"), field="control.variant_id")
                for item in _mapping_list(
                    control.get("variants"), field=f"control.{fixture_id}.variants"
                )
            },
        )
        variants = _indexed(
            _mapping_list(evaluation.get("variants"), field=f"{field}.variants"),
            field=f"{field}.variants",
            id_field="variant_id",
            expected=set(control_variants),
        )
        dimensions = {
            _nonempty(
                item.get("dimension_id"), field=f"{fixture_id}.dimension_id"
            ): _finite_number(item.get("weight"), field=f"{fixture_id}.weight")
            for item in _mapping_list(
                rubric.get("dimensions"), field=f"{fixture_id}.dimensions"
            )
        }
        dimension_requirements = {
            _nonempty(
                item.get("dimension_id"), field=f"{fixture_id}.dimension_id"
            ): _string_list(
                item.get("evidence_required"),
                field=f"{fixture_id}.evidence_required",
            )
            for item in _mapping_list(
                rubric.get("dimensions"), field=f"{fixture_id}.dimensions"
            )
        }
        for variant_id, variant in variants.items():
            variant_field = f"{field}.variants.{variant_id}"
            _assert_keys(
                variant,
                field=variant_field,
                required={
                    "variant_id",
                    "input_packet_digest",
                    "execution_recipe_digest",
                    "execution_artifact_digest",
                    "dimension_scores",
                    "evidence",
                    "dimension_evidence",
                },
            )
            control_variant = control_variants[variant_id]
            for key in ("input_packet_digest", "execution_recipe_digest"):
                if variant.get(key) != control_variant.get(key):
                    raise ValueError(
                        f"{variant_field}.{key} must match the compiler control."
                    )
            host = host_variants[fixture_id][variant_id]
            if variant.get("execution_artifact_digest") != stable_digest(
                str(host.get("artifact") or "")
            ):
                raise ValueError(
                    f"{variant_field}.execution_artifact_digest must bind the host artifact."
                )
            scores = variant.get("dimension_scores")
            if not isinstance(scores, Mapping) or set(scores) != set(dimensions):
                raise ValueError(
                    f"{variant_field}.dimension_scores must cover every rubric dimension."
                )
            for dimension_id, value in scores.items():
                score = _finite_number(value, field=f"{variant_field}.{dimension_id}")
                if not 0.0 <= score <= 1.0:
                    raise ValueError(
                        f"{variant_field}.{dimension_id} must be between 0 and 1."
                    )
            evidence = _raw_evidence(
                variant.get("evidence"),
                field=f"{variant_field}.evidence",
                require_ids=True,
                allowed_literals=_control_literals(control_variant),
            )
            _dimension_evidence_bindings(
                variant.get("dimension_evidence"),
                expected_requirements=dimension_requirements,
                evidence_ids={item["evidence_id"] for item in evidence},
                field=f"{variant_field}.dimension_evidence",
            )
        result[fixture_id] = (evaluation, variants)
    return result


def _source_slices(
    fixture: Mapping[str, Any],
    control: Mapping[str, Any],
) -> list[dict[str, Any]]:
    replay = control.get("replay")
    if not isinstance(replay, Mapping):
        raise ValueError("Behavioral control is missing compiler replay evidence.")
    preflight = replay.get("preflight")
    if not isinstance(preflight, Mapping):
        raise ValueError("Behavioral control is missing its replay preflight.")
    candidates = {
        _nonempty(item.get("source_node_id"), field="preflight.source_node_id"): item
        for item in _mapping_list(
            preflight.get("candidate_source_slices"),
            field="preflight.candidate_source_slices",
        )
    }
    workspace = fixture_workspace_relative_path(fixture)
    result: list[dict[str, Any]] = []
    for binding in _mapping_list(
        control.get("source_bindings"), field="source_bindings"
    ):
        skill_id = _nonempty(binding.get("skill_id"), field="source_binding.skill_id")
        source_node_id = _nonempty(
            binding.get("source_node_id"), field="source_binding.source_node_id"
        )
        candidate = candidates.get(source_node_id)
        if candidate is None:
            raise ValueError(
                "Selected control source is missing from the replay preflight."
            )
        content = _bounded_text(
            candidate.get("content"),
            field=f"preflight.{source_node_id}.content",
            maximum=MAX_SOURCE_SLICE_CHARS,
        )
        if candidate.get("char_start") != 0 or candidate.get("char_end") != len(
            content
        ):
            raise ValueError(
                "Benchmark observations require a complete selected source."
            )
        source_digest = _nonempty(
            candidate.get("source_digest"),
            field=f"preflight.{source_node_id}.source_digest",
        )
        if source_digest != binding.get("content_digest"):
            raise ValueError("Replay source digest does not match its control binding.")
        relative_path = _nonempty(
            binding.get("relative_path"), field="source_binding.relative_path"
        )
        result.append(
            {
                "skill_id": skill_id,
                "source_node_id": source_node_id,
                "relative_path": relative_path,
                "source_path": f"/tmcp-benchmark/{workspace}/{relative_path}",
                "content": content,
                "char_start": 0,
                "char_end": len(content),
                "slice_id": _nonempty(
                    candidate.get("slice_id"),
                    field=f"preflight.{source_node_id}.slice_id",
                ),
                "source_digest": source_digest,
                "slice_digest": _nonempty(
                    candidate.get("slice_digest"),
                    field=f"preflight.{source_node_id}.slice_digest",
                ),
                "content_digest": source_digest,
            }
        )
    return result


def _packet_id_for_phase(
    packet: Mapping[str, Any],
    plan: Mapping[str, Any],
    phase: str,
) -> str:
    """Mirror the compiler's stable packet identity for one permitted phase."""

    return "packet-" + stable_digest(
        {
            "objective": packet.get("objective"),
            "phase": phase,
            "composition_plan_id": plan.get("composition_plan_id"),
            "graph_digest": dict(plan.get("provenance") or {}).get("graph_digest"),
        }
    )[:12]


def _behavioral_projection(
    fixture: Mapping[str, Any],
    control: Mapping[str, Any],
) -> dict[str, Any]:
    replay = control.get("replay")
    if not isinstance(replay, Mapping):
        raise ValueError("Behavioral control is missing replay evidence.")
    packet = replay.get("packet")
    if not isinstance(packet, Mapping):
        raise ValueError("Behavioral control is missing its replay packet.")
    plan = packet.get("composition_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("Behavioral replay packet is missing a composition plan.")
    source_slices = _source_slices(fixture, control)
    skill_by_node = {
        str(item["source_node_id"]): str(item["skill_id"]) for item in source_slices
    }
    relationships: list[dict[str, Any]] = []
    for edge in _mapping_list(
        plan.get("typed_edges"), field="composition_plan.typed_edges"
    ):
        source_node_id = _nonempty(edge.get("from"), field="composition_plan.edge.from")
        target_node_id = _nonempty(edge.get("to"), field="composition_plan.edge.to")
        source_skill_id = skill_by_node.get(source_node_id)
        target_skill_id = skill_by_node.get(target_node_id)
        if source_skill_id is None or target_skill_id is None:
            raise ValueError(
                "Compiler edge references a source outside the selected graph."
            )
        relationships.append(
            {
                "source_id": source_skill_id,
                "target_id": target_skill_id,
                "relation": _nonempty(
                    edge.get("type"), field="composition_plan.edge.type"
                ),
                "citations": list(edge.get("citations") or []),
            }
        )
    active_stages: list[dict[str, Any]] = []
    for stage in _mapping_list(
        plan.get("ordered_stages"), field="composition_plan.stages"
    ):
        node_ids = _string_list(
            stage.get("node_ids"), field="composition_plan.stage.node_ids"
        )
        active_skill_ids = [skill_by_node[node_id] for node_id in node_ids]
        active_stages.append(
            {
                "stage_id": _nonempty(
                    stage.get("stage_id"), field="composition_plan.stage.id"
                ),
                "active_skill_ids": active_skill_ids,
            }
        )
    selected_skill_ids = _string_list(
        control.get("selected_skill_ids"), field="control.selected_skill_ids"
    )
    ordered_skill_ids = _string_list(
        control.get("ordered_skill_ids"), field="control.ordered_skill_ids"
    )
    stage_order = [
        skill_id for stage in active_stages for skill_id in stage["active_skill_ids"]
    ]
    if stage_order != ordered_skill_ids or ordered_skill_ids != selected_skill_ids:
        raise ValueError(
            "Compiler stages must preserve the selected logical skill order."
        )
    source_nodes = {item["skill_id"]: item["source_node_id"] for item in source_slices}
    source_slices_by_id = {item["slice_id"]: item for item in source_slices}
    graph_digest = graph_digest_for_observation(
        selected_skill_ids,
        relationships,
        source_node_by_skill=source_nodes,
        slices_by_id=source_slices_by_id,
    )
    provenance = plan.get("provenance")
    if not isinstance(provenance, Mapping) or graph_digest != provenance.get(
        "graph_digest"
    ):
        raise ValueError(
            "Observation graph projection does not match compiler provenance."
        )
    full_variant = next(
        (
            item
            for item in _mapping_list(control.get("variants"), field="control.variants")
            if item.get("variant_id") == "full_composition"
        ),
        None,
    )
    if not isinstance(full_variant, Mapping):
        raise ValueError("Behavioral control is missing full-composition evidence.")
    recipe = full_variant.get("execution_recipe")
    if not isinstance(recipe, Mapping):
        raise ValueError("Full-composition control is missing its execution recipe.")
    accounting = recipe.get("context_accounting")
    if not isinstance(accounting, Mapping):
        raise ValueError("Full-composition control is missing context accounting.")
    compiled = _finite_number(
        accounting.get("compiled_context_tokens"),
        field="context_accounting.compiled_context_tokens",
    )
    naive = _finite_number(
        accounting.get("naive_context_tokens"),
        field="context_accounting.naive_context_tokens",
    )
    if compiled < 0 or naive <= 0:
        raise ValueError("Compiler context accounting is invalid.")
    task_identity = packet.get("task_identity")
    if not isinstance(task_identity, Mapping):
        raise ValueError("Replay packet is missing task identity.")
    preflight = replay.get("preflight")
    if not isinstance(preflight, Mapping):
        raise ValueError("Behavioral replay is missing its preflight.")
    receipt_template = packet.get("receipt_template")
    if not isinstance(receipt_template, Mapping):
        raise ValueError("Behavioral replay packet is missing its receipt template.")
    permitted_atoms = _string_list(
        _string_list(packet.get("active_atoms"), field="replay.packet.active_atoms")
        + _string_list(
            packet.get("deferred_atoms"), field="replay.packet.deferred_atoms"
        ),
        field="replay.packet.composition_atoms",
    )
    permitted_packet_ids = {
        _nonempty(packet.get("packet_id"), field="replay.packet.packet_id"),
        *(
            _packet_id_for_phase(
                packet,
                plan,
                _nonempty(stage.get("phase"), field="composition_plan.stage.phase"),
            )
            for stage in _mapping_list(
                plan.get("ordered_stages"), field="composition_plan.stages"
            )
        ),
    }
    return {
        "fixture_id": _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id"),
        "preflight_id": _nonempty(preflight.get("preflight_id"), field="preflight.id"),
        "composition_plan_id": _nonempty(
            plan.get("composition_plan_id"), field="composition_plan.id"
        ),
        "graph_digest": graph_digest,
        "task_identity": dict(task_identity),
        "selected_skill_ids": selected_skill_ids,
        "source_slices": source_slices,
        "ordered_skill_ids": ordered_skill_ids,
        "active_stages": active_stages,
        "relationships": relationships,
        "compiled_context_tokens": compiled,
        "naive_context_tokens": naive,
        "permitted_packet_ids": sorted(permitted_packet_ids),
        "permitted_atoms": permitted_atoms,
        "full_variant": dict(full_variant),
        "plan": dict(plan),
    }


def _evidence_ids(values: Sequence[Mapping[str, str]], *, field: str) -> list[str]:
    result: list[str] = []
    for index, item in enumerate(values, start=1):
        record = {
            "media_type": item["media_type"],
            "content": item["content"],
            "content_digest": stable_digest(item["content"]),
        }
        evidence_id = "evidence-" + evidence_record_digest(record)[:20]
        if evidence_id in result:
            raise ValueError(f"{field} contains duplicate evidence content.")
        result.append(evidence_id)
    return result


def _evidence_manifest(
    values: Sequence[Mapping[str, str]],
    *,
    execution_id: str,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for item in values:
        record = {
            "execution_id": execution_id,
            "media_type": item["media_type"],
            "content": item["content"],
            "content_digest": stable_digest(item["content"]),
        }
        record["evidence_id"] = "evidence-" + evidence_record_digest(record)[:20]
        records.append(record)
    return records


def _execution_record(
    *,
    variant_id: str,
    input_digest: str,
    control_input_digest: str,
    execution_recipe_digest: str | None,
    artifact: str,
    result_digest: str,
    run_id: str,
    tmcp_run_receipt: Mapping[str, Any] | None,
    evidence_values: Sequence[Mapping[str, str]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    artifact_digest = stable_digest(artifact)
    receipt: dict[str, Any] = {
        "run_id": "host-run-" + stable_digest(run_id)[:20],
        "variant_id": variant_id,
        "outcome": "passed",
        "artifact_digest": artifact_digest,
    }
    if tmcp_run_receipt is not None:
        receipt["tmcp_run_receipt"] = dict(tmcp_run_receipt)
    evidence_ids = _evidence_ids(evidence_values, field=f"{variant_id}.evidence")
    record: dict[str, Any] = {
        "variant_id": variant_id,
        "input_digest": input_digest,
        "control_input_digest": control_input_digest,
        "artifact": artifact,
        "artifact_digest": artifact_digest,
        "result_digest": result_digest,
        "run_receipt": receipt,
        "receipt_digest": stable_digest(receipt),
        "evidence_ids": evidence_ids,
    }
    if execution_recipe_digest is not None:
        record["execution_recipe_digest"] = execution_recipe_digest
    record["execution_digest"] = execution_record_digest(record)
    record["execution_id"] = "execution-" + record["execution_digest"][:20]
    return record, _evidence_manifest(
        evidence_values, execution_id=record["execution_id"]
    )


def _quality_from_evaluation(
    fixture: Mapping[str, Any],
    *,
    selected_skill_ids: Sequence[str],
    variants: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    rubric = _rubric(fixture, field=str(fixture.get("fixture_id") or "fixture"))
    weights = {
        _nonempty(
            item.get("dimension_id"), field="rubric.dimension_id"
        ): _finite_number(item.get("weight"), field="rubric.dimension.weight")
        for item in _mapping_list(rubric.get("dimensions"), field="rubric.dimensions")
    }
    scores_by_variant: dict[str, float] = {}
    dimensions_by_variant: dict[str, dict[str, float]] = {}
    required = required_behavioral_variants(selected_skill_ids)
    if set(variants) != required:
        raise ValueError("Evaluator variants do not match the compiler controls.")
    for variant_id, variant in variants.items():
        raw = variant.get("dimension_scores")
        if not isinstance(raw, Mapping):
            raise ValueError(f"Evaluator dimensions are missing for {variant_id}.")
        normalized = {
            str(key): _finite_number(value, field=f"{variant_id}.{key}")
            for key, value in raw.items()
        }
        if set(normalized) != set(weights):
            raise ValueError(f"Evaluator dimensions are incomplete for {variant_id}.")
        dimensions_by_variant[variant_id] = normalized
        scores_by_variant[variant_id] = sum(
            normalized[dimension_id] * weight
            for dimension_id, weight in weights.items()
        )
    return (
        {
            "no_skill": scores_by_variant["no_skill"],
            "singletons": {
                skill_id: scores_by_variant[f"singleton:{skill_id}"]
                for skill_id in selected_skill_ids
            },
            "naive_union": scores_by_variant["naive_union"],
            "full_composition": scores_by_variant["full_composition"],
            "leave_one_out": {
                skill_id: scores_by_variant[f"leave_one_out:{skill_id}"]
                for skill_id in selected_skill_ids
            },
            "wrong_order": scores_by_variant["wrong_order"],
        },
        dimensions_by_variant,
    )


def _receipt_quality_metrics(quality_scores: Mapping[str, Any]) -> dict[str, float]:
    full = _finite_number(
        quality_scores.get("full_composition"), field="quality.full_composition"
    )
    naive = _finite_number(quality_scores.get("naive_union"), field="quality.naive")
    wrong_order = _finite_number(
        quality_scores.get("wrong_order"), field="quality.wrong_order"
    )
    singletons = quality_scores.get("singletons")
    if not isinstance(singletons, Mapping) or not singletons:
        raise ValueError("Quality metrics require singleton scores.")
    best_singleton = max(
        _finite_number(value, field=f"quality.singleton.{skill_id}")
        for skill_id, value in singletons.items()
    )
    return {
        "synergy_lift": round(full - best_singleton, 4),
        "compiler_lift": round(full - naive, 4),
        "order_lift": round(full - wrong_order, 4),
    }


def _validate_full_receipt_shape(receipt: Mapping[str, Any], *, field: str) -> None:
    """Enforce the recorded-receipt contract for direct domain callers too."""

    required = {
        "schema",
        "created_at",
        "packet_id",
        "activated_atoms",
        "ignored_atoms",
        "commands_run",
        "verification_results",
        "user_overrides",
        "outcome",
        "trust",
        "instruction_override_policy",
        "recipe_id",
        "task_identity",
        "graph_digest",
        "content_digests",
        "selected_skill_ids",
        "phase_trace",
        "gate_results",
        "handoff_results",
        "quality_metrics",
        "cost_metrics",
        "composition_fixture_id",
        "benchmark_control_input_digest",
        "benchmark_execution_recipe_digest",
    }
    missing = sorted(required.difference(receipt))
    if missing:
        raise ValueError(f"{field}.tmcp_run_receipt is missing {missing}.")
    if receipt.get("schema") != "tmcp-run-receipt-v0.1":
        raise ValueError(f"{field}.tmcp_run_receipt.schema is invalid.")
    if not isinstance(receipt.get("created_at"), str) or UTC_TIMESTAMP_RE.fullmatch(
        str(receipt.get("created_at"))
    ) is None:
        raise ValueError(f"{field}.tmcp_run_receipt.created_at must be UTC.")
    for key in ("packet_id", "recipe_id", "graph_digest", "composition_fixture_id"):
        _nonempty(receipt.get(key), field=f"{field}.tmcp_run_receipt.{key}")
    for key in ("activated_atoms", "ignored_atoms", "commands_run", "verification_results"):
        _string_list(
            receipt.get(key),
            field=f"{field}.tmcp_run_receipt.{key}",
            allow_empty=True,
        )
    if not isinstance(receipt.get("user_overrides"), list):
        raise ValueError(f"{field}.tmcp_run_receipt.user_overrides must be an array.")
    if not isinstance(receipt.get("task_identity"), Mapping):
        raise ValueError(f"{field}.tmcp_run_receipt.task_identity must be an object.")
    _string_list(
        receipt.get("content_digests"),
        field=f"{field}.tmcp_run_receipt.content_digests",
    )
    _string_list(
        receipt.get("selected_skill_ids"),
        field=f"{field}.tmcp_run_receipt.selected_skill_ids",
    )
    for key in ("phase_trace", "gate_results", "handoff_results"):
        _mapping_list(receipt.get(key), field=f"{field}.tmcp_run_receipt.{key}")
    for key in ("quality_metrics", "cost_metrics"):
        if not isinstance(receipt.get(key), Mapping):
            raise ValueError(f"{field}.tmcp_run_receipt.{key} must be an object.")
    if receipt.get("trust") != RECEIPT_TRUST:
        raise ValueError(f"{field}.tmcp_run_receipt.trust is invalid.")
    if receipt.get("instruction_override_policy") != RECEIPT_INSTRUCTION_OVERRIDE_POLICY:
        raise ValueError(
            f"{field}.tmcp_run_receipt.instruction_override_policy is invalid."
        )
    for key in (
        "benchmark_control_input_digest",
        "benchmark_execution_recipe_digest",
    ):
        value = str(receipt.get(key) or "")
        if re.fullmatch(r"[a-f0-9]{64}", value) is None:
            raise ValueError(f"{field}.tmcp_run_receipt.{key} must be a digest.")


def _requested_stage_index(
    stages: Sequence[Mapping[str, Any]],
    *,
    requested_phase: str,
    current_index: int,
) -> int:
    """Mirror runtime phase lookup so recorded obligations remain auditable."""

    matches = [
        index
        for index, stage in enumerate(stages)
        if str(stage.get("phase") or "") == requested_phase
    ]
    if not matches:
        raise ValueError("full receipt requested an unknown compiler phase.")
    later = [index for index in matches if index > current_index]
    if str(stages[current_index].get("phase") or "") == requested_phase:
        return later[0] if later else current_index
    return later[0] if later else matches[0]


def _transition_obligation_ids(
    plan: Mapping[str, Any],
    stages: Sequence[Mapping[str, Any]],
    *,
    current_index: int,
    requested_index: int,
) -> tuple[list[str], list[str]]:
    """Derive the exact runtime gate and handoff lists for one transition."""

    if requested_index <= current_index:
        return [], []
    exit_stage_ids = {
        _nonempty(stage.get("stage_id"), field="composition_plan.stage_id")
        for stage in stages[current_index:requested_index]
    }
    entry_stage_ids = {
        _nonempty(stage.get("stage_id"), field="composition_plan.stage_id")
        for stage in stages[current_index + 1 : requested_index + 1]
    }
    gate_ids = [
        _nonempty(gate.get("gate_id"), field="composition_plan.gate_id")
        for gate in composition_gate_catalog(plan)
        if (
            gate.get("kind") == "exit"
            and gate.get("owner_stage_id") in exit_stage_ids
        )
        or (
            gate.get("kind") == "entry"
            and gate.get("owner_stage_id") in entry_stage_ids
        )
    ]
    handoff_ids = [
        _nonempty(contract.get("handoff_id"), field="composition_plan.handoff_id")
        for contract in composition_handoff_catalog(plan)
        if contract.get("consumer_stage_id") in entry_stage_ids
    ]
    return gate_ids, handoff_ids


def _validate_phase_trace(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate the actual transition records emitted by runtime recompilation."""

    stages = _mapping_list(plan.get("ordered_stages"), field="composition_plan.stages")
    expected_stage_ids = [
        _nonempty(stage.get("stage_id"), field="composition_plan.stage_id")
        for stage in stages
    ]
    stage_index = {stage_id: index for index, stage_id in enumerate(expected_stage_ids)}
    stage_phase = {
        stage_id: _nonempty(stage.get("phase"), field="composition_plan.stage.phase")
        for stage_id, stage in zip(expected_stage_ids, stages, strict=True)
    }
    trace = _mapping_list(receipt.get("phase_trace"), field="receipt.phase_trace")
    if not trace:
        raise ValueError(f"{fixture_id} full receipt phase trace is missing.")
    runtime_evidence = {
        "schema": COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
        "gate_results": receipt.get("gate_results"),
        "handoff_results": receipt.get("handoff_results"),
    }
    gate_evaluation = evaluate_composition_gates(plan, runtime_evidence)
    handoff_evaluation = evaluate_composition_handoffs(plan, runtime_evidence)
    passed_gate_ids = set(gate_evaluation["passed_gate_ids"])
    available_handoff_ids = set(handoff_evaluation["available_handoff_ids"])
    failed_handoff_ids = set(handoff_evaluation["failed_handoff_ids"])
    current_index = 0
    covered_stage_ids = {expected_stage_ids[0]}
    normalized: list[dict[str, Any]] = []
    for sequence, item in enumerate(trace, start=1):
        _assert_keys(
            item,
            field=f"receipt.phase_trace[{sequence}]",
            required={
                "sequence",
                "from_phase",
                "to_phase",
                "from_stage_id",
                "to_stage_id",
                "requested_phase",
                "status",
                "reason",
                "required_gate_ids",
                "pending_gate_ids",
                "required_handoff_ids",
                "pending_handoff_ids",
                "failed_handoff_ids",
                "override",
            },
        )
        if item.get("sequence") != sequence:
            raise ValueError(
                f"{fixture_id} full receipt phase trace sequence is invalid."
            )
        from_stage_id = _nonempty(
            item.get("from_stage_id"), field=f"receipt.phase_trace[{sequence}].from_stage_id"
        )
        to_stage_id = _nonempty(
            item.get("to_stage_id"), field=f"receipt.phase_trace[{sequence}].to_stage_id"
        )
        if from_stage_id not in stage_index or to_stage_id not in stage_index:
            raise ValueError(f"{fixture_id} full receipt phase trace has an unknown stage.")
        if stage_index[from_stage_id] != current_index:
            raise ValueError(
                f"{fixture_id} full receipt phase trace is not a contiguous compiler lineage."
            )
        from_phase = _nonempty(
            item.get("from_phase"),
            field=f"receipt.phase_trace[{sequence}].from_phase",
        )
        to_phase = _nonempty(
            item.get("to_phase"),
            field=f"receipt.phase_trace[{sequence}].to_phase",
        )
        if from_phase != stage_phase[from_stage_id] or to_phase != stage_phase[to_stage_id]:
            raise ValueError(
                f"{fixture_id} full receipt phase trace phases do not match compiler stages."
            )
        requested_phase = _bounded_text(
            item.get("requested_phase"),
            field=f"receipt.phase_trace[{sequence}].requested_phase",
            maximum=MAX_METADATA_CHARS,
        )
        if requested_phase not in set(stage_phase.values()):
            raise ValueError(
                f"{fixture_id} full receipt requested an unknown compiler phase."
            )
        requested_index = _requested_stage_index(
            stages,
            requested_phase=requested_phase,
            current_index=current_index,
        )
        expected_gate_ids, expected_handoff_ids = _transition_obligation_ids(
            plan,
            stages,
            current_index=current_index,
            requested_index=requested_index,
        )
        status = _nonempty(
            item.get("status"), field=f"receipt.phase_trace[{sequence}].status"
        ).lower()
        if item.get("override") is not None or status in {
            "advanced_with_override",
            "reverted",
        }:
            raise ValueError(f"{fixture_id} full receipt cannot use phase overrides.")
        to_index = stage_index[to_stage_id]
        required_gate_ids = _string_list(
            item.get("required_gate_ids"),
            field=f"receipt.phase_trace[{sequence}].required_gate_ids",
            allow_empty=True,
        )
        pending_gate_ids = _string_list(
            item.get("pending_gate_ids"),
            field=f"receipt.phase_trace[{sequence}].pending_gate_ids",
            allow_empty=True,
        )
        required_handoff_ids = _string_list(
            item.get("required_handoff_ids"),
            field=f"receipt.phase_trace[{sequence}].required_handoff_ids",
            allow_empty=True,
        )
        pending_handoff_ids = _string_list(
            item.get("pending_handoff_ids"),
            field=f"receipt.phase_trace[{sequence}].pending_handoff_ids",
            allow_empty=True,
        )
        trace_failed_handoff_ids = _string_list(
            item.get("failed_handoff_ids"),
            field=f"receipt.phase_trace[{sequence}].failed_handoff_ids",
            allow_empty=True,
        )
        if required_gate_ids != expected_gate_ids:
            raise ValueError(
                f"{fixture_id} full receipt required gates do not match compiler transition."
            )
        if required_handoff_ids != expected_handoff_ids:
            raise ValueError(
                f"{fixture_id} full receipt required handoffs do not match compiler transition."
            )
        expected_pending_gate_ids = [
            gate_id for gate_id in expected_gate_ids if gate_id not in passed_gate_ids
        ]
        expected_pending_handoff_ids = [
            handoff_id
            for handoff_id in expected_handoff_ids
            if handoff_id not in available_handoff_ids
        ]
        expected_failed_handoff_ids = [
            handoff_id
            for handoff_id in expected_handoff_ids
            if handoff_id in failed_handoff_ids
        ]
        if pending_gate_ids != expected_pending_gate_ids:
            raise ValueError(
                f"{fixture_id} full receipt pending gates do not match compiler transition."
            )
        if pending_handoff_ids != expected_pending_handoff_ids:
            raise ValueError(
                f"{fixture_id} full receipt pending handoffs do not match compiler transition."
            )
        if trace_failed_handoff_ids != expected_failed_handoff_ids:
            raise ValueError(
                f"{fixture_id} full receipt failed handoffs do not match compiler transition."
            )
        if status == "advanced":
            if to_index <= current_index:
                raise ValueError(f"{fixture_id} full receipt advanced to an invalid stage.")
            if requested_phase != to_phase:
                raise ValueError(
                    f"{fixture_id} full receipt advanced to a phase other than requested."
                )
            if item.get("reason") != "runtime_evidence_recorded":
                raise ValueError(
                    f"{fixture_id} full receipt advanced without runtime evidence."
                )
            if any(
                (pending_gate_ids, pending_handoff_ids, trace_failed_handoff_ids)
            ):
                raise ValueError(
                    f"{fixture_id} full receipt advanced with unresolved obligations."
                )
            if not set(required_gate_ids).issubset(passed_gate_ids):
                raise ValueError(
                    f"{fixture_id} full receipt advanced without passing required gates."
                )
            if not set(required_handoff_ids).issubset(available_handoff_ids):
                raise ValueError(
                    f"{fixture_id} full receipt advanced without available required handoffs."
                )
            current_index = to_index
        elif status in {"blocked", "unchanged"}:
            if to_index != current_index:
                raise ValueError(
                    f"{fixture_id} full receipt {status} trace changed stage."
                )
            if status == "unchanged" and requested_index != current_index:
                raise ValueError(
                    f"{fixture_id} full receipt left a requested transition unchanged."
                )
        else:
            raise ValueError(f"{fixture_id} full receipt phase status is invalid.")
        covered_stage_ids.update({from_stage_id, to_stage_id})
        normalized.append(
            {
                "sequence": sequence,
                "from_phase": from_phase,
                "to_phase": to_phase,
                "from_stage_id": from_stage_id,
                "to_stage_id": to_stage_id,
                "status": status,
            }
        )
    if current_index != len(expected_stage_ids) - 1 or set(expected_stage_ids) != covered_stage_ids:
        raise ValueError(f"{fixture_id} full receipt did not complete every compiler stage.")
    return normalized


def _validate_handoff_artifact_refs(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    plan: Mapping[str, Any],
    full_artifact_digest: str,
) -> None:
    """Tie every typed runtime handoff to the host execution artifact."""

    expected_ref = f"artifact:{full_artifact_digest}"
    contracts = {
        str(contract.get("handoff_id") or "")
        for contract in composition_handoff_catalog(plan)
    }
    results = _mapping_list(receipt.get("handoff_results"), field="receipt.handoffs")
    for index, result in enumerate(results, start=1):
        handoff_id = _nonempty(
            result.get("handoff_id"), field=f"receipt.handoffs[{index}].handoff_id"
        )
        if handoff_id not in contracts:
            raise ValueError(f"{fixture_id} full receipt has an unknown handoff.")
        refs = _string_list(
            result.get("evidence_refs"),
            field=f"receipt.handoffs[{index}].evidence_refs",
        )
        if refs != [expected_ref]:
            raise ValueError(
                f"{fixture_id} full receipt handoff evidence must bind the host artifact."
            )


def _validate_full_receipt(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    projection: Mapping[str, Any],
    quality_scores: Mapping[str, Any],
    full_artifact_digest: str,
) -> dict[str, Any]:
    full_variant = projection["full_variant"]
    if not isinstance(full_variant, Mapping):
        raise ValueError("Full-composition control is invalid.")
    plan = projection["plan"]
    if not isinstance(plan, Mapping):
        raise ValueError("Replay composition plan is invalid.")
    _validate_full_receipt_shape(receipt, field=fixture_id)
    if receipt.get("packet_id") not in projection.get("permitted_packet_ids"):
        raise ValueError(f"{fixture_id} full receipt packet_id is outside compiler lineage.")
    if receipt.get("composition_fixture_id") != fixture_id:
        raise ValueError(
            f"{fixture_id} full receipt composition_fixture_id is invalid."
        )
    if receipt.get("recipe_id") != projection.get("composition_plan_id"):
        raise ValueError(f"{fixture_id} full receipt recipe_id must match replay.")
    if receipt.get("task_identity") != projection.get("task_identity"):
        raise ValueError(f"{fixture_id} full receipt task_identity must match replay.")
    if receipt.get("graph_digest") != projection.get("graph_digest"):
        raise ValueError(f"{fixture_id} full receipt graph_digest must match replay.")
    selected = list(projection["selected_skill_ids"])
    expected_source_nodes = [
        next(
            item["source_node_id"]
            for item in projection["source_slices"]
            if item["skill_id"] == skill_id
        )
        for skill_id in selected
    ]
    if receipt.get("selected_skill_ids") != expected_source_nodes:
        raise ValueError(f"{fixture_id} full receipt source selection is invalid.")
    expected_content_digests = sorted(
        {item["content_digest"] for item in projection["source_slices"]}
    )
    if sorted(receipt.get("content_digests") or []) != expected_content_digests:
        raise ValueError(f"{fixture_id} full receipt content digests are invalid.")
    activated_atoms = _string_list(
        receipt.get("activated_atoms"), field=f"{fixture_id}.receipt.activated_atoms"
    )
    permitted_atoms = set(_string_list(
        projection.get("permitted_atoms"), field=f"{fixture_id}.permitted_atoms"
    ))
    if not set(activated_atoms).issubset(permitted_atoms):
        raise ValueError(f"{fixture_id} full receipt activated atoms are invalid.")
    if receipt.get("user_overrides") != []:
        raise ValueError(f"{fixture_id} full receipt must not use user overrides.")
    if receipt.get("outcome") != "passed":
        raise ValueError(f"{fixture_id} full receipt outcome must be passed.")
    if receipt.get("benchmark_control_input_digest") != full_variant.get(
        "input_packet_digest"
    ):
        raise ValueError(f"{fixture_id} full receipt control input binding is invalid.")
    if receipt.get("benchmark_execution_recipe_digest") != full_variant.get(
        "execution_recipe_digest"
    ):
        raise ValueError(f"{fixture_id} full receipt recipe binding is invalid.")
    phase_trace = _validate_phase_trace(
        receipt, fixture_id=fixture_id, plan=plan
    )
    runtime_evidence = {
        "schema": COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
        "gate_results": receipt.get("gate_results"),
        "handoff_results": receipt.get("handoff_results"),
    }
    gates = evaluate_composition_gates(plan, runtime_evidence)
    if (
        gates["failed_gate_ids"]
        or gates["pending_gate_ids"]
        or gates["unmatched_results"]
    ):
        raise ValueError(f"{fixture_id} full receipt has unresolved composition gates.")
    handoffs = evaluate_composition_handoffs(plan, runtime_evidence)
    if (
        handoffs["failed_handoff_ids"]
        or handoffs["pending_handoff_ids"]
        or handoffs["invalid_contracts"]
        or handoffs["unmatched_results"]
    ):
        raise ValueError(f"{fixture_id} full receipt has unresolved typed handoffs.")
    _validate_handoff_artifact_refs(
        receipt,
        fixture_id=fixture_id,
        plan=plan,
        full_artifact_digest=full_artifact_digest,
    )
    expected_quality = _receipt_quality_metrics(quality_scores)
    receipt_quality = receipt.get("quality_metrics")
    if not isinstance(receipt_quality, Mapping) or any(
        not math.isclose(
            _finite_number(receipt_quality.get(key), field=f"receipt.quality.{key}"),
            value,
            abs_tol=1e-9,
        )
        for key, value in expected_quality.items()
    ):
        raise ValueError(f"{fixture_id} full receipt quality metrics are invalid.")
    compiled = _finite_number(
        projection.get("compiled_context_tokens"), field="projection.compiled_context"
    )
    naive = _finite_number(
        projection.get("naive_context_tokens"), field="projection.naive_context"
    )
    receipt_cost = receipt.get("cost_metrics")
    if (
        not isinstance(receipt_cost, Mapping)
        or not math.isclose(
            _finite_number(receipt_cost.get("context_tokens"), field="receipt.context"),
            compiled,
            abs_tol=1e-9,
        )
        or not math.isclose(
            _finite_number(receipt_cost.get("context_ratio"), field="receipt.ratio"),
            round(compiled / naive, 4),
            abs_tol=1e-9,
        )
    ):
        raise ValueError(f"{fixture_id} full receipt context metrics are invalid.")
    return {
        "phase_trace": phase_trace,
        "gates": gates,
        "handoffs": handoffs,
        "activated_atoms": activated_atoms,
    }


def _receipt_projection(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    projection: Mapping[str, Any],
    receipt_validation: Mapping[str, Any],
    quality_scores: Mapping[str, Any],
    full_artifact_digest: str,
) -> dict[str, Any]:
    """Persist only compiler-derived receipt fields and bounded runtime outcomes."""

    gates = receipt_validation["gates"]
    handoffs = receipt_validation["handoffs"]
    if not isinstance(gates, Mapping) or not isinstance(handoffs, Mapping):
        raise ValueError("Receipt validation did not produce structured runtime evidence.")
    expected_ref = f"artifact:{full_artifact_digest}"
    expected_quality = _receipt_quality_metrics(quality_scores)
    compiled = _finite_number(
        projection.get("compiled_context_tokens"), field="projection.compiled_context"
    )
    naive = _finite_number(
        projection.get("naive_context_tokens"), field="projection.naive_context"
    )
    return {
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
        "content_digests": sorted(
            {item["content_digest"] for item in projection["source_slices"]}
        ),
        "selected_skill_ids": [
            item["source_node_id"]
            for skill_id in projection["selected_skill_ids"]
            for item in projection["source_slices"]
            if item["skill_id"] == skill_id
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
        "composition_fixture_id": fixture_id,
        "benchmark_control_input_digest": projection["full_variant"]["input_packet_digest"],
        "benchmark_execution_recipe_digest": projection["full_variant"][
            "execution_recipe_digest"
        ],
        "host_receipt_digest": stable_digest(dict(receipt)),
        "host_artifact_digest": full_artifact_digest,
    }


def _behavioral_observation(
    fixture: Mapping[str, Any],
    control: Mapping[str, Any],
    host_variants: Mapping[str, Mapping[str, Any]],
    evaluation: Mapping[str, Any],
    evaluator_variants: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    projection = _behavioral_projection(fixture, control)
    selected = list(projection["selected_skill_ids"])
    quality_scores, dimension_scores = _quality_from_evaluation(
        fixture,
        selected_skill_ids=selected,
        variants=evaluator_variants,
    )
    controls = _indexed(
        _mapping_list(control.get("variants"), field="control.variants"),
        field="control.variants",
        id_field="variant_id",
        expected=required_behavioral_variants(selected),
    )
    execution_manifest: list[dict[str, Any]] = []
    evidence_manifest: list[dict[str, str]] = []
    variant_evidence: dict[str, list[str]] = {}
    variant_dimension_evidence: dict[str, dict[str, list[dict[str, Any]]]] = {}
    full_receipt = host_variants["full_composition"].get("tmcp_run_receipt")
    if not isinstance(full_receipt, Mapping):
        raise ValueError("Full-composition host result is missing a TMCP receipt.")
    full_artifact = _untrusted_text(
        host_variants["full_composition"].get("artifact"),
        field="host.full_composition.artifact",
        maximum=MAX_ARTIFACT_CHARS,
        allowed_literals=_control_literals(controls["full_composition"]),
    )
    full_artifact_digest = stable_digest(full_artifact)
    receipt_validation = _validate_full_receipt(
        full_receipt,
        fixture_id=str(projection["fixture_id"]),
        projection=projection,
        quality_scores=quality_scores,
        full_artifact_digest=full_artifact_digest,
    )
    persisted_receipt = _receipt_projection(
        full_receipt,
        fixture_id=str(projection["fixture_id"]),
        projection=projection,
        receipt_validation=receipt_validation,
        quality_scores=quality_scores,
        full_artifact_digest=full_artifact_digest,
    )
    rubric = _rubric(fixture, field=str(projection["fixture_id"]))
    dimension_requirements = {
        _nonempty(item.get("dimension_id"), field="rubric.dimension_id"): _string_list(
            item.get("evidence_required"), field="rubric.evidence_required"
        )
        for item in _mapping_list(rubric.get("dimensions"), field="rubric.dimensions")
    }
    for variant_id in sorted(controls):
        variant_control = controls[variant_id]
        host = host_variants[variant_id]
        evaluator = evaluator_variants[variant_id]
        raw_evidence = _raw_evidence(
            evaluator.get("evidence"),
            field=f"evaluator.{variant_id}.evidence",
            require_ids=True,
            allowed_literals=_control_literals(variant_control),
        )
        dimension_evidence = _dimension_evidence_bindings(
            evaluator.get("dimension_evidence"),
            expected_requirements=dimension_requirements,
            evidence_ids={item["evidence_id"] for item in raw_evidence},
            field=f"evaluator.{variant_id}.dimension_evidence",
        )
        singleton = quality_scores["singletons"]
        leave_one_out = quality_scores["leave_one_out"]
        if variant_id.startswith("singleton:"):
            quality_score = singleton[variant_id.partition(":")[2]]
        elif variant_id.startswith("leave_one_out:"):
            quality_score = leave_one_out[variant_id.partition(":")[2]]
        else:
            quality_score = quality_scores[variant_id]
        execution, evidence = _execution_record(
            variant_id=variant_id,
            input_digest=behavioral_input_digest(fixture, selected, variant_id),
            control_input_digest=_nonempty(
                variant_control.get("input_packet_digest"),
                field=f"control.{variant_id}.input_packet_digest",
            ),
            execution_recipe_digest=_nonempty(
                variant_control.get("execution_recipe_digest"),
                field=f"control.{variant_id}.execution_recipe_digest",
            ),
            artifact=_untrusted_text(
                host.get("artifact"),
                field=f"host.{variant_id}.artifact",
                maximum=MAX_ARTIFACT_CHARS,
                allowed_literals=_control_literals(variant_control),
            ),
            result_digest=execution_result_digest(
                variant_id,
                quality_score,
                dimension_scores[variant_id],
            ),
            run_id=_bounded_text(
                host.get("run_id"),
                field=f"host.{variant_id}.run_id",
                maximum=MAX_METADATA_CHARS,
            ),
            tmcp_run_receipt=(
                persisted_receipt if variant_id == "full_composition" else None
            ),
            evidence_values=raw_evidence,
        )
        execution_manifest.append(execution)
        evidence_manifest.extend(evidence)
        variant_evidence[variant_id] = [item["evidence_id"] for item in evidence]
        evidence_by_raw_id = {
            raw["evidence_id"]: assembled["evidence_id"]
            for raw, assembled in zip(raw_evidence, evidence, strict=True)
        }
        variant_dimension_evidence[variant_id] = {
            dimension_id: [
                {
                    "requirement": binding["requirement"],
                    "evidence_ids": [
                        evidence_by_raw_id[evidence_id]
                        for evidence_id in binding["evidence_ids"]
                    ],
                    "claim": binding["claim"],
                }
                for binding in bindings
            ]
            for dimension_id, bindings in dimension_evidence.items()
        }
    return {
        **{
            key: value
            for key, value in projection.items()
            if key
            not in {"full_variant", "plan", "permitted_packet_ids", "permitted_atoms"}
        },
        "quality_scores": quality_scores,
        "evaluation_provenance": {
            "evaluator_id": evaluation["evaluator_id"],
            "evaluator_version": evaluation["evaluator_version"],
            "evaluation_run_id": evaluation["evaluation_run_id"],
            "evaluated_at": evaluation["evaluated_at"],
            "method": evaluation["method"],
            "rubric_id": rubric["rubric_id"],
            "rubric_version": rubric["version"],
            "rubric_digest": stable_digest(dict(rubric)),
            "variant_evidence": variant_evidence,
            "variant_dimension_scores": dimension_scores,
            "variant_dimension_evidence": variant_dimension_evidence,
        },
        "execution_manifest": execution_manifest,
        "evidence_manifest": evidence_manifest,
        "run_receipt": persisted_receipt,
    }


def _routing_observation(
    case: Mapping[str, Any],
    control: Mapping[str, Any],
    host: Mapping[str, Any],
) -> dict[str, Any]:
    selected = list(control.get("selected_skill_ids") or [])
    raw_evidence = _raw_evidence(
        host.get("evidence"),
        field="host.routing.evidence",
        allowed_literals=_control_literals(control),
    )
    execution, evidence = _execution_record(
        variant_id="routing",
        input_digest=routing_input_digest(case),
        control_input_digest=_nonempty(
            control.get("input_digest"), field="control.input_digest"
        ),
        execution_recipe_digest=None,
        artifact=_untrusted_text(
            host.get("artifact"),
            field="host.routing.artifact",
            maximum=MAX_ARTIFACT_CHARS,
            allowed_literals=_control_literals(control),
        ),
        result_digest=stable_digest({"selected_skill_ids": selected}),
        run_id=_bounded_text(
            host.get("run_id"),
            field="host.routing.run_id",
            maximum=MAX_METADATA_CHARS,
        ),
        tmcp_run_receipt=None,
        evidence_values=raw_evidence,
    )
    return {
        "case_id": case["case_id"],
        "selected_skill_ids": selected,
        "execution_manifest": [execution],
        "evidence_manifest": evidence,
    }


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


def _validate_projection(
    observations: Mapping[str, Any],
    *,
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
    control_plan: Mapping[str, Any],
) -> None:
    routing_cases = _indexed(
        _mapping_list(routing_golden.get("cases"), field="routing.cases"),
        field="routing.cases",
        id_field="case_id",
        expected={
            _nonempty(item.get("case_id"), field="routing.case_id")
            for item in _mapping_list(
                routing_golden.get("cases"), field="routing.cases"
            )
        },
    )
    fixtures = _indexed(
        _mapping_list(behavioral_fixtures.get("fixtures"), field="fixtures"),
        field="fixtures",
        id_field="fixture_id",
        expected={
            _nonempty(item.get("fixture_id"), field="fixture.fixture_id")
            for item in _mapping_list(
                behavioral_fixtures.get("fixtures"), field="fixtures"
            )
        },
    )
    routing_controls, behavioral_controls = _control_indexes(control_plan)
    routing = _indexed(
        _mapping_list(
            observations.get("routing_results"), field="observations.routing"
        ),
        field="observations.routing",
        id_field="case_id",
        expected=set(routing_controls),
    )
    for case_id, observed in routing.items():
        control = routing_controls[case_id]
        if observed.get("selected_skill_ids") != control.get("selected_skill_ids"):
            raise ValueError(f"{case_id} routing selection is not compiler-derived.")
        records = _mapping_list(
            observed.get("execution_manifest"), field=f"{case_id}.execution_manifest"
        )
        if len(records) != 1 or records[0].get("control_input_digest") != control.get(
            "input_digest"
        ):
            raise ValueError(
                f"{case_id} routing execution is not bound to its control."
            )
        if records[0].get("input_digest") != routing_input_digest(
            routing_cases[case_id]
        ):
            raise ValueError(f"{case_id} routing legacy input binding is invalid.")
    behavioral = _indexed(
        _mapping_list(
            observations.get("behavioral_results"), field="observations.behavioral"
        ),
        field="observations.behavioral",
        id_field="fixture_id",
        expected=set(behavioral_controls),
    )
    for fixture_id, observed in behavioral.items():
        expected = _behavioral_projection(
            fixtures[fixture_id], behavioral_controls[fixture_id]
        )
        for key in (
            "preflight_id",
            "composition_plan_id",
            "graph_digest",
            "task_identity",
            "selected_skill_ids",
            "source_slices",
            "ordered_skill_ids",
            "active_stages",
            "relationships",
            "compiled_context_tokens",
            "naive_context_tokens",
        ):
            if observed.get(key) != expected.get(key):
                raise ValueError(f"{fixture_id}.{key} is not compiler-derived.")
        variants = _indexed(
            _mapping_list(
                behavioral_controls[fixture_id].get("variants"),
                field=f"control.{fixture_id}.variants",
            ),
            field=f"control.{fixture_id}.variants",
            id_field="variant_id",
            expected=required_behavioral_variants(expected["selected_skill_ids"]),
        )
        records = _indexed(
            _mapping_list(
                observed.get("execution_manifest"),
                field=f"{fixture_id}.execution_manifest",
            ),
            field=f"{fixture_id}.execution_manifest",
            id_field="variant_id",
            expected=set(variants),
        )
        for variant_id, record in records.items():
            variant = variants[variant_id]
            if record.get("control_input_digest") != variant.get("input_packet_digest"):
                raise ValueError(f"{fixture_id}.{variant_id} control input is invalid.")
            if record.get("execution_recipe_digest") != variant.get(
                "execution_recipe_digest"
            ):
                raise ValueError(
                    f"{fixture_id}.{variant_id} recipe binding is invalid."
                )


def validate_assembled_benchmark_observations(
    observations: Mapping[str, Any],
    *,
    run_plan: Mapping[str, Any],
    semantic_proposals: Mapping[str, Any],
    control_plan: Mapping[str, Any],
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
    host_results: Mapping[str, Any],
    evaluator_artifacts: Mapping[str, Any],
) -> None:
    """Require exact reassembly from the raw host/evaluator evidence bundles.

    A binding digest alone is only self-consistent data unless the named raw
    bundles are present.  Reassembly is intentionally the public validation
    API so direct callers receive the same fail-closed guarantee as the CLI.
    """

    expected = assemble_benchmark_observations(
        run_plan=run_plan,
        semantic_proposals=semantic_proposals,
        control_plan=control_plan,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
        host_results=host_results,
        evaluator_artifacts=evaluator_artifacts,
    )
    if dict(observations) != expected:
        raise ValueError(
            "observations do not exactly match compiler-bound host/evaluator assembly."
        )


def assemble_benchmark_observations(
    *,
    run_plan: Mapping[str, Any],
    semantic_proposals: Mapping[str, Any],
    control_plan: Mapping[str, Any],
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
    host_results: Mapping[str, Any],
    evaluator_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive observations from replay controls plus bounded host/evaluator facts."""

    for field, payload in (
        ("benchmark run plan", run_plan),
        ("semantic proposal bundle", semantic_proposals),
        ("benchmark control plan", control_plan),
        ("routing golden", routing_golden),
        ("behavioral fixtures", behavioral_fixtures),
        ("host results", host_results),
        ("evaluator artifacts", evaluator_artifacts),
    ):
        _serialized_size(payload, field=field)
    if control_plan.get("schema") != BENCHMARK_CONTROL_PLAN_SCHEMA:
        raise ValueError(
            f"control_plan.schema must be {BENCHMARK_CONTROL_PLAN_SCHEMA}."
        )
    validate_benchmark_run_plan(
        run_plan,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    validate_benchmark_control_plan(
        control_plan,
        run_plan=run_plan,
        semantic_proposals=semantic_proposals,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    routing_host, behavioral_host = _validate_host_results(
        host_results,
        control_plan=control_plan,
    )
    evaluator = _validate_evaluator_artifacts(
        evaluator_artifacts,
        control_plan=control_plan,
        behavioral_fixtures=behavioral_fixtures,
        host_variants=behavioral_host,
    )
    routing_cases = _indexed(
        _mapping_list(routing_golden.get("cases"), field="routing.cases"),
        field="routing.cases",
        id_field="case_id",
        expected=set(routing_host),
    )
    fixtures = _indexed(
        _mapping_list(behavioral_fixtures.get("fixtures"), field="fixtures"),
        field="fixtures",
        id_field="fixture_id",
        expected=set(behavioral_host),
    )
    routing_controls, behavioral_controls = _control_indexes(control_plan)
    routing_results = [
        _routing_observation(
            routing_cases[case_id],
            routing_controls[case_id],
            routing_host[case_id],
        )
        for case_id in routing_controls
    ]
    behavioral_results = [
        _behavioral_observation(
            fixtures[fixture_id],
            behavioral_controls[fixture_id],
            behavioral_host[fixture_id],
            evaluator[fixture_id][0],
            evaluator[fixture_id][1],
        )
        for fixture_id in behavioral_controls
    ]
    raw_observations: dict[str, Any] = {
        "schema": OBSERVATIONS_SCHEMA,
        "routing_results": routing_results,
        "behavioral_results": behavioral_results,
    }
    observations = {
        **raw_observations,
        "benchmark_binding": _binding(
            run_plan=run_plan,
            semantic_proposals=semantic_proposals,
            control_plan=control_plan,
            host_results=host_results,
            evaluator_artifacts=evaluator_artifacts,
            observations=raw_observations,
        ),
    }
    _validate_projection(
        observations,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
        control_plan=control_plan,
    )
    score_composition_benchmark(
        golden_cases=_mapping_list(routing_golden.get("cases"), field="routing.cases"),
        fixture_definitions=_mapping_list(
            behavioral_fixtures.get("fixtures"), field="behavioral.fixtures"
        ),
        routing_results=routing_results,
        behavioral_results=behavioral_results,
    )
    _serialized_size(observations, field="benchmark observations")
    return observations
