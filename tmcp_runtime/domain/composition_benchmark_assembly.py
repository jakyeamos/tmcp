"""Compatibility facade for compiler-bound composition benchmark assembly."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.composition_benchmark_boundaries import (
    BENCHMARK_BINDING_SCHEMA,
    EVALUATOR_ARTIFACTS_SCHEMA,
    HOST_RESULTS_SCHEMA,
    MAX_ARTIFACT_CHARS,
    MAX_BENCHMARK_ARTIFACT_BYTES,
    MAX_EVIDENCE_CHARS,
    MAX_EVIDENCE_ITEMS,
    MAX_METADATA_CHARS,
    MAX_SOURCE_SLICE_CHARS,
    OBSERVATIONS_SCHEMA,
    UTC_TIMESTAMP_RE,
    _binding,
    _bounded_text,
    _control_indexes,
    _control_literals,
    _finite_number,
    _indexed,
    _mapping_list,
    _nonempty,
    _serialized_size,
    _string_list,
    _untrusted_text,
)
from tmcp_runtime.domain.composition_benchmark_evidence import (
    _dimension_evidence_bindings,
    _raw_evidence,
    _rubric,
    _validate_evaluator_artifacts,
    _validate_host_results,
)
from tmcp_runtime.domain.composition_benchmark_manifests import (
    behavioral_input_digest,
    execution_result_digest,
    required_behavioral_variants,
    routing_input_digest,
)
from tmcp_runtime.domain.composition_benchmark_projection import (
    _behavioral_projection,
    _execution_record,
    _quality_from_evaluation,
    _receipt_quality_metrics,
)
from tmcp_runtime.domain.composition_benchmark_protocol import (
    validate_benchmark_run_plan,
)
from tmcp_runtime.domain.composition_benchmark_receipts import (
    _validate_full_receipt,
)
from tmcp_runtime.domain.composition_benchmark_receipt_projection import (
    _receipt_projection,
)
from tmcp_runtime.domain.composition_benchmark_replay import (
    BENCHMARK_CONTROL_PLAN_SCHEMA,
    validate_benchmark_control_plan,
)
from tmcp_runtime.domain.composition_benchmarks import score_composition_benchmark
from tmcp_runtime.domain.composition_preflight import stable_digest
def _behavioral_observation(
    fixture: Mapping[str, Any],
    control: Mapping[str, Any],
    host_variants: Mapping[str, Mapping[str, Any]],
    evaluation: Mapping[str, Any],
    evaluator_variants: Mapping[str, Mapping[str, Any]],
    *,
    control_plan_id: str,
    control_plan_digest: str,
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
        fixture_digest=stable_digest(dict(fixture)),
        control_plan_id=control_plan_id,
        control_plan_digest=control_plan_digest,
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
        "context_execution_mode": persisted_receipt["context_execution_mode"],
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
            "context_accounting",
        ):
            if observed.get(key) != expected.get(key):
                raise ValueError(f"{fixture_id}.{key} is not compiler-derived.")
        if observed.get("context_execution_mode") != observed.get("run_receipt", {}).get(
            "context_execution_mode"
        ):
            raise ValueError(f"{fixture_id}.context_execution_mode is not receipt-derived.")
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
            control_plan_id=str(control_plan["control_plan_id"]),
            control_plan_digest=str(control_plan["control_plan_digest"]),
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
