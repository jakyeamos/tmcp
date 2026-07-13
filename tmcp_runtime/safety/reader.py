"""Bounded, race-aware reads for verified harvest candidates."""

from __future__ import annotations

import os
import stat

from tmcp_runtime.safety.redaction import redact_sensitive_text
from tmcp_runtime.safety.files import (
    HarvestCandidate,
    SafeText,
    _is_link_or_reparse_point,
    _is_within,
    _safe_error,
)


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
        or _is_link_or_reparse_point(root_metadata)
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
    if current_path != candidate.resolved_path or not _is_within(
        current_path, candidate.root.resolved_path
    ):
        return None, f"Skipped source outside source root: {candidate.display_path}"
    try:
        metadata = candidate.resolved_path.lstat()
    except OSError as exc:
        return None, f"Could not stat {candidate.display_path}: {_safe_error(exc)}"
    if _is_link_or_reparse_point(metadata):
        return (
            None,
            f"Skipped symlink or reparse-point source file: {candidate.display_path}",
        )
    if not stat.S_ISREG(metadata.st_mode):
        return None, f"Skipped non-regular source file: {candidate.display_path}"

    no_follow_flag = getattr(os, "O_NOFOLLOW", None)
    if no_follow_flag is None and os.name != "nt":
        return (
            None,
            "Cannot safely read source file because this platform lacks a "
            f"no-follow open primitive: {candidate.display_path}",
        )
    # Windows has no O_NOFOLLOW equivalent.  The boundary checks above reject
    # links/reparse points and the descriptor identity check below still closes
    # the ordinary read-only path if the file changes before or during open.
    flags = os.O_RDONLY | (no_follow_flag or 0)
    try:
        descriptor = os.open(candidate.resolved_path, flags)
    except OSError as exc:
        return None, f"Could not read {candidate.display_path}: {_safe_error(exc)}"

    try:
        with os.fdopen(descriptor, "rb", closefd=True) as source_file:
            descriptor = -1
            opened_metadata = os.fstat(source_file.fileno())
            if not stat.S_ISREG(opened_metadata.st_mode):
                return (
                    None,
                    f"Skipped non-regular source file: {candidate.display_path}",
                )
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
    text = (
        data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    )
    safe_text, redactions = redact_sensitive_text(text, enabled=redact_sensitive)
    return SafeText(text=safe_text, redactions=redactions), None
