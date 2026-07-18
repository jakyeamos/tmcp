"""Validate bounded host and evaluator evidence for composition benchmarks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.composition_benchmark_boundaries import (
    EVALUATOR_ARTIFACTS_SCHEMA,
    HOST_RESULTS_SCHEMA,
    MAX_ARTIFACT_CHARS,
    MAX_EVIDENCE_CHARS,
    MAX_EVIDENCE_ITEMS,
    MAX_METADATA_CHARS,
    UTC_TIMESTAMP_RE,
    _assert_keys,
    _bounded_text,
    _control_indexes,
    _control_literals,
    _finite_number,
    _indexed,
    _mapping_list,
    _nonempty,
    _string_list,
    _untrusted_text,
    _validate_header,
)
from tmcp_runtime.domain.composition_benchmark_receipts import (
    _validate_full_receipt_shape,
)
from tmcp_runtime.domain.composition_preflight import stable_digest


HOST_EXECUTED_EVIDENCE_CLASS = "host_executed"
SYNTHETIC_TEST_EVIDENCE_CLASS = "synthetic_test"
TRUSTED_EVALUATOR_EXECUTION_CLASS = "trusted_evaluator_execution"
_HOST_EVIDENCE_CLASSES = frozenset(
    {HOST_EXECUTED_EVIDENCE_CLASS, SYNTHETIC_TEST_EVIDENCE_CLASS}
)
_EVALUATOR_EXECUTION_CLASSES = frozenset(
    {TRUSTED_EVALUATOR_EXECUTION_CLASS, SYNTHETIC_TEST_EVIDENCE_CLASS}
)
_TEST_ONLY_EVALUATOR_METHODS = frozenset(
    {"deterministic-test-rubric", "synthetic_unit_test"}
)


def _host_evidence_class(value: object, *, field: str) -> str:
    evidence_class = _bounded_text(value, field=field, maximum=MAX_METADATA_CHARS)
    if evidence_class not in _HOST_EVIDENCE_CLASSES:
        raise ValueError(f"{field} must be one of {sorted(_HOST_EVIDENCE_CLASSES)}.")
    return evidence_class


def _evaluator_execution_metadata(
    value: object,
    *,
    field: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    _assert_keys(
        value,
        field=field,
        required={"execution_class", "executor_id", "execution_id", "executed_at"},
    )
    execution_class = _bounded_text(
        value.get("execution_class"),
        field=f"{field}.execution_class",
        maximum=MAX_METADATA_CHARS,
    )
    if execution_class not in _EVALUATOR_EXECUTION_CLASSES:
        raise ValueError(
            f"{field}.execution_class must be one of "
            f"{sorted(_EVALUATOR_EXECUTION_CLASSES)}."
        )
    executed_at = _bounded_text(
        value.get("executed_at"),
        field=f"{field}.executed_at",
        maximum=MAX_METADATA_CHARS,
    )
    if UTC_TIMESTAMP_RE.fullmatch(executed_at) is None:
        raise ValueError(f"{field}.executed_at must be a UTC timestamp.")
    return {
        "execution_class": execution_class,
        "executor_id": _untrusted_text(
            value.get("executor_id"),
            field=f"{field}.executor_id",
            maximum=MAX_METADATA_CHARS,
        ),
        "execution_id": _untrusted_text(
            value.get("execution_id"),
            field=f"{field}.execution_id",
            maximum=MAX_METADATA_CHARS,
        ),
        "executed_at": executed_at,
    }


def validate_release_benchmark_evidence_admissibility(
    *,
    host_results: Mapping[str, Any],
    evaluator_artifacts: Mapping[str, Any],
) -> None:
    """Reject contract-test evidence from the CLI and release proof boundary.

    Raw benchmark records remain advisory, so this is not an attestation system.
    It does make evidence origin an explicit, bounded declaration and prevents
    the known synthetic contract fixtures from being replayed as release proof.
    """

    evidence_class = _host_evidence_class(
        host_results.get("evidence_class"),
        field="host_results.evidence_class",
    )
    if evidence_class != HOST_EXECUTED_EVIDENCE_CLASS:
        raise ValueError(
            "release benchmark host_results.evidence_class must be "
            f"{HOST_EXECUTED_EVIDENCE_CLASS}; {SYNTHETIC_TEST_EVIDENCE_CLASS} "
            "is unit-test-only."
        )
    execution = _evaluator_execution_metadata(
        evaluator_artifacts.get("evaluator_execution"),
        field="evaluator_artifacts.evaluator_execution",
    )
    if execution["execution_class"] != TRUSTED_EVALUATOR_EXECUTION_CLASS:
        raise ValueError(
            "release benchmark evaluator_artifacts.evaluator_execution."
            "execution_class must be "
            f"{TRUSTED_EVALUATOR_EXECUTION_CLASS}; "
            f"{SYNTHETIC_TEST_EVIDENCE_CLASS} is unit-test-only."
        )
    evaluations = _mapping_list(
        evaluator_artifacts.get("fixture_evaluations"),
        field="evaluator_artifacts.fixture_evaluations",
    )
    for index, evaluation in enumerate(evaluations, start=1):
        method = _bounded_text(
            evaluation.get("method"),
            field=(f"evaluator_artifacts.fixture_evaluations[{index}].method"),
            maximum=MAX_METADATA_CHARS,
        )
        if method in _TEST_ONLY_EVALUATOR_METHODS:
            raise ValueError(
                f"release benchmark evaluator method is test-only: {method}."
            )


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
        entries = _mapping_list(
            value.get(dimension_id), field=f"{field}.{dimension_id}"
        )
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
        required_fields={"evidence_class"},
    )
    _host_evidence_class(
        host_results.get("evidence_class"),
        field="host_results.evidence_class",
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
        required_fields={"evaluator_execution"},
    )
    _evaluator_execution_metadata(
        evaluator_artifacts.get("evaluator_execution"),
        field="evaluator_artifacts.evaluator_execution",
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
