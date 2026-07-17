"""Pure source authority, type, and identity policy for harvested nodes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


SOURCE_ROLES = frozenset(
    {"governing_instruction", "active_skill", "supporting_reference", "evidence_only"}
)
ACTIVATION_ELIGIBLE_SOURCE_ROLES = frozenset(
    {"governing_instruction", "active_skill"}
)
EVIDENCE_ONLY_PATH_COMPONENTS = frozenset(
    {
        "__fixtures__",
        "__tests__",
        "example",
        "examples",
        "fixture",
        "fixtures",
        "test",
        "tests",
    }
)
SUPPORTING_REFERENCE_PATH_COMPONENTS = frozenset({"reference", "references"})

HARVEST_SOURCE_TYPE_ATOMS: dict[str, tuple[str, ...]] = {
    "skill_definition": (
        "skill-routing",
        "behavior-preservation",
        "source-traceability",
    ),
    "agent_operating_contract": (
        "agent-operating-contract",
        "instruction-precedence",
        "source-traceability",
    ),
    "cursor_rule": ("editor-rule", "workflow-routing", "source-traceability"),
    "github_process": ("repository-process", "quality-gate-disclosure"),
    "project_documentation": ("project-context", "source-grounding"),
    "workflow_prompt": ("workflow-routing", "artifact-contract"),
    "markdown_process_doc": ("process-documentation", "source-grounding"),
    "scoped_packet_seed": (),
}


def _path_components(value: str) -> set[str]:
    return {
        component for component in re.split(r"[\\/]+", str(value).lower()) if component
    }


def is_evidence_only_path(value: str) -> bool:
    """Identify non-governing test, fixture, and example source locations."""

    return bool(_path_components(value).intersection(EVIDENCE_ONLY_PATH_COMPONENTS))


def is_supporting_reference_path(value: str) -> bool:
    """Keep reference trees advisory even when their prose mentions workflows."""

    return bool(
        _path_components(value).intersection(SUPPORTING_REFERENCE_PATH_COMPONENTS)
    )


def source_role_for(
    _path: Path,
    rel_path: str,
    source_type: str,
    *,
    explicitly_scoped: bool = False,
) -> str:
    """Classify how a harvested source may participate in composition."""

    if is_supporting_reference_path(rel_path):
        return "supporting_reference"
    if is_evidence_only_path(rel_path) and not explicitly_scoped:
        return "evidence_only"
    if source_type in {"agent_operating_contract", "cursor_rule"}:
        return "governing_instruction"
    if source_type in {"skill_definition", "scoped_packet_seed", "workflow_prompt"}:
        return "active_skill"
    return "supporting_reference"


def node_source_role(
    node: dict[str, Any], *, explicitly_scoped: bool = False
) -> str:
    """Resolve additive source roles while keeping legacy nodes composable."""

    rel_path = str(node.get("relative_path") or node.get("path") or "")
    if is_supporting_reference_path(rel_path):
        return "supporting_reference"
    if is_evidence_only_path(rel_path) and not explicitly_scoped:
        return "evidence_only"
    explicit_role = str(node.get("source_role") or "")
    if explicit_role in SOURCE_ROLES and not (
        explicitly_scoped and explicit_role == "evidence_only"
    ):
        return explicit_role
    source_type = str(node.get("source_type") or "")
    if source_type not in HARVEST_SOURCE_TYPE_ATOMS:
        return "supporting_reference"
    return source_role_for(
        Path(str(node.get("path") or rel_path)),
        rel_path,
        source_type,
        explicitly_scoped=explicitly_scoped,
    )


def source_role_is_activation_eligible(source_role: str) -> bool:
    return source_role in ACTIVATION_ELIGIBLE_SOURCE_ROLES


def source_type_for(path: Path, rel_path: str, _text: str) -> str:
    """Classify by trusted path convention, never by instruction-like prose."""

    name = path.name.lower()
    rel = rel_path.lower()
    if name == "skill.md":
        return "skill_definition"
    if name in {"agents.md", "claude.md"}:
        return "agent_operating_contract"
    if ".cursor/" in rel or name == ".cursorrules":
        return "cursor_rule"
    if ".github/" in rel:
        return "github_process"
    if is_supporting_reference_path(rel):
        return "project_documentation"
    if "workflow" in rel:
        return "workflow_prompt"
    if name == "readme.md" or "/docs/" in f"/{rel}" or "/doc/" in f"/{rel}":
        return "project_documentation"
    return "markdown_process_doc"


def skill_id_for(
    relative_path: str,
    source_type: str,
    frontmatter: dict[str, Any],
) -> str:
    """Return a stable human-facing source identity without replacing node IDs."""

    declared = str(frontmatter.get("name") or "").strip()
    if declared:
        return declared
    path = Path(relative_path)
    if source_type == "skill_definition" and path.parent.name:
        return path.parent.name
    return path.stem or relative_path
