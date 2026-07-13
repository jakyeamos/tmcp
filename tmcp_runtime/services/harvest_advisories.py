"""Runtime-owned harvest advisory classification and catalog lookup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tmcp_runtime.services.evaluation_catalog import (
    EFFECTIVE_PATTERNS,
    V01_ANTI_PATTERNS,
)
from tmcp_runtime.services.evaluation_policy import decompose_skill, static_review
from tmcp_runtime.services.evaluation_rendering import (
    build_harvest_advisories,
    merge_pattern_catalog,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
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
    return "/skills/" in f"/{rel}" or rel.startswith("skills/")


def pattern_catalog_from_path(path: Path = PATTERN_CATALOG_PATH) -> dict[str, dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict):
        candidate = payload.get("patterns", [])
        if isinstance(candidate, list):
            discovered = [item for item in candidate if isinstance(item, dict)]
    return merge_pattern_catalog(V01_ANTI_PATTERNS, discovered)


def harvest_warnings_for_source(
    path: Path | str,
    text: str,
    *,
    rel_path: str = "",
    source_type: str = "",
    catalog_path: Path = PATTERN_CATALOG_PATH,
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
    return build_harvest_advisories(findings, pattern_catalog_from_path(catalog_path))
