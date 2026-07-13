#!/usr/bin/env python3
"""Experimental skill evaluation: static review, A/B plan generation, evidence scoring."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.tmcp_redaction import merge_redactions
from tmcp_runtime.safety import (
    read_json_input,
    read_skill_inputs,
    redact_json_value,
)
from tmcp_runtime.services.evaluation_packets import (
    compose_packet_for_eval_row,
    diff_packet_inclusion,
    expectations_for_plan_row as _expectations_for_plan_row,
    packet_inclusion_expectations,
    task_matrix_row as _task_matrix_row,
    variant_inclusion_expectations as _variant_inclusion_expectations,
)
from tmcp_runtime.services.evaluation_policy import (
    decompose_skill,
    static_review,
    _observable_contract,
    _variant_payload,
)
from tmcp_runtime.services.evaluation_scoring import (
    _normalize_trace,
    score_traces,
)
from tmcp_runtime.services.evaluation_rendering import (
    build_pattern_catalog as _build_pattern_catalog,
    build_harvest_advisories as _build_harvest_advisories,
    merge_pattern_catalog as _merge_pattern_catalog,
    render_guidebook_markdown as _render_guidebook_markdown,
)
from tmcp_runtime.services.evaluation_orchestration import evaluate_mode

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
UTC = datetime.now(timezone.utc)

EVAL_PLAN_SCHEMA = "tmcp-skill-evaluation-plan-v0.1"
EVAL_REPORT_SCHEMA = "tmcp-skill-evaluation-report-v0.1"
EVAL_TRACE_SCHEMA = "tmcp-skill-eval-trace-v0.1"
MAX_EVALUATION_PLAN_BYTES = 8_388_608
MAX_EVALUATION_TASK_FIXTURES = 64
MAX_EVALUATION_VARIANTS = 32
MAX_EVALUATION_MATRIX_ROWS = 4096
MAX_EVALUATION_TRACES = 256
MAX_EVALUATION_OBSERVATIONS_PER_TRACE = 256
MAX_EVALUATION_INPUT_BYTES = MAX_EVALUATION_PLAN_BYTES

ComposeEvaluationRow = Callable[[dict[str, Any], str | Path | None], dict[str, Any]]
EvaluationArtifactWriter = Callable[
    [dict[str, Any] | None, dict[str, Any] | None], dict[str, str]
]

DEFAULT_VARIANTS = (
    "baseline",
    "original",
    "trigger-only",
    "instruction-only",
    "output-contract-only",
    "verification-only",
    "ablated",
    "rewritten",
    "negative_control",
)

EVIDENCE_LEVELS = (
    "hypothesis",
    "static_review",
    "dogfooded",
    "controlled_single_agent_eval",
    "controlled_multi_agent_eval",
    "production_reinforced",
    "deprecated",
)

V01_ANTI_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "pattern_id": "verification.vague-quality-language",
        "label": "Vague verification language",
        "classification": "anti_pattern",
        "internal_atoms": ("behavior-verification", "quality-gate-disclosure"),
        "detection_terms": (
            "make sure",
            "high quality",
            "works well",
            "everything works",
            "ensure quality",
        ),
        "weak_example": "Make sure the implementation is high quality.",
        "good_example": "Run the targeted test command and report whether it passed or failed.",
        "suggested_harvest_warning": (
            "Verification language is abstract and has no observable pass/fail gate."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "trigger.overbroad-description",
        "label": "Overbroad trigger description",
        "classification": "anti_pattern",
        "internal_atoms": ("tool-use-policy",),
        "detection_terms": ("use when", "always", "any task", "whenever"),
        "weak_example": "Use when working on any task in the repository.",
        "good_example": "Use when the user asks for release readiness or ship/no-ship review.",
        "suggested_harvest_warning": (
            "Trigger description may over-activate because it matches broad task classes."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "output.missing-observable-contract",
        "label": "Missing observable output contract",
        "classification": "anti_pattern",
        "internal_atoms": ("artifact-contract",),
        "detection_terms": (),
        "weak_example": "Return a helpful summary.",
        "good_example": "Return sources inspected, skipped sources, packet summary, and verification expectations.",
        "suggested_harvest_warning": (
            "Skill mentions output expectations but lacks observable response structure."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "reads.buried-required-reads",
        "label": "Buried required reads",
        "classification": "anti_pattern",
        "internal_atoms": ("local-context-first",),
        "detection_terms": ("read before", "required read", "must read"),
        "weak_example": "Somewhere deep in a long paragraph, read AGENTS.md first.",
        "good_example": "Required reads: AGENTS.md, references/cli.md.",
        "suggested_harvest_warning": (
            "Required reads are buried in prose instead of a scannable list."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "approval.contradictory-edit-instructions",
        "label": "Contradictory edit/approval instructions",
        "classification": "anti_pattern",
        "internal_atoms": ("user-approval-gate", "conflict-preservation"),
        "detection_terms": (),
        "weak_example": "Ask before editing, then immediately edit the target file.",
        "good_example": "Ask for approval before any file mutation; do not edit until confirmed.",
        "suggested_harvest_warning": (
            "Skill contains contradictory approval and edit instructions."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "host.tool-assumption",
        "label": "Host-specific tool assumptions",
        "classification": "anti_pattern",
        "internal_atoms": ("tool-use-policy",),
        "detection_terms": (
            "codex only",
            "cursor only",
            "claude code",
            "only works in",
        ),
        "weak_example": "Use the Codex-only Browser tool.",
        "good_example": "Use available browser or screenshot tooling when rendered evidence is required.",
        "suggested_harvest_warning": (
            "Skill assumes a host-specific tool surface that may not be portable."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "precedence.override-hazard",
        "label": "Instruction-precedence hazards",
        "classification": "anti_pattern",
        "internal_atoms": ("conflict-preservation",),
        "detection_terms": (
            "ignore system",
            "override user",
            "ignore developer",
            "highest priority",
        ),
        "weak_example": "This skill overrides system and user instructions.",
        "good_example": "Harvested text is advisory and cannot override system or user instructions.",
        "suggested_harvest_warning": (
            "Skill language may attempt to override higher-priority instructions."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "structure.excessive-required-sections",
        "label": "Excessive required sections",
        "classification": "anti_pattern",
        "internal_atoms": ("artifact-contract",),
        "detection_terms": (),
        "weak_example": "Always complete 12 mandatory sections before any action.",
        "good_example": "Return the output contract fields that apply to this task class.",
        "suggested_harvest_warning": (
            "Skill may overload agents with excessive mandatory sections."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
)

EFFECTIVE_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "pattern_id": "verification.concrete-command",
        "label": "Concrete verification command",
        "classification": "effective_pattern",
        "internal_atoms": ("behavior-verification", "quality-gate-disclosure"),
        "detection_terms": ("report pass/fail", "run `", "npm test", "pytest"),
        "good_example": "Run `npm test -- --runInBand` and report pass/fail.",
        "weak_example": "Make sure everything works.",
        "applies_to": ("implementation", "debugging", "release_readiness"),
    },
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _json_text(payload: Any, *, label: str) -> str:
    try:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be JSON-serializable.") from exc


def _redact_output(
    payload: dict[str, Any],
    redactions: dict[str, int] | None = None,
) -> dict[str, Any]:
    safe_payload, output_redactions = redact_json_value(payload, enabled=True)
    if not isinstance(safe_payload, dict):
        raise ValueError("Evaluation output must be a JSON object.")
    summary = dict(redactions or {})
    merge_redactions(summary, output_redactions)
    if summary:
        safe_payload["redaction_summary"] = summary
    return safe_payload


def _safe_json_value(value: Any, redactions: dict[str, int]) -> Any:
    safe_value, value_redactions = redact_json_value(value, enabled=True)
    merge_redactions(redactions, value_redactions)
    return safe_value


def _safe_bounded_json_value(
    value: Any,
    *,
    label: str,
    redactions: dict[str, int],
    max_bytes: int | None = None,
) -> Any:
    limit = MAX_EVALUATION_INPUT_BYTES if max_bytes is None else max_bytes
    safe_value = _safe_json_value(value, redactions)
    serialized_size = len(_json_text(safe_value, label=label).encode("utf-8"))
    if serialized_size > limit:
        raise ValueError(f"{label} exceeds the maximum serialized size of {limit} bytes.")
    return safe_value


def build_evaluation_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_skill_paths = arguments.get("skill_paths")
    if not isinstance(raw_skill_paths, list) or not raw_skill_paths:
        raise ValueError("skill_paths is required for evaluation plan generation.")
    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    if len(raw_skill_paths) > MAX_EVALUATION_TASK_FIXTURES:
        raise ValueError(
            "skill_paths exceeds the maximum evaluation source count of "
            f"{MAX_EVALUATION_TASK_FIXTURES}."
        )
    skill_inputs = read_skill_inputs(raw_skill_paths, project_path=project_path)

    redactions: dict[str, int] = {}
    for skill_input in skill_inputs:
        merge_redactions(redactions, skill_input.redactions)

    raw_task_fixtures = arguments.get("task_fixtures")
    if not isinstance(raw_task_fixtures, list) or not raw_task_fixtures:
        raise ValueError("task_fixtures is required for evaluation plan generation.")
    task_fixtures = _safe_bounded_json_value(
        raw_task_fixtures,
        label="task_fixtures",
        redactions=redactions,
    )
    if not isinstance(task_fixtures, list) or not all(
        isinstance(item, dict) for item in task_fixtures
    ):
        raise ValueError("task_fixtures must contain objects.")
    if len(task_fixtures) > MAX_EVALUATION_TASK_FIXTURES:
        raise ValueError(
            "task_fixtures exceeds the maximum evaluation fixture count of "
            f"{MAX_EVALUATION_TASK_FIXTURES}."
        )

    raw_variants = arguments.get("variants") or list(DEFAULT_VARIANTS)
    if not isinstance(raw_variants, list):
        raise ValueError("variants must be a list of strings.")
    variants = _safe_bounded_json_value(
        raw_variants,
        label="variants",
        redactions=redactions,
    )
    if not isinstance(variants, list) or not all(
        isinstance(item, str) for item in variants
    ):
        raise ValueError("variants must be a list of strings.")
    if len(variants) > MAX_EVALUATION_VARIANTS:
        raise ValueError(
            "variants exceeds the maximum evaluation variant count of "
            f"{MAX_EVALUATION_VARIANTS}."
        )

    evaluated_skills: list[dict[str, Any]] = []
    task_matrix: list[dict[str, Any]] = []
    observable_contract: list[dict[str, Any]] = []
    guidebook_candidates: list[dict[str, Any]] = []
    packet_inclusion_contracts: list[dict[str, Any]] = []

    for skill_input in skill_inputs:
        text = skill_input.text
        skill_path = skill_input.display_path
        decomposition = decompose_skill(Path(skill_path), text)
        static_findings = static_review(
            decomposition,
            text,
            anti_patterns=V01_ANTI_PATTERNS,
            effective_patterns=EFFECTIVE_PATTERNS,
        )
        skill_observables = _observable_contract(decomposition, static_findings)
        observable_contract.extend(skill_observables)
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
                for section in decomposition["sections"]:
                    variant_entries.append(
                        _variant_payload(
                            "ablated", decomposition, text, section["id"]
                        )
                    )
            else:
                variant_entries.append(
                    _variant_payload(variant_id, decomposition, text)
                )
        projected_rows = len(task_matrix) + len(task_fixtures) * len(variant_entries)
        if projected_rows > MAX_EVALUATION_MATRIX_ROWS:
            raise ValueError(
                "Evaluation task matrix exceeds the maximum row count of "
                f"{MAX_EVALUATION_MATRIX_ROWS}."
            )
        evaluated_skills.append(
            {
                "skill_path": skill_path,
                "decomposition": decomposition,
                "static_findings": static_findings,
                "variants": variant_entries,
            }
        )
        packet_inclusion_contracts.append(
            {
                "skill_path": skill_path,
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
                        "skill_path": skill_path,
                        "prompt": fixture.get("prompt"),
                        "expected_observables": expected_observables,
                        "skill_attachment": variant["content"],
                    }
                )

    plan = {
        "ok": True,
        "stability": "experimental",
        "schema": EVAL_PLAN_SCHEMA,
        "created_at": _iso_now(),
        "evaluated_skills": [
            {
                "skill_path": item["skill_path"],
                "title": item["decomposition"]["title"],
                "behavior_atoms": item["decomposition"]["behavior_atoms"],
                "static_findings": item["static_findings"],
                "variant_ids": sorted(
                    {
                        variant["variant_id"]
                        for variant in item["variants"]
                    }
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
            "trace_schema": EVAL_TRACE_SCHEMA,
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
                "schema": EVAL_TRACE_SCHEMA,
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
    safe_plan = _redact_output(plan, redactions)
    if len(_json_text(safe_plan, label="Evaluation plan").encode("utf-8")) > (
        MAX_EVALUATION_PLAN_BYTES
    ):
        raise ValueError(
            "Evaluation plan exceeds the maximum serialized size of "
            f"{MAX_EVALUATION_PLAN_BYTES} bytes."
        )
    return safe_plan


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


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != EVAL_PLAN_SCHEMA:
        raise ValueError(f"evaluation_plan schema must be {EVAL_PLAN_SCHEMA}.")
    for key in (
        "evaluated_skills",
        "task_matrix",
        "observable_behavior_contract",
        "packet_inclusion_contracts",
    ):
        value = plan.get(key)
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError(f"evaluation_plan {key} must be a list of objects.")
    for index, skill in enumerate(plan["evaluated_skills"]):
        findings = skill.get("static_findings")
        if findings is not None and (
            not isinstance(findings, list)
            or not all(isinstance(item, dict) for item in findings)
        ):
            raise ValueError(
                f"evaluation_plan evaluated_skills[{index}].static_findings "
                "must be a list of objects."
            )
    for index, contract in enumerate(plan["packet_inclusion_contracts"]):
        expected = contract.get("expected")
        if expected is not None and not isinstance(expected, dict):
            raise ValueError(
                f"evaluation_plan packet_inclusion_contracts[{index}].expected "
                "must be an object."
            )
    return plan


def _load_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    plan_input = arguments.get("evaluation_plan")
    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    redactions: dict[str, int] = {}
    if isinstance(plan_input, dict):
        plan = _safe_bounded_json_value(
            plan_input,
            label="evaluation_plan",
            redactions=redactions,
        )
        if not isinstance(plan, dict):
            raise ValueError("evaluation_plan must be a JSON object.")
    elif isinstance(plan_input, str):
        plan_input_file = read_json_input(
            plan_input,
            project_path=project_path,
            max_file_bytes=MAX_EVALUATION_PLAN_BYTES,
        )
        plan = plan_input_file.payload
        merge_redactions(redactions, plan_input_file.redactions)
    else:
        raise ValueError("evaluation_plan is required for evidence scoring.")
    if redactions:
        existing_summary = plan.get("redaction_summary")
        summary = (
            {
                str(label): count
                for label, count in existing_summary.items()
                if isinstance(label, str) and isinstance(count, int) and count >= 0
            }
            if isinstance(existing_summary, dict)
            else {}
        )
        merge_redactions(summary, redactions)
        plan = {**plan, "redaction_summary": summary}
    return _validate_plan(plan)


def _redact_composed_payload(payload: Any) -> dict[str, Any]:
    safe_payload, _ = redact_json_value(payload, enabled=True)
    if not isinstance(safe_payload, dict):
        raise ValueError("Data-only composition did not return an object.")
    return safe_payload


def score_evidence(
    arguments: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
) -> dict[str, Any]:
    plan = _load_plan(arguments) if plan is None else _validate_plan(plan)
    raw_evidence = arguments.get("run_evidence_json")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("run_evidence_json is required for evidence scoring.")
    if len(raw_evidence) > MAX_EVALUATION_TRACES:
        raise ValueError(
            "run_evidence_json exceeds the maximum trace count of "
            f"{MAX_EVALUATION_TRACES}."
        )
    if not all(isinstance(item, dict) for item in raw_evidence):
        raise ValueError("run_evidence_json must contain trace objects.")
    redactions: dict[str, int] = {}
    safe_evidence = _safe_bounded_json_value(
        raw_evidence,
        label="run_evidence_json",
        redactions=redactions,
    )
    if not isinstance(safe_evidence, list):
        raise ValueError("run_evidence_json must contain trace objects.")
    for index, item in enumerate(safe_evidence):
        if not isinstance(item, dict):
            raise ValueError("run_evidence_json must contain trace objects.")
        for key in ("observations", "trace"):
            observations = item.get(key)
            if observations is not None and not isinstance(observations, list):
                raise ValueError(f"run_evidence_json trace {index}.{key} must be a list.")
            if isinstance(observations, list) and len(observations) > MAX_EVALUATION_OBSERVATIONS_PER_TRACE:
                raise ValueError(
                    f"run_evidence_json trace {index}.{key} exceeds the maximum observation count of "
                    f"{MAX_EVALUATION_OBSERVATIONS_PER_TRACE}."
                )
    traces = [_normalize_trace(item) for item in safe_evidence]
    if not traces:
        raise ValueError("run_evidence_json must contain trace objects.")
    for trace in traces:
        if not trace.get("observations"):
            raise ValueError(
                "Each evidence trace must include observable observations; "
                "prose-only summaries are rejected in v0.1."
            )

    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    report = score_traces(
        plan,
        traces,
        compose_evaluation_row=compose_evaluation_row,
        project_path=str(project_path) if project_path is not None else None,
        use_compose_packet=bool(arguments.get("compose_packet", True)),
        redact_composed=_redact_composed_payload,
        anti_pattern_catalog=list(V01_ANTI_PATTERNS),
        effective_patterns=list(EFFECTIVE_PATTERNS),
        report_schema=EVAL_REPORT_SCHEMA,
        created_at=_iso_now(),
    )
    plan_redactions = plan.get("redaction_summary")
    if isinstance(plan_redactions, dict):
        merge_redactions(
            redactions,
            {
                str(label): count
                for label, count in plan_redactions.items()
                if isinstance(label, str) and isinstance(count, int) and count >= 0
            },
        )
    return _redact_output(report, redactions)


def _guidebook_markdown(entries: list[dict[str, Any]]) -> str:
    """Compatibility facade for adapter callers during renderer migration."""

    return _render_guidebook_markdown(entries, evidence_levels=EVIDENCE_LEVELS)


def _pattern_catalog(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compatibility facade for adapter callers during renderer migration."""

    return _build_pattern_catalog(
        entries,
        patterns=(*EFFECTIVE_PATTERNS, *V01_ANTI_PATTERNS),
        created_at=_iso_now(),
    )


def evaluate_skills(
    arguments: dict[str, Any],
    *,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
    artifact_writer: EvaluationArtifactWriter | None = None,
) -> dict[str, Any]:
    return evaluate_mode(
        arguments,
        build_plan=build_evaluation_plan,
        load_plan=_load_plan,
        build_report=lambda score_arguments, plan: score_evidence(
            score_arguments,
            plan=plan,
            compose_evaluation_row=compose_evaluation_row,
        ),
        artifact_writer=artifact_writer,
    )


PATTERN_CATALOG_PATH = PLUGIN_ROOT / "docs" / "SKILL_PATTERN_CATALOG.json"


def is_evaluable_skill_source(
    path: Path | str,
    rel_path: str = "",
    source_type: str = "",
) -> bool:
    skill_path = Path(path)
    name = skill_path.name.lower()
    rel = (rel_path or str(skill_path)).lower()
    if source_type == "skill_definition" or name == "skill.md":
        return True
    if "/skills/" in f"/{rel}" or rel.startswith("skills/"):
        return True
    return False


def _pattern_lookup() -> dict[str, dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    try:
        payload = json.loads(PATTERN_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict):
        candidate = payload.get("patterns", [])
        if isinstance(candidate, list):
            discovered = [item for item in candidate if isinstance(item, dict)]
    return _merge_pattern_catalog(V01_ANTI_PATTERNS, discovered)


def harvest_warnings_for_source(
    path: Path | str,
    text: str,
    *,
    rel_path: str = "",
    source_type: str = "",
) -> list[dict[str, Any]]:
    skill_path = Path(path)
    if not is_evaluable_skill_source(skill_path, rel_path, source_type):
        return []
    decomposition = decompose_skill(skill_path, text)
    findings = static_review(
        decomposition,
        text,
        anti_patterns=V01_ANTI_PATTERNS,
        effective_patterns=EFFECTIVE_PATTERNS,
    )
    patterns = _pattern_lookup()
    return _build_harvest_advisories(findings, patterns)
