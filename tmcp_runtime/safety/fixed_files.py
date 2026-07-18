"""Safe exact-file inputs for evaluation and other non-traversal features."""

from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from tmcp_runtime.safety.redaction import merge_redactions
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
    """A bounded JSON object parsed only after redaction.

    ``preserved_sha256_literals`` is deliberately narrower than the decoded
    input: it can contain only caller-requested, fixed-width lowercase SHA-256
    values captured during the same protected file read.  It exists for
    compiler-issued identities that would otherwise be redacted as high
    entropy strings; it must never contain source prose or arbitrary values.
    """

    display_path: str
    payload: dict[str, Any]
    redactions: dict[str, int]
    preserved_sha256_literals: dict[tuple[str | int, ...], str] = field(
        default_factory=dict
    )


_SHA256_LITERAL_RE = re.compile(r"[a-f0-9]{64}")
_MAX_PRESERVED_SHA256_PATHS = 64
_MAX_PRESERVED_SHA256_PATH_DEPTH = 16
_MAX_PRESERVED_SHA256_LITERALS = 512
_MAX_HASH_PATH_PART_LENGTH = 128


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
            f"Input is outside the approved project path: {root.display_path}"
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
    redact_sensitive: bool = True,
) -> SafeFileInput:
    root = _file_root(path)
    candidate = _candidate_for(root, boundary)
    source, warning = read_harvest_text(
        candidate,
        max_file_bytes,
        redact_sensitive=redact_sensitive,
    )
    if warning or source is None:
        raise ValueError(warning or f"Could not read input file: {root.display_path}")
    return SafeFileInput(
        display_path=candidate.display_path,
        display_relative_path=candidate.display_relative_path,
        text=source.text,
        redactions=source.redactions,
    )


def _preserved_sha256_paths(
    paths: Iterable[Sequence[str | int]],
) -> tuple[tuple[str | int, ...], ...]:
    """Validate a tiny allowlist of raw hash locations before one safe read."""

    normalized: list[tuple[str | int, ...]] = []
    for raw_path in paths:
        if not isinstance(raw_path, (tuple, list)):
            raise ValueError("preserve_sha256_paths entries must be path sequences.")
        path = tuple(raw_path)
        if (
            not path
            or len(path) > _MAX_PRESERVED_SHA256_PATH_DEPTH
            or any(
                (not isinstance(part, (str, int)))
                or isinstance(part, bool)
                or (isinstance(part, int) and part < 0)
                or (
                    isinstance(part, str)
                    and len(part) > _MAX_HASH_PATH_PART_LENGTH
                )
                for part in path
            )
        ):
            raise ValueError("preserve_sha256_paths contains an invalid path.")
        normalized.append(path)
    if len(normalized) > _MAX_PRESERVED_SHA256_PATHS:
        raise ValueError(
            "preserve_sha256_paths exceeds the maximum of "
            f"{_MAX_PRESERVED_SHA256_PATHS} paths."
        )
    return tuple(normalized)


def _preserve_sha256_literals(
    value: object,
    patterns: Sequence[tuple[str | int, ...]],
) -> dict[tuple[str | int, ...], str]:
    """Copy only requested hash leaves from an already bounded parsed object.

    A ``'*'`` segment matches mapping keys or list indices.  It is useful for
    bounded traces while keeping the public result a closed set of actual
    locations and values rather than a raw object reference.
    """

    preserved: dict[tuple[str | int, ...], str] = {}

    def visit(
        current: object,
        remaining: Sequence[str | int],
        location: tuple[str | int, ...],
    ) -> None:
        if not remaining:
            if isinstance(current, str) and _SHA256_LITERAL_RE.fullmatch(current):
                if (
                    location not in preserved
                    and len(preserved) >= _MAX_PRESERVED_SHA256_LITERALS
                ):
                    raise ValueError(
                        "preserve_sha256_paths exceeds the maximum of "
                        f"{_MAX_PRESERVED_SHA256_LITERALS} literals."
                    )
                preserved[location] = current
            return
        segment = remaining[0]
        rest = remaining[1:]
        if segment == "*":
            if isinstance(current, dict):
                for key, item in current.items():
                    if isinstance(key, str):
                        visit(item, rest, (*location, key))
            elif isinstance(current, list):
                for index, item in enumerate(current):
                    visit(item, rest, (*location, index))
            return
        if isinstance(current, dict) and isinstance(segment, str):
            if segment in current:
                visit(current[segment], rest, (*location, segment))
        elif isinstance(current, list) and isinstance(segment, int):
            if segment < len(current):
                visit(current[segment], rest, (*location, segment))

    for pattern in patterns:
        visit(value, pattern, ())
    return preserved


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
                f"Evaluation accepts explicit SKILL.md files only: {root.display_path}"
            )
        if root.resolved_path in seen:
            continue
        seen.add(root.resolved_path)
        try:
            file_size = root.resolved_path.stat().st_size
        except OSError as exc:
            raise ValueError(
                f"Could not inspect input file: {root.display_path}"
            ) from exc
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
    project_path: str | Path | None = None,
    max_file_bytes: int = 262_144,
    preserve_sha256_paths: Iterable[Sequence[str | int]] = (),
) -> SafeJsonInput:
    """Read a regular `.json` file and redact decoded string values.

    The optional hash path allowlist is captured before decoded-value
    redaction, but only fixed-width SHA-256 literals are returned.  This lets
    persistence code retain verifiable compiler identities without a second,
    unbounded filesystem read after this protected read completes.
    """

    root = _file_root(path)
    if root.logical_path.suffix.lower() != ".json":
        raise ValueError(f"Input must be a JSON file: {root.display_path}")
    boundary = _project_root(project_path)
    source = _read_exact_file(
        path,
        boundary=boundary,
        max_file_bytes=max_file_bytes,
        redact_sensitive=False,
    )
    try:
        parsed = json.loads(source.text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input JSON is invalid: {source.display_path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Input JSON must contain an object.")
    literals = _preserve_sha256_literals(
        parsed,
        _preserved_sha256_paths(preserve_sha256_paths),
    )
    payload, decoded_redactions = redact_json_value(parsed, enabled=True)
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must contain an object.")
    redactions = dict(source.redactions)
    merge_redactions(redactions, decoded_redactions)
    return SafeJsonInput(
        display_path=source.display_path,
        payload=payload,
        redactions=redactions,
        preserved_sha256_literals=literals,
    )
