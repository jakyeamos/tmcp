"""Harvested incompatibility checks for semantic composition validation."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .composition_preflight import normalized_text, string_list
from .composition_validation_text import _error


def validate_harvested_conflicts(
    nodes_by_id: dict[str, dict[str, Any]],
    roles_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    """Reject selected same-phase conflicts declared by harvested sources."""

    aliases: dict[str, set[str]] = {}

    def add_alias(value: object, node_id: str) -> None:
        raw = normalized_text(value).lower()
        if raw:
            aliases.setdefault(raw, set()).add(node_id)
        slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
        if slug:
            aliases.setdefault(slug, set()).add(node_id)

    for node_id, item in nodes_by_id.items():
        for alias in (
            node_id,
            str(item.get("title") or ""),
            str(item.get("relative_path") or ""),
            str(item.get("path") or ""),
            str(item.get("skill_id") or ""),
        ):
            add_alias(alias, node_id)
        relative_path = PurePosixPath(
            str(item.get("relative_path") or "").replace("\\", "/")
        )
        if relative_path.name.lower() == "skill.md":
            add_alias(relative_path.parent.name, node_id)
    for node_id, role in roles_by_id.items():
        for incompatible in string_list(nodes_by_id[node_id].get("incompatibilities")):
            raw_alias = normalized_text(incompatible).lower()
            slug_alias = re.sub(r"[^a-z0-9]+", "-", raw_alias).strip("-")
            targets = set(aliases.get(raw_alias, set())).union(
                aliases.get(slug_alias, set())
            ).intersection(roles_by_id)
            if len(targets) > 1:
                errors.append(
                    _error(
                        "ambiguous_harvested_incompatibility",
                        f"skill_roles[{node_id}]",
                        "Harvested incompatibility "
                        + incompatible
                        + " resolves to multiple selected skills.",
                    )
                )
                continue
            if not targets:
                continue
            target = next(iter(targets))
            shared = sorted(
                set(role["phase_affinity"]).intersection(
                    roles_by_id[target]["phase_affinity"]
                )
            )
            if shared:
                errors.append(
                    _error(
                        "same_phase_conflict",
                        f"skill_roles[{node_id}]",
                        f"Harvested incompatibility with {target} shares phases: {', '.join(shared)}.",
                    )
                )
