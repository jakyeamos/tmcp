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
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


CANONICAL_SCHEMA = "tmcp-handoff-manifest-v0.1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class HandoffManifestError(ValueError):
    """Raised when a manifest or replay target is unsafe or inconsistent."""


@dataclass(frozen=True)
class HandoffEntry:
    destination: PurePosixPath
    source: PurePosixPath
    sha256: str
    size: int | None
    size_declared: bool


@dataclass(frozen=True)
class HandoffManifest:
    schema: str
    exact_base: str | None
    entries: tuple[HandoffEntry, ...]
    legacy: bool


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


def _declared_size(record: dict[str, Any], label: str) -> tuple[int | None, bool]:
    key = "bytes" if "bytes" in record else "size" if "size" in record else None
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
    return HandoffEntry(destination, source, digest, size, size_declared)


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


def load_manifest(path: Path) -> HandoffManifest:
    payload = _read_object(path)
    schema = payload.get("schema")
    if schema == CANONICAL_SCHEMA:
        if not isinstance(payload.get("exact_base"), str) or not payload["exact_base"]:
            raise HandoffManifestError(
                "canonical manifest requires a non-empty exact_base"
            )
        records = payload.get("files")
        if not isinstance(records, list) or not records:
            raise HandoffManifestError("canonical manifest.files must be non-empty")
        entries = tuple(
            _entry(
                record,
                index=index,
                source_key="artifact_path",
                destination_key="path",
            )
            for index, record in enumerate(records)
        )
        if any(not entry.size_declared for entry in entries):
            raise HandoffManifestError(
                "canonical manifest requires bytes or size for every file"
            )
        legacy = False
    elif schema == "tmcp-iteration-handoff-v0.1" or payload.get("schema_version") in {
        1,
        2,
    }:
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
    return HandoffManifest(
        schema if isinstance(schema, str) else "legacy", exact_base, entries, legacy
    )


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
    if payload.get("schema_version") in {1, 2} and isinstance(
        payload.get("changed_files"), list
    ):
        return PurePosixPath("files", *entry.source.parts)
    return entry.source


def validate_sources(manifest_path: Path, bundle_root: Path) -> list[dict[str, object]]:
    manifest = load_manifest(manifest_path)
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
        observed.append(
            {
                "path": entry.destination.as_posix(),
                "source": source_relative.as_posix(),
                "bytes": size,
                "sha256": digest,
            }
        )
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
) -> list[dict[str, object]]:
    manifest = load_manifest(manifest_path)
    source_results = validate_sources(manifest_path, bundle_root)
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
    return [
        {
            "path": path,
            "source": row["source"],
            "bytes": row["bytes"],
            "sha256": row["sha256"],
        }
        for path, row in source_by_path.items()
    ] + [{"copied": copied, "skipped": skipped}]


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = args.manifest.resolve()
    bundle_root = (args.bundle_root or manifest_path.parent).resolve()
    try:
        if args.command == "verify":
            if args.destination_root is not None:
                raise HandoffManifestError("verify does not accept --destination-root")
            manifest = load_manifest(manifest_path)
            rows = validate_sources(manifest_path, bundle_root)
            result = {
                "ok": True,
                "command": "verify",
                "schema": manifest.schema,
                "legacy": manifest.legacy,
                "exact_base": manifest.exact_base,
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
            )
            result = {
                "ok": True,
                "command": "replay",
                "schema": manifest.schema,
                "legacy": manifest.legacy,
                "exact_base": manifest.exact_base,
                "files": rows,
            }
    except HandoffManifestError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
