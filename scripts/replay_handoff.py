#!/usr/bin/env python3
"""Validate and replay versioned Codex/TMCP handoff file manifests.

The command is intentionally stdlib-only so it remains usable with a minimal
PATH in a fresh worktree.  It validates every source before writing anything,
then installs each file through a temporary sibling followed by ``os.replace``.
Existing files must already match unless ``--force`` is explicitly supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


CANONICAL_SCHEMA = "tmcp-handoff-manifest-v0.2"
SUPPORTED_CANONICAL_SCHEMAS = {
    "tmcp-handoff-manifest-v0.1": False,
    "tmcp-handoff-manifest-v0.2": True,
}
_CUSTODY_STATUSES = {"verified", "source_only", "unresolved", "stale"}
_OVERLAP_STATUSES = {"none", "shared", "unresolved"}
_RECEIPT_FRESHNESS = {"current", "stale", "unknown"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FORMATTER_FINGERPRINT_FIELDS = {
    "name",
    "version",
    "config_sha256",
    "invocation",
    "mode",
}
_FORMATTER_CONFIG_FILES = (".ruff.toml", "pyproject.toml", "ruff.toml")
_FORMATTER_DEFAULT_PROFILE = "ruff-format-defaults-v1"
_FORMATTER_NAME = "ruff"
_FORMATTER_INVOCATION = "ruff format --check"
_FORMATTER_MODE = "check"


class HandoffManifestError(ValueError):
    """Raised when a manifest or replay target is unsafe or inconsistent."""


@dataclass(frozen=True)
class HandoffEntry:
    destination: PurePosixPath
    source: PurePosixPath
    sha256: str
    size: int | None
    size_declared: bool
    custody: dict[str, str] | None


@dataclass(frozen=True)
class HandoffManifest:
    schema: str
    exact_base: str | None
    entries: tuple[HandoffEntry, ...]
    legacy: bool
    custody: dict[str, object] | None


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HandoffManifestError(f"manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HandoffManifestError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HandoffManifestError("manifest must contain a JSON object")
    return payload


def _safe_relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise HandoffManifestError(f"{label} must be a non-empty relative path")
    if "\\" in value or value.startswith("/") or "\x00" in value:
        raise HandoffManifestError(f"{label} is not a safe relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HandoffManifestError(f"{label} is not a safe relative path: {value!r}")
    return path


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise HandoffManifestError(f"{label} must be a non-empty string")
    return value


def _enum(value: object, label: str, allowed: set[str]) -> str:
    text = _string(value, label)
    if text not in allowed:
        values = ", ".join(sorted(allowed))
        raise HandoffManifestError(f"{label} must be one of: {values}")
    return text


def _date_time(value: object, label: str) -> str:
    text = _string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HandoffManifestError(f"{label} must be an ISO-8601 date-time") from exc
    if parsed.tzinfo is None:
        raise HandoffManifestError(f"{label} must include a timezone")
    return text


def _formatter_config_sha256(bundle_root: Path) -> str:
    config_files: list[dict[str, str]] = []
    for relative in sorted(_FORMATTER_CONFIG_FILES):
        candidate = bundle_root / relative
        if not candidate.is_file():
            continue
        config = _contained(
            bundle_root,
            PurePosixPath(relative),
            "formatter config file",
            strict=True,
        )
        _, digest = _digest(config)
        config_files.append({"path": relative, "sha256": digest})
    payload = {
        "default_profile": _FORMATTER_DEFAULT_PROFILE,
        "format_config_files": config_files,
    }
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def formatter_fingerprint(bundle_root: Path) -> dict[str, str]:
    """Resolve the deterministic formatter fingerprint used by strict custody."""
    executable = shutil.which(_FORMATTER_NAME)
    if executable is None:
        raise HandoffManifestError(
            "--require-custody cannot resolve formatter fingerprint: "
            "ruff is not available on PATH"
        )
    try:
        completed = subprocess.run(
            [executable, "--version"],
            cwd=bundle_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HandoffManifestError(
            "--require-custody cannot resolve formatter fingerprint: "
            f"ruff --version failed: {exc}"
        ) from exc
    if completed.returncode != 0:
        raise HandoffManifestError(
            "--require-custody cannot resolve formatter fingerprint: "
            f"ruff --version exited {completed.returncode}"
        )
    version_output = completed.stdout.strip()
    match = re.fullmatch(r"ruff\s+(\S+)", version_output)
    if match is None:
        raise HandoffManifestError(
            "--require-custody cannot resolve formatter fingerprint: "
            f"unexpected ruff version output {version_output!r}"
        )
    return {
        "name": _FORMATTER_NAME,
        "version": match.group(1),
        "config_sha256": _formatter_config_sha256(bundle_root),
        "invocation": _FORMATTER_INVOCATION,
        "mode": _FORMATTER_MODE,
    }


def _manifest_formatter_fingerprint(
    raw_custody: dict[str, Any],
) -> dict[str, str] | None:
    if "formatter_fingerprint" not in raw_custody:
        return None
    raw_fingerprint = raw_custody["formatter_fingerprint"]
    if not isinstance(raw_fingerprint, dict):
        raise HandoffManifestError("custody.formatter_fingerprint must be an object")
    missing = _FORMATTER_FINGERPRINT_FIELDS.difference(raw_fingerprint)
    if missing:
        fields = ", ".join(sorted(missing))
        raise HandoffManifestError(
            "custody.formatter_fingerprint is missing fields: " + fields
        )
    config_sha256 = _string(
        raw_fingerprint.get("config_sha256"),
        "custody.formatter_fingerprint.config_sha256",
    )
    if _SHA256_RE.fullmatch(config_sha256) is None:
        raise HandoffManifestError(
            "custody.formatter_fingerprint.config_sha256 must be lowercase SHA-256"
        )
    return {
        "name": _string(
            raw_fingerprint.get("name"), "custody.formatter_fingerprint.name"
        ),
        "version": _string(
            raw_fingerprint.get("version"),
            "custody.formatter_fingerprint.version",
        ),
        "config_sha256": config_sha256,
        "invocation": _string(
            raw_fingerprint.get("invocation"),
            "custody.formatter_fingerprint.invocation",
        ),
        "mode": _string(
            raw_fingerprint.get("mode"), "custody.formatter_fingerprint.mode"
        ),
    }


def _manifest_custody(payload: dict[str, Any]) -> dict[str, object]:
    raw_custody = payload.get("custody")
    if not isinstance(raw_custody, dict):
        raise HandoffManifestError("owner-aware manifest requires custody metadata")
    receipt = raw_custody.get("receipt")
    if not isinstance(receipt, dict):
        raise HandoffManifestError("custody.receipt must be an object")
    digest = _string(receipt.get("sha256"), "custody.receipt.sha256")
    if _SHA256_RE.fullmatch(digest) is None:
        raise HandoffManifestError("custody.receipt.sha256 must be lowercase SHA-256")
    custody: dict[str, object] = {
        "stream": _string(raw_custody.get("stream"), "custody.stream"),
        "owner": _string(raw_custody.get("owner"), "custody.owner"),
        "receipt": {
            "reference": _string(receipt.get("reference"), "custody.receipt.reference"),
            "sha256": digest,
            "freshness": _enum(
                receipt.get("freshness"),
                "custody.receipt.freshness",
                _RECEIPT_FRESHNESS,
            ),
            "observed_at": _date_time(
                receipt.get("observed_at"), "custody.receipt.observed_at"
            ),
        },
    }
    formatter = _manifest_formatter_fingerprint(raw_custody)
    if formatter is not None:
        custody["formatter_fingerprint"] = formatter
    return custody


def _require_formatter_fingerprint(
    manifest: HandoffManifest, bundle_root: Path
) -> None:
    if manifest.custody is None:
        raise HandoffManifestError(
            "--require-custody requires formatter fingerprint metadata"
        )
    declared = manifest.custody.get("formatter_fingerprint")
    if not isinstance(declared, dict):
        raise HandoffManifestError(
            "--require-custody requires custody.formatter_fingerprint"
        )
    observed = formatter_fingerprint(bundle_root)
    if declared != observed:
        expected_text = json.dumps(observed, sort_keys=True, separators=(",", ":"))
        declared_text = json.dumps(declared, sort_keys=True, separators=(",", ":"))
        raise HandoffManifestError(
            "--require-custody rejects formatter fingerprint mismatch: "
            f"expected={expected_text} observed={declared_text}"
        )


def _file_custody(record: dict[str, Any], index: int) -> dict[str, str]:
    raw_custody = record.get("custody")
    if not isinstance(raw_custody, dict):
        raise HandoffManifestError(f"files[{index}].custody must be an object")
    return {
        "status": _enum(
            raw_custody.get("status"),
            f"files[{index}].custody.status",
            _CUSTODY_STATUSES,
        ),
        "overlap": _enum(
            raw_custody.get("overlap"),
            f"files[{index}].custody.overlap",
            _OVERLAP_STATUSES,
        ),
    }


def _declared_size(record: dict[str, Any], label: str) -> tuple[int | None, bool]:
    key = (
        "bytes"
        if "bytes" in record
        else "size"
        if "size" in record
        else "byte_size"
        if "byte_size" in record
        else None
    )
    if key is None:
        return None, False
    value = record[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise HandoffManifestError(f"{label}.{key} must be a non-negative integer")
    return value, True


def _entry(
    record: object,
    *,
    index: int,
    source_key: str,
    destination_key: str,
    owner_aware: bool = False,
) -> HandoffEntry:
    if not isinstance(record, dict):
        raise HandoffManifestError(f"files[{index}] must be an object")
    destination = _safe_relative(
        record.get(destination_key), f"files[{index}].{destination_key}"
    )
    source = _safe_relative(record.get(source_key), f"files[{index}].{source_key}")
    digest = _string(record.get("sha256"), f"files[{index}].sha256")
    if _SHA256_RE.fullmatch(digest) is None:
        raise HandoffManifestError(f"files[{index}].sha256 must be lowercase SHA-256")
    size, size_declared = _declared_size(record, f"files[{index}]")
    return HandoffEntry(
        destination,
        source,
        digest,
        size,
        size_declared,
        _file_custody(record, index) if owner_aware else None,
    )


def _legacy_entries(payload: dict[str, Any]) -> tuple[tuple[HandoffEntry, ...], bool]:
    records = payload.get("files")
    if isinstance(records, list):
        entries: list[HandoffEntry] = []
        for index, record in enumerate(records):
            if isinstance(record, dict) and "artifact_path" in record:
                entries.append(
                    _entry(
                        record,
                        index=index,
                        source_key="artifact_path",
                        destination_key="path",
                    )
                )
            else:
                entries.append(
                    _entry(
                        record,
                        index=index,
                        source_key="path",
                        destination_key="path",
                    )
                )
        return tuple(entries), True

    records = payload.get("changed_files")
    if isinstance(records, list):
        entries = []
        for index, record in enumerate(records):
            if isinstance(record, dict) and {
                "repo_path",
                "bundle_path",
            }.issubset(record):
                entries.append(
                    _entry(
                        record,
                        index=index,
                        source_key="bundle_path",
                        destination_key="repo_path",
                    )
                )
            else:
                entries.append(
                    _entry(
                        record,
                        index=index,
                        source_key="path",
                        destination_key="path",
                    )
                )
        return tuple(entries), True
    raise HandoffManifestError("manifest must contain a files array")


def load_manifest(path: Path, *, require_custody: bool = False) -> HandoffManifest:
    payload = _read_object(path)
    schema = payload.get("schema")
    schema_name = schema if isinstance(schema, str) else None
    owner_aware = SUPPORTED_CANONICAL_SCHEMAS.get(schema_name, False)
    custody: dict[str, object] | None = None
    if schema_name in SUPPORTED_CANONICAL_SCHEMAS:
        if not isinstance(payload.get("exact_base"), str) or not payload["exact_base"]:
            raise HandoffManifestError(
                "canonical manifest requires a non-empty exact_base"
            )
        records = payload.get("files")
        if not isinstance(records, list) or not records:
            raise HandoffManifestError("canonical manifest.files must be non-empty")
        if owner_aware:
            for index, record in enumerate(records):
                if not isinstance(record, dict) or "bytes" not in record:
                    raise HandoffManifestError(
                        f"files[{index}].bytes is required by the v0.2 contract"
                    )
        entries = tuple(
            _entry(
                record,
                index=index,
                source_key="artifact_path",
                destination_key="path",
                owner_aware=owner_aware,
            )
            for index, record in enumerate(records)
        )
        if any(not entry.size_declared for entry in entries):
            raise HandoffManifestError(
                "canonical manifest requires bytes or size for every file"
            )
        if owner_aware:
            custody = _manifest_custody(payload)
        legacy = False
    elif (
        schema == "tmcp-iteration-handoff-v0.1"
        or payload.get("schema_version") in {1, 2}
        or payload.get("handoff_version") == "1.0"
    ):
        entries, legacy = _legacy_entries(payload)
    else:
        raise HandoffManifestError(
            "unsupported manifest schema; expected "
            f"{CANONICAL_SCHEMA} or a supported legacy handoff manifest"
        )
    if not entries:
        raise HandoffManifestError("manifest must declare at least one file")
    destinations = [entry.destination for entry in entries]
    if len(set(destinations)) != len(destinations):
        raise HandoffManifestError("manifest contains duplicate destination paths")
    exact_base = payload.get("exact_base")
    if exact_base is None and isinstance(payload.get("base"), dict):
        exact_base = payload["base"].get("commit")
    if exact_base is not None and not isinstance(exact_base, str):
        raise HandoffManifestError("exact_base/base.commit must be a string")
    manifest = HandoffManifest(
        schema if isinstance(schema, str) else "legacy",
        exact_base,
        entries,
        legacy,
        custody,
    )
    if require_custody:
        if not manifest.custody or manifest.legacy:
            raise HandoffManifestError(
                "--require-custody requires tmcp-handoff-manifest-v0.2 metadata"
            )
        receipt = manifest.custody["receipt"]
        if not isinstance(receipt, dict) or receipt.get("freshness") != "current":
            raise HandoffManifestError(
                "--require-custody requires a current receipt freshness status"
            )
        for entry in manifest.entries:
            if entry.custody is None:
                raise HandoffManifestError(
                    f"--require-custody requires file custody metadata: {entry.destination}"
                )
            if entry.custody["status"] != "verified":
                raise HandoffManifestError(
                    f"--require-custody rejects {entry.destination}: "
                    f"status={entry.custody['status']}"
                )
            if entry.custody["overlap"] != "none":
                raise HandoffManifestError(
                    f"--require-custody rejects {entry.destination}: "
                    f"overlap={entry.custody['overlap']}"
                )
    return manifest


def _contained(
    root: Path, relative: PurePosixPath, label: str, *, strict: bool
) -> Path:
    root_resolved = root.resolve()
    candidate = root / Path(*relative.parts)
    try:
        resolved = candidate.resolve(strict=strict)
    except FileNotFoundError as exc:
        raise HandoffManifestError(f"{label} does not exist: {candidate}") from exc
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise HandoffManifestError(f"{label} escapes its root: {relative}") from exc
    return resolved


def _digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _source_relative(entry: HandoffEntry, manifest_path: Path) -> PurePosixPath:
    # Canonical and v0.8 manifests declare artifact_path explicitly. Legacy
    # changed_files bundles store payloads under files/<destination>.
    if entry.source != entry.destination:
        return entry.source
    payload = _read_object(manifest_path)
    if payload.get("schema") == "tmcp-iteration-handoff-v0.1":
        return PurePosixPath("files", *entry.source.parts)
    if (
        payload.get("schema_version") in {1, 2}
        or payload.get("handoff_version") == "1.0"
    ) and isinstance(payload.get("changed_files"), list):
        return PurePosixPath("files", *entry.source.parts)
    return entry.source


def validate_sources(
    manifest_path: Path,
    bundle_root: Path,
    *,
    require_custody: bool = False,
) -> list[dict[str, object]]:
    manifest = load_manifest(manifest_path, require_custody=require_custody)
    if require_custody:
        _require_formatter_fingerprint(manifest, bundle_root)
    observed: list[dict[str, object]] = []
    for entry in manifest.entries:
        source_relative = _source_relative(entry, manifest_path)
        source = _contained(bundle_root, source_relative, "source file", strict=True)
        size, digest = _digest(source)
        if entry.size is not None and size != entry.size:
            raise HandoffManifestError(
                f"size mismatch for {entry.destination}: expected {entry.size}, observed {size}"
            )
        if digest != entry.sha256:
            raise HandoffManifestError(
                f"SHA-256 mismatch for {entry.destination}: expected {entry.sha256}, observed {digest}"
            )
        row: dict[str, object] = {
            "path": entry.destination.as_posix(),
            "source": source_relative.as_posix(),
            "bytes": size,
            "sha256": digest,
        }
        if entry.custody is not None:
            row["custody"] = dict(entry.custody)
        observed.append(row)
    return observed


def _destination(root: Path, relative: PurePosixPath) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / Path(*relative.parts)
    for parent in candidate.parents:
        if parent == root:
            break
        if parent.exists() and parent.is_symlink():
            raise HandoffManifestError(f"destination parent is a symlink: {parent}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise HandoffManifestError(f"destination escapes its root: {relative}") from exc
    return candidate


def replay(
    manifest_path: Path,
    bundle_root: Path,
    destination_root: Path,
    *,
    force: bool,
    require_custody: bool = False,
) -> list[dict[str, object]]:
    manifest = load_manifest(manifest_path, require_custody=require_custody)
    source_results = validate_sources(
        manifest_path,
        bundle_root,
        require_custody=require_custody,
    )
    source_by_path = {row["path"]: row for row in source_results}
    destinations = {
        entry.destination: _destination(destination_root, entry.destination)
        for entry in manifest.entries
    }
    expected_by_path = {row["path"]: row for row in source_results}
    for entry in manifest.entries:
        destination = destinations[entry.destination]
        if not destination.exists():
            continue
        size, digest = _digest(destination)
        expected = expected_by_path[entry.destination.as_posix()]
        if size == expected["bytes"] and digest == expected["sha256"]:
            continue
        if not force:
            raise HandoffManifestError(
                f"destination differs for {entry.destination}; pass --force to replace"
            )
    copied = 0
    skipped = 0
    for entry in manifest.entries:
        destination = destinations[entry.destination]
        if destination.exists():
            size, digest = _digest(destination)
            expected = expected_by_path[entry.destination.as_posix()]
            if size == expected["bytes"] and digest == expected["sha256"]:
                skipped += 1
                continue
        source = _contained(
            bundle_root,
            _source_relative(entry, manifest_path),
            "source file",
            strict=True,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".handoff.tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                with source.open("rb") as input_stream:
                    shutil.copyfileobj(input_stream, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
            copied_size, copied_digest = _digest(Path(temporary_name))
            expected = expected_by_path[entry.destination.as_posix()]
            if copied_size != expected["bytes"] or copied_digest != expected["sha256"]:
                raise HandoffManifestError(
                    f"staged copy mismatch for {entry.destination}"
                )
            os.replace(temporary_name, destination)
            temporary_name = None
            copied += 1
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
    return [dict(row) for row in source_by_path.values()] + [
        {"copied": copied, "skipped": skipped}
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "replay"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--bundle-root",
        type=Path,
        help="Root containing manifest payload files; defaults to the manifest directory.",
    )
    parser.add_argument(
        "--destination-root",
        type=Path,
        help="Repository/worktree root for replay destinations.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace differing destination files after source validation.",
    )
    parser.add_argument(
        "--require-custody",
        action="store_true",
        help=(
            "Require owner-aware v0.2 metadata, a current receipt, verified files, "
            "no unresolved/shared overlap, and a matching formatter fingerprint."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = args.manifest.resolve()
    bundle_root = (args.bundle_root or manifest_path.parent).resolve()
    try:
        if args.command == "verify":
            if args.destination_root is not None:
                raise HandoffManifestError("verify does not accept --destination-root")
            manifest = load_manifest(
                manifest_path,
                require_custody=args.require_custody,
            )
            rows = validate_sources(
                manifest_path,
                bundle_root,
                require_custody=args.require_custody,
            )
            result = {
                "ok": True,
                "command": "verify",
                "schema": manifest.schema,
                "legacy": manifest.legacy,
                "exact_base": manifest.exact_base,
                "custody": manifest.custody,
                "files": rows,
            }
        else:
            if args.destination_root is None:
                raise HandoffManifestError("replay requires --destination-root")
            manifest = load_manifest(manifest_path)
            rows = replay(
                manifest_path,
                bundle_root,
                args.destination_root.resolve(),
                force=args.force,
                require_custody=args.require_custody,
            )
            result = {
                "ok": True,
                "command": "replay",
                "schema": manifest.schema,
                "legacy": manifest.legacy,
                "exact_base": manifest.exact_base,
                "custody": manifest.custody,
                "files": rows,
            }
    except HandoffManifestError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
