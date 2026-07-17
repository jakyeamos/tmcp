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


EVAL_PLAN_SCHEMA = "tmcp-skill-evaluation-plan-v0.1"
EVAL_PROTOCOL = "tmcp-skill-evaluation-protocol-v0.2"


def _json_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{_json_digest(value)[:16]}"


def _display_digest(digest: str) -> str:
    return "sha256:" + ".".join(
        digest[index : index + 8] for index in range(0, len(digest), 8)
    )


@dataclass(frozen=True)
class EvaluationSource:
    """Already-bounded and redacted source text for plan construction."""

    display_path: str
    text: str


def build_evaluation_plan_from_sources(
    sources: Sequence[EvaluationSource],
    task_fixtures: Sequence[Mapping[str, Any]],
    variants: Sequence[str],
    *,
    anti_patterns: Sequence[Mapping[str, Any]],
    effective_patterns: Sequence[Mapping[str, Any]],
    created_at: str,
    max_matrix_rows: int,
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

    evaluated_skills: list[dict[str, Any]] = []
    task_matrix: list[dict[str, Any]] = []
    observable_contract: list[dict[str, Any]] = []
    guidebook_candidates: list[dict[str, Any]] = []
    packet_inclusion_contracts: list[dict[str, Any]] = []
    matrix_row_ids: set[str] = set()
    source_digests = [hashlib.sha256(source.text.encode("utf-8")).hexdigest() for source in sources]
    fixture_digests = [_json_digest(fixture) for fixture in task_fixtures]
    experiment_id = _stable_id(
        "skill-eval",
        {
            "protocol": EVAL_PROTOCOL,
            "source_digests": source_digests,
            "fixture_digests": fixture_digests,
            "variants": list(variants),
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
            intervention_variant = str(
                fixture.get("intervention_variant") or "original"
            )
            control_variant = str(fixture.get("control_variant") or "baseline")
            if pattern_id and (
                intervention_variant not in variants or control_variant not in variants
            ):
                raise ValueError(
                    "Pattern fixtures require intervention_variant and control_variant "
                    "to be present in variants."
                )
            for variant in variant_entries:
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
                        "pattern_id": pattern_id,
                        "intervention_variant": intervention_variant,
                        "control_variant": control_variant,
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
                },
            },
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
                "case_verdict": {"passed": False, "evidence": []},
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
