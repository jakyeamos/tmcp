"""Pure evaluator plan construction from safe source DTOs."""

from __future__ import annotations

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

    for source in sources:
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
                "decomposition": decomposition,
                "static_findings": static_findings,
                "variants": variant_entries,
            }
        )
        packet_inclusion_contracts.append(
            {
                "skill_path": source.display_path,
                "expected": packet_inclusion_expectations(decomposition),
            }
        )
        for fixture in task_fixtures:
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
            for variant in variant_entries:
                task_matrix.append(
                    {
                        "task_id": fixture_id,
                        "variant_id": variant["variant_id"],
                        "ablation_section": variant.get("ablation_section"),
                        "skill_path": source.display_path,
                        "prompt": fixture.get("prompt"),
                        "expected_observables": expected_observables,
                        "skill_attachment": variant["content"],
                    }
                )

    return {
        "ok": True,
        "stability": "experimental",
        "schema": EVAL_PLAN_SCHEMA,
        "created_at": created_at,
        "evaluated_skills": [
            {
                "skill_path": item["skill_path"],
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
            "Run each task_matrix row in an isolated agent session.",
            "Attach only the listed skill_attachment for the variant under test.",
            "Record observations using schema tmcp-skill-eval-trace-v0.1.",
            "Prefer structured observations over prose-only transcripts.",
            "Do not auto-promote findings into durable routing state.",
        ],
        "evidence_contract": {
            "trace_schema": "tmcp-skill-eval-trace-v0.1",
            "required_fields": ["task_id", "variant_id", "observations"],
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
                "task_id": "example-task",
                "variant_id": "original",
                "agent": {"name": "unspecified", "model": "unspecified"},
                "observations": [],
                "human_labels": [],
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
