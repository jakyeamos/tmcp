"""Filesystem boundaries for untrusted harvested source material."""

from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from scripts.tmcp_redaction import merge_redactions, redact_sensitive_text


@dataclass(frozen=True)
class HarvestRoot:
    """A user-selected source root and its canonical containment boundary."""

    logical_path: Path
    resolved_path: Path
    display_path: str
    kind: str


@dataclass(frozen=True)
class HarvestCandidate:
    """A regular file selected within a verified harvest root."""

    root: HarvestRoot
    logical_path: Path
    resolved_path: Path
    relative_path: str
    display_path: str
    display_relative_path: str
    device: int
    inode: int


@dataclass(frozen=True)
class SafeText:
    """Bounded source text after the requested redaction policy."""

    text: str
    redactions: dict[str, int]


def redact_json_value(value: Any, *, enabled: bool) -> tuple[Any, dict[str, int]]:
    """Redact decoded JSON values before callers derive or serialize metadata."""

    if not enabled:
        return value, {}
    if isinstance(value, str):
        return redact_sensitive_text(value, enabled=True)
    if isinstance(value, list):
        safe_values: list[Any] = []
        redactions: dict[str, int] = {}
        for item in value:
            safe_item, item_redactions = redact_json_value(item, enabled=True)
            safe_values.append(safe_item)
            merge_redactions(redactions, item_redactions)
        return safe_values, redactions
    if isinstance(value, dict):
        safe_values: dict[str, Any] = {}
        redactions: dict[str, int] = {}
        for raw_key, item in value.items():
            safe_key, key_redactions = redact_sensitive_text(
                str(raw_key),
                enabled=True,
            )
            safe_item, item_redactions = redact_json_value(item, enabled=True)
            safe_values[safe_key] = safe_item
            merge_redactions(redactions, key_redactions)
            merge_redactions(redactions, item_redactions)
        return safe_values, redactions
    return value, {}


def redact_path(value: str | Path) -> str:
    """Return a provenance-safe path string without exposing secret-like names."""

    safe_path, _ = redact_sensitive_text(str(value), enabled=True)
    return safe_path


def _safe_error(exc: OSError) -> str:
    return redact_path(str(exc))


def _absolute_path(value: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(value).expanduser())))


def _trusted_system_alias_target(path: Path) -> Path | None:
    if os.name != "posix" or path not in {Path("/tmp"), Path("/var")}:
        return None
    try:
        target = path.resolve(strict=True)
        metadata = target.lstat()
    except OSError:
        return None
    return target if stat.S_ISDIR(metadata.st_mode) else None


def _first_untrusted_symlink_component(path: Path) -> Path | None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return None
        except OSError:
            return current
        if not stat.S_ISLNK(metadata.st_mode):
            continue
        trusted_target = _trusted_system_alias_target(current)
        if trusted_target is None:
            return current
        current = trusted_target
    return None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _append_warning(warnings: list[str], warning: str, *, limit: int = 20) -> None:
    if len(warnings) < limit:
        warnings.append(warning)


def collect_harvest_roots(
    raw_paths: Iterable[str | Path], *, follow_symlinks: bool
) -> tuple[list[HarvestRoot], list[str]]:
    """Validate user-selected harvest roots without resolving before policy checks."""

    roots: list[HarvestRoot] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        logical_path = _absolute_path(raw_path)
        display_path = redact_path(logical_path)
        symlink_component = _first_untrusted_symlink_component(logical_path)
        if symlink_component is not None and not follow_symlinks:
            label = (
                "source-root symlink"
                if symlink_component.name == logical_path.name
                else "source-path symlink component"
            )
            warnings.append(
                f"Skipped {label} without follow_symlinks=true: {display_path}"
            )
            continue
        try:
            source_metadata = logical_path.lstat()
        except FileNotFoundError:
            warnings.append(f"Source path does not exist: {display_path}")
            continue
        except OSError as exc:
            warnings.append(
                f"Could not inspect source path {display_path}: {_safe_error(exc)}"
            )
            continue

        is_symlink = stat.S_ISLNK(source_metadata.st_mode)
        if (
            is_symlink
            and not follow_symlinks
            and _trusted_system_alias_target(logical_path) is None
        ):
            warnings.append(
                "Skipped source-root symlink without follow_symlinks=true: "
                f"{display_path}"
            )
            continue
        try:
            resolved_path = logical_path.resolve(strict=True)
            target_metadata = resolved_path.stat()
        except FileNotFoundError:
            warnings.append(f"Source path does not exist: {display_path}")
            continue
        except OSError as exc:
            warnings.append(
                f"Could not resolve source path {display_path}: {_safe_error(exc)}"
            )
            continue

        if stat.S_ISREG(target_metadata.st_mode):
            kind = "file"
        elif stat.S_ISDIR(target_metadata.st_mode):
            kind = "directory"
        else:
            warnings.append(
                "Source path is not a regular file or directory: "
                f"{display_path}"
            )
            continue
        root_key = str(resolved_path)
        if root_key in seen:
            continue
        seen.add(root_key)
        roots.append(
            HarvestRoot(
                logical_path=logical_path,
                resolved_path=resolved_path,
                display_path=display_path,
                kind=kind,
            )
        )
    return roots, warnings


def _expand_brace_glob(pattern: str) -> list[str]:
    start = pattern.find("{")
    if start == -1:
        return [pattern]
    end = pattern.find("}", start + 1)
    if end == -1:
        return [pattern]
    before = pattern[:start]
    after = pattern[end + 1 :]
    return [
        f"{before}{item.strip()}{after}"
        for item in pattern[start + 1 : end].split(",")
    ]


def _matches_glob(rel_path: str, path: Path, pattern: str) -> bool:
    variants = [pattern]
    if pattern.startswith("**/"):
        variants.append(pattern[3:])
    return any(
        fnmatch.fnmatch(rel_path, variant)
        or fnmatch.fnmatch(path.name, variant)
        or fnmatch.fnmatch(f"/{rel_path}", f"/{variant}")
        for variant in variants
    )


def _matches_any(rel_path: str, path: Path, patterns: Sequence[str]) -> bool:
    return any(
        _matches_glob(rel_path, path, expanded)
        for pattern in patterns
        for expanded in _expand_brace_glob(pattern)
    )


def _path_suffix(path: Path, depth: int) -> str:
    parts = [part for part in path.parts if part and part != path.anchor]
    return "/".join(parts[-depth:]) if parts else path.name


def _file_root_relative_paths(roots: Sequence[HarvestRoot]) -> dict[HarvestRoot, str]:
    file_roots = [root for root in roots if root.kind == "file"]
    if not file_roots:
        return {}
    max_depth = max(len(root.logical_path.parts) for root in file_roots)
    for depth in range(1, max_depth + 1):
        labels = {
            root: _path_suffix(root.logical_path, depth)
            for root in file_roots
        }
        if len(set(labels.values())) == len(labels):
            return labels
    return {root: str(root.logical_path) for root in file_roots}


def _candidate_is_selected(
    rel_path: str,
    logical_path: Path,
    include_globs: Sequence[str],
    exclude_globs: Sequence[str],
) -> bool:
    return not _matches_any(rel_path, logical_path, exclude_globs) and _matches_any(
        rel_path,
        logical_path,
        include_globs,
    )


def _candidate_for(
    root: HarvestRoot,
    logical_path: Path,
    resolved_path: Path,
    relative_path: str,
    *,
    seen_files: set[str],
    include_globs: Sequence[str],
    exclude_globs: Sequence[str],
) -> HarvestCandidate | None:
    if not _candidate_is_selected(
        relative_path,
        logical_path,
        include_globs,
        exclude_globs,
    ):
        return None
    try:
        resolved_relative_path = resolved_path.relative_to(
            root.resolved_path
        ).as_posix()
    except ValueError:
        return None
    if _matches_any(resolved_relative_path, resolved_path, exclude_globs):
        return None
    resolved_key = str(resolved_path)
    if resolved_key in seen_files:
        return None
    try:
        metadata = resolved_path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        return None
    seen_files.add(resolved_key)
    return HarvestCandidate(
        root=root,
        logical_path=logical_path,
        resolved_path=resolved_path,
        relative_path=relative_path,
        display_path=redact_path(logical_path),
        display_relative_path=redact_path(relative_path),
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


def _directory_is_excluded(
    rel_path: str,
    logical_path: Path,
    excluded_dir_names: set[str],
    exclude_globs: Sequence[str],
) -> bool:
    return logical_path.name in excluded_dir_names or _matches_any(
        f"{rel_path}/",
        logical_path,
        exclude_globs,
    )


def _resolved_directory_is_excluded(
    resolved_path: Path,
    root: HarvestRoot,
    excluded_dir_names: set[str],
    exclude_globs: Sequence[str],
) -> bool:
    try:
        resolved_relative_path = resolved_path.relative_to(
            root.resolved_path
        ).as_posix()
    except ValueError:
        return True
    return _directory_is_excluded(
        resolved_relative_path,
        resolved_path,
        excluded_dir_names,
        exclude_globs,
    )


def _resolved_inside_root(path: Path, root: HarvestRoot) -> Path | None:
    try:
        resolved_path = path.resolve(strict=True)
    except OSError:
        return None
    if not _is_within(resolved_path, root.resolved_path):
        return None
    return resolved_path


def iter_harvest_candidates(
    roots: Sequence[HarvestRoot],
    include_globs: Sequence[str],
    exclude_globs: Sequence[str],
    excluded_dir_names: set[str],
    *,
    follow_symlinks: bool,
) -> tuple[list[HarvestCandidate], list[str]]:
    """Traverse only regular files contained by their selected source root."""

    candidates: list[HarvestCandidate] = []
    warnings: list[str] = []
    seen_files: set[str] = set()
    file_root_relative_paths = _file_root_relative_paths(roots)

    for root in roots:
        if root.kind == "file":
            relative_path = file_root_relative_paths.get(root, root.logical_path.name)
            candidate = _candidate_for(
                root,
                root.logical_path,
                root.resolved_path,
                relative_path,
                seen_files=seen_files,
                include_globs=include_globs,
                exclude_globs=exclude_globs,
            )
            if candidate is not None:
                candidates.append(candidate)
            continue

        stack: list[tuple[Path, Path]] = [(root.resolved_path, Path())]
        visited_directories = {str(root.resolved_path)}
        while stack:
            physical_directory, logical_relative_directory = stack.pop()
            try:
                entries = sorted(
                    list(os.scandir(physical_directory)),
                    key=lambda entry: entry.name,
                )
            except OSError as exc:
                _append_warning(
                    warnings,
                    "Could not scan directory "
                    f"{redact_path(physical_directory)}: {_safe_error(exc)}",
                )
                continue

            nested_directories: list[tuple[Path, Path]] = []
            for entry in entries:
                relative_path = (
                    logical_relative_directory / entry.name
                ).as_posix()
                logical_path = root.logical_path / relative_path
                physical_path = Path(entry.path)
                try:
                    is_symlink = entry.is_symlink()
                except OSError as exc:
                    _append_warning(
                        warnings,
                        "Could not inspect source path "
                        f"{redact_path(logical_path)}: {_safe_error(exc)}",
                    )
                    continue

                if is_symlink:
                    if not follow_symlinks:
                        _append_warning(
                            warnings,
                            "Skipped symlink without follow_symlinks=true: "
                            f"{redact_path(logical_path)}",
                        )
                        continue
                    resolved_path = _resolved_inside_root(physical_path, root)
                    if resolved_path is None:
                        _append_warning(
                            warnings,
                            "Skipped symlink outside source root or unresolved: "
                            f"{redact_path(logical_path)}",
                        )
                        continue
                    try:
                        target_metadata = resolved_path.stat()
                    except OSError as exc:
                        _append_warning(
                            warnings,
                            "Could not inspect source path "
                            f"{redact_path(logical_path)}: {_safe_error(exc)}",
                        )
                        continue
                    if stat.S_ISDIR(target_metadata.st_mode):
                        if _directory_is_excluded(
                            relative_path,
                            logical_path,
                            excluded_dir_names,
                            exclude_globs,
                        ) or _resolved_directory_is_excluded(
                            resolved_path,
                            root,
                            excluded_dir_names,
                            exclude_globs,
                        ):
                            _append_warning(
                                warnings,
                                f"Skipped directory: {redact_path(relative_path)}",
                            )
                            continue
                        resolved_key = str(resolved_path)
                        if resolved_key in visited_directories:
                            _append_warning(
                                warnings,
                                "Skipped duplicate or cyclic symlink directory: "
                                f"{redact_path(logical_path)}",
                            )
                            continue
                        visited_directories.add(resolved_key)
                        nested_directories.append(
                            (resolved_path, logical_relative_directory / entry.name)
                        )
                        continue
                    if not stat.S_ISREG(target_metadata.st_mode):
                        _append_warning(
                            warnings,
                            "Skipped symlink to non-regular source: "
                            f"{redact_path(logical_path)}",
                        )
                        continue
                    candidate = _candidate_for(
                        root,
                        logical_path,
                        resolved_path,
                        relative_path,
                        seen_files=seen_files,
                        include_globs=include_globs,
                        exclude_globs=exclude_globs,
                    )
                    if candidate is not None:
                        candidates.append(candidate)
                    continue

                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    _append_warning(
                        warnings,
                        "Could not inspect source path "
                        f"{redact_path(logical_path)}: {_safe_error(exc)}",
                    )
                    continue
                if stat.S_ISDIR(metadata.st_mode):
                    if _directory_is_excluded(
                        relative_path,
                        logical_path,
                        excluded_dir_names,
                        exclude_globs,
                    ):
                        _append_warning(
                            warnings,
                            f"Skipped directory: {redact_path(relative_path)}",
                        )
                        continue
                    resolved_path = _resolved_inside_root(physical_path, root)
                    if resolved_path is None:
                        _append_warning(
                            warnings,
                            "Skipped directory outside source root or unresolved: "
                            f"{redact_path(logical_path)}",
                        )
                        continue
                    resolved_key = str(resolved_path)
                    if resolved_key in visited_directories:
                        _append_warning(
                            warnings,
                            f"Skipped duplicate directory: {redact_path(logical_path)}",
                        )
                        continue
                    visited_directories.add(resolved_key)
                    nested_directories.append(
                        (resolved_path, logical_relative_directory / entry.name)
                    )
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                resolved_path = _resolved_inside_root(physical_path, root)
                if resolved_path is None:
                    _append_warning(
                        warnings,
                        "Skipped source file outside source root or unresolved: "
                        f"{redact_path(logical_path)}",
                    )
                    continue
                candidate = _candidate_for(
                    root,
                    logical_path,
                    resolved_path,
                    relative_path,
                    seen_files=seen_files,
                    include_globs=include_globs,
                    exclude_globs=exclude_globs,
                )
                if candidate is not None:
                    candidates.append(candidate)
            stack.extend(reversed(nested_directories))
    return candidates, warnings


def read_harvest_text(
    candidate: HarvestCandidate,
    max_file_bytes: int,
    *,
    redact_sensitive: bool,
) -> tuple[SafeText | None, str | None]:
    """Read one verified regular file without following a newly introduced link."""

    try:
        current_root = candidate.root.resolved_path.resolve(strict=True)
        root_metadata = candidate.root.resolved_path.lstat()
    except OSError as exc:
        return (
            None,
            "Could not verify source root "
            f"{candidate.root.display_path}: {_safe_error(exc)}",
        )
    expected_root_mode = (
        stat.S_ISDIR if candidate.root.kind == "directory" else stat.S_ISREG
    )
    if (
        current_root != candidate.root.resolved_path
        or stat.S_ISLNK(root_metadata.st_mode)
        or not expected_root_mode(root_metadata.st_mode)
    ):
        return None, f"Skipped source root that changed: {candidate.root.display_path}"
    try:
        current_path = candidate.resolved_path.resolve(strict=True)
    except OSError as exc:
        return (
            None,
            "Could not verify source path "
            f"{candidate.display_path}: {_safe_error(exc)}",
        )
    if (
        current_path != candidate.resolved_path
        or not _is_within(current_path, candidate.root.resolved_path)
    ):
        return None, f"Skipped source outside source root: {candidate.display_path}"
    try:
        metadata = candidate.resolved_path.lstat()
    except OSError as exc:
        return None, f"Could not stat {candidate.display_path}: {_safe_error(exc)}"
    if stat.S_ISLNK(metadata.st_mode):
        return None, f"Skipped symlink source file: {candidate.display_path}"
    if not stat.S_ISREG(metadata.st_mode):
        return None, f"Skipped non-regular source file: {candidate.display_path}"

    flags = os.O_RDONLY
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    flags |= no_follow
    try:
        descriptor = os.open(candidate.resolved_path, flags)
    except OSError as exc:
        return None, f"Could not read {candidate.display_path}: {_safe_error(exc)}"

    try:
        with os.fdopen(descriptor, "rb", closefd=True) as source_file:
            descriptor = -1
            opened_metadata = os.fstat(source_file.fileno())
            if not stat.S_ISREG(opened_metadata.st_mode):
                return None, f"Skipped non-regular source file: {candidate.display_path}"
            if (opened_metadata.st_dev, opened_metadata.st_ino) != (
                candidate.device,
                candidate.inode,
            ):
                return (
                    None,
                    "Skipped source file that changed while reading: "
                    f"{candidate.display_path}",
                )
            if opened_metadata.st_size > max_file_bytes:
                return (
                    None,
                    "Skipped large file: "
                    f"{candidate.display_path} "
                    f"({opened_metadata.st_size} bytes > {max_file_bytes})",
                )
            data = source_file.read(max_file_bytes + 1)
    except OSError as exc:
        return None, f"Could not read {candidate.display_path}: {_safe_error(exc)}"
    finally:
        if descriptor != -1:
            os.close(descriptor)

    if len(data) > max_file_bytes:
        return (
            None,
            "Skipped large file: "
            f"{candidate.display_path} ({len(data)} bytes > {max_file_bytes})",
        )
    if b"\x00" in data[:2048]:
        return None, f"Skipped likely binary file: {candidate.display_path}"
    text = data.decode("utf-8", errors="replace")
    safe_text, redactions = redact_sensitive_text(text, enabled=redact_sensitive)
    return SafeText(text=safe_text, redactions=redactions), None
