"""Pure evaluator plan construction from safe source DTOs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tmcp_runtime.services.evaluation_packets import packet_inclusion_expectations
from tmcp_runtime.services.evaluation_policy import (
    _observable_contract,
    _variant_payload,
    decompose_skill,
    static_review,
)


EVAL_PLAN_SCHEMA = "tmcp-skill-evaluation-plan-v0.2"
EVAL_PROTOCOL = "tmcp-skill-evaluation-protocol-v0.2"
CAMPAIGN_POLICY_SCHEMA = "tmcp-skill-eval-campaign-policy-v0.1"


def _json_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{_json_digest(value)[:16]}"


def _display_digest(digest: str) -> str:
    return "sha256:" + ".".join(
        digest[index : index + 8] for index in range(0, len(digest), 8)
    )


def displayed_content_digest(text: str) -> str:
    """Return the plan's stable display digest for supplied skill content."""

    return _display_digest(hashlib.sha256(text.encode("utf-8")).hexdigest())


def section_ablation_content(text: str, section_id: str) -> str:
    """Deterministically rebuild a one-section ablation from original content."""

    decomposition = decompose_skill("SKILL.md", text)
    return str(
        _variant_payload("ablated", decomposition, text, section_id).get("content")
        or ""
    )


@dataclass(frozen=True)
class EvaluationSource:
    """Already-bounded and redacted source text for plan construction."""

    display_path: str
    text: str


def normalize_campaign_policy(
    policy: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate and canonicalize an optional runnable campaign contract."""

    if policy is None:
        return None
    if policy.get("schema") != CAMPAIGN_POLICY_SCHEMA:
        raise ValueError("campaign_policy schema does not match.")
    design = policy.get("design")
    if design not in {"baseline_reliability", "causal_contrast"}:
        raise ValueError("campaign_policy design is invalid.")
    raw_configurations = policy.get("runner_configurations")
    if not isinstance(raw_configurations, Sequence) or isinstance(
        raw_configurations, (str, bytes)
    ):
        raise ValueError("campaign_policy runner_configurations must be a list.")
    configurations: list[dict[str, str]] = []
    for item in raw_configurations:
        if not isinstance(item, Mapping):
            raise ValueError("campaign_policy runner configuration is invalid.")
        model = item.get("model")
        effort = item.get("reasoning_effort")
        if (
            not isinstance(model, str)
            or not model.strip()
            or not isinstance(effort, str)
            or not effort.strip()
        ):
            raise ValueError("campaign_policy runner configuration is invalid.")
        configurations.append({"model": model, "reasoning_effort": effort})
    if (
        len(configurations) != 3
        or len({(item["model"], item["reasoning_effort"]) for item in configurations})
        != 3
    ):
        raise ValueError(
            "campaign_policy requires exactly three distinct configurations."
        )
    baseline = policy.get("baseline_reliability")
    if (
        not isinstance(baseline, Mapping)
        or not isinstance(baseline.get("control_variant"), str)
        or not str(baseline["control_variant"]).strip()
        or not isinstance(baseline.get("minimum_control_pass_rate"), (int, float))
        or float(baseline["minimum_control_pass_rate"]) < 0.5
        or not isinstance(
            baseline.get("minimum_per_fixture_control_pass_rate"), (int, float)
        )
        or float(baseline["minimum_per_fixture_control_pass_rate"]) < 0.5
        or baseline.get("require_predeclared_clustered_interval") is not True
    ):
        raise ValueError("campaign_policy baseline_reliability is invalid.")
    fixture_review = policy.get("fixture_review")
    if not isinstance(fixture_review, Mapping) or any(
        fixture_review.get(field) is not True
        for field in (
            "independent_reviewer",
            "prompt_event_directness",
            "bar_skill_expressibility",
        )
    ):
        raise ValueError("campaign_policy fixture_review is invalid.")
    judge = policy.get("judge_configuration")
    if (
        not isinstance(judge, Mapping)
        or not isinstance(judge.get("model"), str)
        or not str(judge["model"]).strip()
        or not isinstance(judge.get("reasoning_effort"), str)
        or not str(judge["reasoning_effort"]).strip()
    ):
        raise ValueError("campaign_policy judge_configuration is invalid.")
    confirmation = policy.get("cross_model_confirmation")
    if (
        not isinstance(confirmation, Mapping)
        or not isinstance(confirmation.get("required"), bool)
        or not isinstance(confirmation.get("minimum_distinct_runner_models"), int)
        or int(confirmation["minimum_distinct_runner_models"]) < 1
        or not isinstance(confirmation.get("minimum_fixture_count_per_model"), int)
        or int(confirmation["minimum_fixture_count_per_model"]) < 1
        or not isinstance(confirmation.get("minimum_repetitions_per_cell"), int)
        or int(confirmation["minimum_repetitions_per_cell"]) < 1
        or not isinstance(confirmation.get("require_directional_replication"), bool)
    ):
        raise ValueError("campaign_policy cross_model_confirmation is invalid.")
    normalized = {
        "schema": CAMPAIGN_POLICY_SCHEMA,
        "design": design,
        "runner_configurations": sorted(
            configurations, key=lambda item: (item["model"], item["reasoning_effort"])
        ),
        "baseline_reliability": {
            "control_variant": str(baseline["control_variant"]),
            "minimum_control_pass_rate": float(baseline["minimum_control_pass_rate"]),
            "minimum_per_fixture_control_pass_rate": float(
                baseline["minimum_per_fixture_control_pass_rate"]
            ),
            "require_predeclared_clustered_interval": True,
        },
        "fixture_review": {
            "independent_reviewer": True,
            "prompt_event_directness": True,
            "bar_skill_expressibility": True,
        },
        "judge_configuration": {
            "model": str(judge["model"]),
            "reasoning_effort": str(judge["reasoning_effort"]),
        },
        "cross_model_confirmation": {
            "required": confirmation["required"],
            "minimum_distinct_runner_models": confirmation[
                "minimum_distinct_runner_models"
            ],
            "minimum_fixture_count_per_model": confirmation[
                "minimum_fixture_count_per_model"
            ],
            "minimum_repetitions_per_cell": confirmation[
                "minimum_repetitions_per_cell"
            ],
            "require_directional_replication": confirmation[
                "require_directional_replication"
            ],
        },
    }
    if (
        normalized["cross_model_confirmation"]["required"]
        and len({item["model"] for item in configurations})
        < normalized["cross_model_confirmation"]["minimum_distinct_runner_models"]
    ):
        raise ValueError("campaign_policy requires more distinct runner models.")
    return normalized


def build_evaluation_plan_from_sources(
    sources: Sequence[EvaluationSource],
    task_fixtures: Sequence[Mapping[str, Any]],
    variants: Sequence[str],
    *,
    anti_patterns: Sequence[Mapping[str, Any]],
    effective_patterns: Sequence[Mapping[str, Any]],
    created_at: str,
    max_matrix_rows: int,
    campaign_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an evaluation plan without filesystem, redaction, or storage access."""

    if not sources:
        raise ValueError("At least one evaluation source is required.")
    if not task_fixtures:
        raise ValueError("At least one task fixture is required.")
    if not variants:
        raise ValueError("At least one evaluation variant is required.")
    if not all(isinstance(variant, str) for variant in variants):
        raise ValueError("Evaluation variants must be strings.")
    if not all(isinstance(fixture, Mapping) for fixture in task_fixtures):
        raise ValueError("Evaluation task fixtures must be objects.")

    normalized_campaign_policy = normalize_campaign_policy(campaign_policy)
    evaluated_skills: list[dict[str, Any]] = []
    task_matrix: list[dict[str, Any]] = []
    observable_contract: list[dict[str, Any]] = []
    guidebook_candidates: list[dict[str, Any]] = []
    packet_inclusion_contracts: list[dict[str, Any]] = []
    matrix_row_ids: set[str] = set()
    pattern_catalog = {
        str(pattern.get("pattern_id")): pattern
        for pattern in (*effective_patterns, *anti_patterns)
        if str(pattern.get("pattern_id") or "")
    }
    source_digests = [
        hashlib.sha256(source.text.encode("utf-8")).hexdigest() for source in sources
    ]
    fixture_digests = [_json_digest(fixture) for fixture in task_fixtures]
    experiment_id = _stable_id(
        "skill-eval",
        {
            "protocol": EVAL_PROTOCOL,
            "source_digests": source_digests,
            "fixture_digests": fixture_digests,
            "variants": list(variants),
            "campaign_policy": normalized_campaign_policy,
        },
    )

    for source_index, source in enumerate(sources):
        skill_digest = source_digests[source_index]
        displayed_skill_digest = _display_digest(skill_digest)
        decomposition = decompose_skill(source.display_path, source.text)
        static_findings = static_review(
            decomposition,
            source.text,
            anti_patterns=anti_patterns,
            effective_patterns=effective_patterns,
        )
        observable_contract.extend(_observable_contract(decomposition, static_findings))
        guidebook_candidates.extend(
            {
                "pattern_id": item["pattern_id"],
                "classification": item["classification"],
                "evidence_level": item["evidence_level"],
                "skill_path": item["skill_path"],
                "message": item["message"],
            }
            for item in static_findings
        )

        variant_entries: list[dict[str, Any]] = []
        for variant_id in variants:
            if variant_id == "ablated":
                variant_entries.extend(
                    _variant_payload(
                        "ablated", decomposition, source.text, section["id"]
                    )
                    for section in decomposition["sections"]
                )
            else:
                variant_entries.append(
                    _variant_payload(variant_id, decomposition, source.text)
                )
        projected_rows = len(task_matrix) + len(task_fixtures) * len(variant_entries)
        if projected_rows > max_matrix_rows:
            raise ValueError(
                "Evaluation task matrix exceeds the maximum row count of "
                f"{max_matrix_rows}."
            )

        evaluated_skills.append(
            {
                "skill_path": source.display_path,
                "skill_digest": displayed_skill_digest,
                "decomposition": decomposition,
                "static_findings": static_findings,
                "variants": variant_entries,
            }
        )
        packet_inclusion_contracts.append(
            {
                "skill_path": source.display_path,
                "skill_digest": displayed_skill_digest,
                "expected": packet_inclusion_expectations(decomposition),
            }
        )
        for fixture_index, fixture in enumerate(task_fixtures):
            fixture_digest = fixture_digests[fixture_index]
            displayed_fixture_digest = _display_digest(fixture_digest)
            fixture_id = str(fixture.get("id") or "")
            if not fixture_id:
                raise ValueError("Each task fixture requires an id.")
            expected_observables = fixture.get("expected_observables") or []
            if not isinstance(expected_observables, list) or not all(
                isinstance(item, str) for item in expected_observables
            ):
                raise ValueError(
                    "Each task fixture expected_observables value must be a list of strings."
                )
            failure_smells = fixture.get("failure_smells") or []
            if not isinstance(failure_smells, list) or not all(
                isinstance(item, str) for item in failure_smells
            ):
                raise ValueError(
                    "Each task fixture failure_smells value must be a list of strings."
                )
            fixture_family = str(fixture.get("fixture_family") or "unspecified")
            pattern_id = str(fixture.get("pattern_id") or "") or None
            supplied_effect_direction = fixture.get("expected_effect_direction")
            intervention_variant = str(
                fixture.get("intervention_variant") or "original"
            )
            control_variant = str(fixture.get("control_variant") or "baseline")
            intervention_target = str(fixture.get("intervention_target") or "") or None
            tested_atom = str(fixture.get("tested_atom") or "") or None
            pattern_definition = pattern_catalog.get(pattern_id or "")
            pattern_interventions = (
                [
                    dict(item)
                    for item in pattern_definition.get("tested_interventions") or []
                    if isinstance(item, Mapping)
                ]
                if isinstance(pattern_definition, Mapping)
                else []
            )
            if pattern_id and pattern_definition is None:
                raise ValueError(f"Unknown evaluation pattern_id: {pattern_id}.")
            if pattern_id and (
                intervention_variant not in variants or control_variant not in variants
            ):
                raise ValueError(
                    "Pattern fixtures require intervention_variant and control_variant "
                    "to be present in variants."
                )
            if pattern_id and (not tested_atom or not intervention_target):
                raise ValueError(
                    "Pattern fixtures require tested_atom and intervention_target."
                )
            matching_pattern_interventions = [
                item
                for item in pattern_interventions
                if str(item.get("tested_atom") or "") == tested_atom
            ]
            if pattern_id and len(matching_pattern_interventions) != 1:
                raise ValueError(
                    f"Pattern {pattern_id} does not declare tested atom {tested_atom}."
                )
            pattern_intervention_contract = (
                {
                    "tested_atom": tested_atom,
                    "allowed_targets": sorted(
                        str(item)
                        for item in matching_pattern_interventions[0].get(
                            "allowed_targets"
                        )
                        or []
                    ),
                    "allowed_kinds": sorted(
                        str(item)
                        for item in matching_pattern_interventions[0].get(
                            "allowed_kinds"
                        )
                        or []
                    ),
                    "claim_granularity": str(
                        matching_pattern_interventions[0].get("claim_granularity") or ""
                    ),
                    "expected_support_direction": str(
                        matching_pattern_interventions[0].get(
                            "expected_support_direction"
                        )
                        or ""
                    ),
                }
                if matching_pattern_interventions
                else None
            )
            if pattern_id:
                if pattern_intervention_contract is None:
                    raise ValueError("Pattern intervention contract is missing.")
                canonical_contract = pattern_intervention_contract
                expected_effect_direction = canonical_contract[
                    "expected_support_direction"
                ]
                if expected_effect_direction not in {"positive", "negative"}:
                    raise ValueError(
                        "Pattern tested_interventions require an "
                        "expected_support_direction of positive or negative."
                    )
                if not canonical_contract["claim_granularity"]:
                    raise ValueError(
                        "Pattern tested_interventions require claim_granularity."
                    )
                if (
                    supplied_effect_direction is not None
                    and str(supplied_effect_direction) != expected_effect_direction
                ):
                    raise ValueError(
                        "Task fixture expected_effect_direction does not match the "
                        "canonical pattern intervention contract."
                    )
            else:
                expected_effect_direction = str(supplied_effect_direction or "positive")
                if expected_effect_direction not in {"positive", "negative"}:
                    raise ValueError(
                        "Each task fixture expected_effect_direction must be positive or negative."
                    )
            if pattern_id:
                if intervention_target not in canonical_contract["allowed_targets"]:
                    raise ValueError(
                        "Pattern intervention_target is not allowed for tested_atom."
                    )
                intervention_entries = [
                    entry
                    for entry in variant_entries
                    if entry.get("variant_id") == intervention_variant
                    and (
                        intervention_variant != "ablated"
                        or entry.get("ablation_section") == intervention_target
                    )
                ]
                if len(intervention_entries) != 1:
                    raise ValueError(
                        "Pattern intervention must identify exactly one variant row."
                    )
                intervention_metadata = intervention_entries[0].get("intervention")
                if not isinstance(intervention_metadata, Mapping):
                    raise ValueError("Pattern intervention metadata is missing.")
                if intervention_metadata.get("kind") == "control":
                    raise ValueError(
                        "A control-kind variant cannot be a pattern intervention."
                    )
                if (
                    intervention_metadata.get("kind")
                    not in canonical_contract["allowed_kinds"]
                ):
                    raise ValueError(
                        "Pattern intervention kind is not allowed for tested_atom."
                    )
                if intervention_metadata.get("causal_attribution") is not True:
                    raise ValueError(
                        "Pattern intervention must be a lossless causal contrast."
                    )
                if (
                    intervention_metadata.get("kind") == "single_section_ablation"
                    and control_variant != "original"
                ):
                    raise ValueError(
                        "A section ablation requires the original skill as its matched control."
                    )
                if str(intervention_metadata.get("target") or "") != str(
                    intervention_target
                ):
                    raise ValueError(
                        "Pattern intervention target does not match the variant target."
                    )
            for variant in variant_entries:
                is_target_intervention = variant.get(
                    "variant_id"
                ) == intervention_variant and (
                    intervention_variant != "ablated"
                    or variant.get("ablation_section") == intervention_target
                )
                is_matched_control = variant.get("variant_id") == control_variant
                is_pattern_contrast_row = bool(pattern_id) and (
                    is_target_intervention or is_matched_control
                )
                contrast_id = (
                    _stable_id(
                        "eval-contrast",
                        {
                            "pattern_id": pattern_id,
                            "skill_path": source.display_path,
                            "skill_digest": skill_digest,
                            "fixture_digest": fixture_digest,
                            "intervention_variant": intervention_variant,
                            "control_variant": control_variant,
                            "intervention_target": intervention_target,
                        },
                    )
                    if is_pattern_contrast_row
                    else None
                )
                matrix_row_id = _stable_id(
                    "eval-row",
                    {
                        "experiment_id": experiment_id,
                        "skill_path": source.display_path,
                        "skill_digest": skill_digest,
                        "fixture_digest": displayed_fixture_digest,
                        "variant_id": variant["variant_id"],
                        "ablation_section": variant.get("ablation_section"),
                    },
                )
                if matrix_row_id in matrix_row_ids:
                    raise ValueError(
                        "Evaluation task matrix contains duplicate experimental rows."
                    )
                matrix_row_ids.add(matrix_row_id)
                variant_content = str(variant.get("content") or "")
                variant_contract = (
                    packet_inclusion_expectations(
                        decompose_skill(source.display_path, variant_content)
                    )
                    if variant_content
                    else {
                        "skill_path": source.display_path,
                        "required_reads": [],
                        "verification_gates": [],
                        "stop_conditions": [],
                        "output_contract": [],
                        "behavior_atoms": [],
                    }
                )
                task_matrix.append(
                    {
                        "experiment_id": experiment_id,
                        "matrix_row_id": matrix_row_id,
                        "task_id": fixture_id,
                        "fixture_family": fixture_family,
                        "fixture_digest": displayed_fixture_digest,
                        "pattern_id": pattern_id if is_pattern_contrast_row else None,
                        "tested_atom": tested_atom if is_pattern_contrast_row else None,
                        "pattern_intervention_contract": (
                            pattern_intervention_contract
                            if is_pattern_contrast_row
                            else None
                        ),
                        "claim_granularity": (
                            pattern_intervention_contract["claim_granularity"]
                            if is_pattern_contrast_row and pattern_intervention_contract
                            else None
                        ),
                        "contrast_id": contrast_id,
                        "expected_effect_direction": (
                            expected_effect_direction
                            if is_pattern_contrast_row
                            else None
                        ),
                        "intervention_variant": intervention_variant,
                        "control_variant": control_variant,
                        "intervention_target": (
                            intervention_target if is_pattern_contrast_row else None
                        ),
                        "variant_id": variant["variant_id"],
                        "ablation_section": variant.get("ablation_section"),
                        "included_slices": list(variant.get("included_slices") or []),
                        "intervention": dict(variant.get("intervention") or {}),
                        "skill_path": source.display_path,
                        "skill_digest": displayed_skill_digest,
                        "prompt": fixture.get("prompt"),
                        "expected_observables": expected_observables,
                        "failure_smells": list(failure_smells),
                        "primary_outcome": fixture.get("primary_outcome")
                        or "case_passed",
                        "expected_packet_contract": variant_contract,
                        "skill_attachment": variant_content,
                    }
                )

    return {
        "ok": True,
        "stability": "experimental",
        "schema": EVAL_PLAN_SCHEMA,
        "created_at": created_at,
        "experiment": {
            "experiment_id": experiment_id,
            "protocol_version": EVAL_PROTOCOL,
            "design": "blind_controlled_skill_variants",
            "blinding": {"runner": True, "judge": True},
            "promotion_thresholds": {
                "dogfooded": {
                    "minimum_traces": 3,
                    "minimum_fixtures": 2,
                },
                "controlled_single_agent_eval": {
                    "minimum_repetitions_per_cell": 2,
                    "minimum_fixtures": 2,
                    "minimum_agent_configurations": 1,
                },
                "controlled_multi_agent_eval": {
                    "minimum_repetitions_per_cell": 2,
                    "minimum_fixtures": 6,
                    "minimum_fixture_families": 3,
                    "minimum_agent_configurations": 3,
                    "minimum_absolute_lift": 0.1,
                    "minimum_control_pass_rate": 0.5,
                    "minimum_per_fixture_control_pass_rate": 0.5,
                },
            },
            "analysis_policy": {
                "clustered_interval": {
                    "method": "fixture_block_bootstrap_by_configuration",
                    "confidence": 0.95,
                    "cluster_unit": "fixture_digest",
                    "resamples": 10_000,
                    "seed": 20_260_717,
                }
            },
            "campaign_policy": normalized_campaign_policy,
        },
        "evaluated_skills": [
            {
                "skill_path": item["skill_path"],
                "skill_digest": item["skill_digest"],
                "title": item["decomposition"]["title"],
                "behavior_atoms": item["decomposition"]["behavior_atoms"],
                "static_findings": item["static_findings"],
                "variant_ids": sorted(
                    {variant["variant_id"] for variant in item["variants"]}
                ),
            }
            for item in evaluated_skills
        ],
        "task_matrix": task_matrix,
        "variants": sorted({entry["variant_id"] for entry in task_matrix}),
        "observable_behavior_contract": _dedupe_observables(observable_contract),
        "packet_inclusion_contracts": packet_inclusion_contracts,
        "runner_instructions": [
            "Run each task_matrix row and repetition in a fresh isolated agent session.",
            "Attach only the listed skill_attachment for the variant under test.",
            "Hide semantic variant labels, the hypothesis, and the grading bar from the runner.",
            "Grade the artifact with a separate judge blinded to the assigned variant.",
            "Record observations using schema tmcp-skill-eval-trace-v0.1.",
            "Prefer structured observations over prose-only transcripts.",
            "Do not auto-promote findings into durable routing state.",
        ],
        "evidence_contract": {
            "trace_schema": "tmcp-skill-eval-trace-v0.1",
            "required_fields": ["task_id", "variant_id", "observations"],
            "controlled_claim_fields": [
                "trace_id",
                "experiment_id",
                "matrix_row_id",
                "replicate_id",
                "agent.configuration_id",
                "provenance.runner_blinded",
                "provenance.judge_blinded",
                "provenance.isolated_session",
                "case_verdict.passed",
                "case_verdict.evidence",
                "case_verdict.safety_regression",
                "case_verdict.cost_regression",
            ],
            "observation_kinds": [
                "file_read",
                "file_write",
                "command_run",
                "assistant_message",
                "tool_call",
                "human_label",
            ],
            "starter_template": {
                "schema": "tmcp-skill-eval-trace-v0.1",
                "trace_id": "trace-example-1",
                "experiment_id": experiment_id,
                "matrix_row_id": "eval-row-from-task-matrix",
                "replicate_id": "replicate-1",
                "task_id": "example-task",
                "variant_id": "original",
                "agent": {
                    "name": "unspecified",
                    "model": "unspecified",
                    "configuration_id": "provider-model-host-version",
                },
                "provenance": {
                    "runner_blinded": True,
                    "judge_blinded": True,
                    "isolated_session": True,
                },
                "observations": [],
                "human_labels": [],
                "case_verdict": {
                    "passed": False,
                    "evidence": [],
                    "safety_regression": False,
                    "cost_regression": False,
                },
            },
        },
        "guidebook_candidate_patterns": guidebook_candidates,
        "promotion_policy": {
            "auto_promote": False,
            "harvest_warnings_only": True,
            "notes": (
                "Evaluation findings are advisory. Harvest may warn or label; "
                "they must not silently rewrite durable routing state."
            ),
        },
    }


def _dedupe_observables(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        observable_id = str(item.get("observable_id") or "")
        if observable_id in seen:
            continue
        seen.add(observable_id)
        result.append(item)
    return result
