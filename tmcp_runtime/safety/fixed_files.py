"""Safe exact-file inputs for evaluation and other non-traversal features."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.tmcp_redaction import merge_redactions
from tmcp_runtime.safety.files import (
    HarvestCandidate,
    HarvestRoot,
    collect_harvest_roots,
    redact_json_value,
    redact_path,
)
from tmcp_runtime.safety.reader import read_harvest_text


@dataclass(frozen=True)
class SafeFileInput:
    """A bounded, redacted exact-file input with safe provenance metadata."""

    display_path: str
    display_relative_path: str
    text: str
    redactions: dict[str, int]


@dataclass(frozen=True)
class SafeJsonInput:
    """A bounded JSON object parsed only after redaction."""

    display_path: str
    payload: dict[str, Any]
    redactions: dict[str, int]


def _failure(messages: list[str], fallback: str) -> ValueError:
    return ValueError("; ".join(messages) if messages else fallback)


def _project_root(project_path: str | Path | None) -> HarvestRoot | None:
    if project_path is None:
        return None
    roots, warnings = collect_harvest_roots([project_path], follow_symlinks=False)
    if warnings:
        raise _failure(warnings, "Could not validate project path.")
    if len(roots) != 1 or roots[0].kind != "directory":
        raise ValueError("project_path must be one real directory.")
    return roots[0]


def _file_root(path: str | Path) -> HarvestRoot:
    roots, warnings = collect_harvest_roots([path], follow_symlinks=False)
    if warnings:
        raise _failure(warnings, "Could not validate input file.")
    if len(roots) != 1 or roots[0].kind != "file":
        raise ValueError(f"Input must be a regular file: {redact_path(path)}")
    return roots[0]


def _candidate_for(
    root: HarvestRoot,
    boundary: HarvestRoot | None,
) -> HarvestCandidate:
    candidate_root = boundary or root
    try:
        raw_relative_path = root.resolved_path.relative_to(
            candidate_root.resolved_path
        ).as_posix()
    except ValueError as exc:
        raise ValueError(
            "Input is outside the approved project path: "
            f"{root.display_path}"
        ) from exc
    if boundary is None:
        raw_relative_path = root.logical_path.name
    try:
        metadata = root.resolved_path.stat()
    except OSError as exc:
        raise ValueError(f"Could not inspect input file: {root.display_path}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"Input must be a regular file: {root.display_path}")
    return HarvestCandidate(
        root=candidate_root,
        logical_path=root.logical_path,
        resolved_path=root.resolved_path,
        relative_path=raw_relative_path,
        display_path=root.display_path,
        display_relative_path=redact_path(raw_relative_path),
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


def _read_exact_file(
    path: str | Path,
    *,
    boundary: HarvestRoot | None,
    max_file_bytes: int,
) -> SafeFileInput:
    root = _file_root(path)
    candidate = _candidate_for(root, boundary)
    source, warning = read_harvest_text(
        candidate,
        max_file_bytes,
        redact_sensitive=True,
    )
    if warning or source is None:
        raise ValueError(warning or f"Could not read input file: {root.display_path}")
    return SafeFileInput(
        display_path=candidate.display_path,
        display_relative_path=candidate.display_relative_path,
        text=source.text,
        redactions=source.redactions,
    )


def read_skill_inputs(
    paths: Iterable[str | Path],
    *,
    project_path: str | Path | None,
    max_file_bytes: int = 262_144,
    max_files: int = 20,
    max_total_bytes: int = 1_048_576,
) -> list[SafeFileInput]:
    """Read explicit `SKILL.md` files without allowing parent-directory escape."""

    values = list(paths)
    if not values:
        raise ValueError("skill_paths is required for evaluation plan generation.")
    if len(values) > max_files:
        raise ValueError(f"skill_paths exceeds the maximum of {max_files} files.")
    boundary = _project_root(project_path)
    inputs: list[SafeFileInput] = []
    total_bytes = 0
    seen: set[Path] = set()
    for path in values:
        root = _file_root(path)
        if root.logical_path.name != "SKILL.md":
            raise ValueError(
                "Evaluation accepts explicit SKILL.md files only: "
                f"{root.display_path}"
            )
        if root.resolved_path in seen:
            continue
        seen.add(root.resolved_path)
        try:
            file_size = root.resolved_path.stat().st_size
        except OSError as exc:
            raise ValueError(f"Could not inspect input file: {root.display_path}") from exc
        if total_bytes + file_size > max_total_bytes:
            raise ValueError(
                "skill_paths exceeds the total input budget of "
                f"{max_total_bytes} bytes."
            )
        total_bytes += file_size
        candidate = _candidate_for(root, boundary)
        source, warning = read_harvest_text(
            candidate,
            max_file_bytes,
            redact_sensitive=True,
        )
        if warning or source is None:
            raise ValueError(
                warning or f"Could not read input file: {candidate.display_path}"
            )
        inputs.append(
            SafeFileInput(
                display_path=candidate.display_path,
                display_relative_path=candidate.display_relative_path,
                text=source.text,
                redactions=source.redactions,
            )
        )
    if not inputs:
        raise ValueError("skill_paths did not contain a readable SKILL.md file.")
    return inputs


def read_json_input(
    path: str | Path,
    *,
    max_file_bytes: int = 262_144,
) -> SafeJsonInput:
    """Read a regular `.json` file and redact decoded string values."""

    root = _file_root(path)
    if root.logical_path.suffix.lower() != ".json":
        raise ValueError(f"Input must be a JSON file: {root.display_path}")
    source = _read_exact_file(
        path,
        boundary=None,
        max_file_bytes=max_file_bytes,
    )
    try:
        parsed = json.loads(source.text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input JSON is invalid: {source.display_path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Input JSON must contain an object.")
    payload, decoded_redactions = redact_json_value(parsed, enabled=True)
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must contain an object.")
    redactions = dict(source.redactions)
    merge_redactions(redactions, decoded_redactions)
    return SafeJsonInput(
        display_path=source.display_path,
        payload=payload,
        redactions=redactions,
    )
