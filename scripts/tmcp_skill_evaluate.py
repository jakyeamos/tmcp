#!/usr/bin/env python3
"""Compatibility facade for evaluator and harvest-advisory entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tmcp_runtime.api.evaluation as _evaluation_api
from tmcp_runtime.api.evaluation import (
    EVAL_PLAN_SCHEMA,
    EVAL_REPORT_SCHEMA,
    EVAL_TRACE_SCHEMA,
    MAX_EVALUATION_INPUT_BYTES,
    MAX_EVALUATION_MATRIX_ROWS,
    MAX_EVALUATION_OBSERVATIONS_PER_TRACE,
    MAX_EVALUATION_PLAN_BYTES,
    MAX_EVALUATION_TASK_FIXTURES,
    MAX_EVALUATION_TRACES,
    MAX_EVALUATION_VARIANTS,
    ComposeEvaluationRow,
    EvaluationArtifactWriter,
    _iso_now,
    _json_text,
    _load_plan,
    _redact_output,
    _safe_bounded_json_value,
    _safe_json_value,
)
from tmcp_runtime.services.evaluation_catalog import (
    DEFAULT_VARIANTS,
    EFFECTIVE_PATTERNS,
    EVIDENCE_LEVELS,
    V01_ANTI_PATTERNS,
)
from tmcp_runtime.services.evaluation_packets import (
    compose_packet_for_eval_row,
    diff_packet_inclusion,
    expectations_for_plan_row as _expectations_for_plan_row,
    task_matrix_row as _task_matrix_row,
    variant_inclusion_expectations as _variant_inclusion_expectations,
)
from tmcp_runtime.services.evaluation_policy import decompose_skill, static_review
from tmcp_runtime.services.evaluation_rendering import (
    build_harvest_advisories as _build_harvest_advisories,
    build_pattern_catalog as _build_pattern_catalog,
    merge_pattern_catalog as _merge_pattern_catalog,
    render_guidebook_markdown as _render_guidebook_markdown,
)
from tmcp_runtime.services.evaluation_scoring import _normalize_trace, score_traces


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PATTERN_CATALOG_PATH = PLUGIN_ROOT / "docs" / "SKILL_PATTERN_CATALOG.json"


def _with_compatibility_limits() -> dict[str, int]:
    previous: dict[str, int] = {}
    for name in (
        "MAX_EVALUATION_INPUT_BYTES",
        "MAX_EVALUATION_MATRIX_ROWS",
        "MAX_EVALUATION_OBSERVATIONS_PER_TRACE",
        "MAX_EVALUATION_PLAN_BYTES",
        "MAX_EVALUATION_TASK_FIXTURES",
        "MAX_EVALUATION_TRACES",
        "MAX_EVALUATION_VARIANTS",
    ):
        previous[name] = getattr(_evaluation_api, name)
        setattr(_evaluation_api, name, globals()[name])
    return previous


def _restore_compatibility_limits(previous: dict[str, int]) -> None:
    for name, value in previous.items():
        setattr(_evaluation_api, name, value)


def build_evaluation_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    previous = _with_compatibility_limits()
    try:
        return _evaluation_api.build_evaluation_plan(arguments)
    finally:
        _restore_compatibility_limits(previous)


def score_evidence(
    arguments: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
) -> dict[str, Any]:
    previous = _with_compatibility_limits()
    try:
        return _evaluation_api.score_evidence(
            arguments,
            plan=plan,
            compose_evaluation_row=compose_evaluation_row,
        )
    finally:
        _restore_compatibility_limits(previous)


def evaluate_skills(
    arguments: dict[str, Any],
    *,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
    artifact_writer: EvaluationArtifactWriter | None = None,
) -> dict[str, Any]:
    previous = _with_compatibility_limits()
    try:
        return _evaluation_api.evaluate_skills(
            arguments,
            compose_evaluation_row=compose_evaluation_row,
            artifact_writer=artifact_writer,
        )
    finally:
        _restore_compatibility_limits(previous)


def _guidebook_markdown(entries: list[dict[str, Any]]) -> str:
    """Compatibility facade for legacy artifact callers."""

    return _render_guidebook_markdown(entries, evidence_levels=EVIDENCE_LEVELS)


def _pattern_catalog(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compatibility facade for legacy artifact callers."""

    return _build_pattern_catalog(
        entries,
        patterns=(*EFFECTIVE_PATTERNS, *V01_ANTI_PATTERNS),
        created_at=_iso_now(),
    )


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
    return _build_harvest_advisories(findings, _pattern_lookup())
