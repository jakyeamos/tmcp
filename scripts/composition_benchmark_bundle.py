#!/usr/bin/env python3
"""Resolve the fixed, reviewable TMCP composition benchmark evidence bundle.

The benchmark inputs are intentionally external to the Python package.  A
release check needs a small, deterministic boundary around those files instead
of accepting arbitrary paths supplied by a caller.  This module owns that
boundary; callers can replay the resolved files with the benchmark assembler
and runner.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tmcp_runtime.safety.redaction import redact_sensitive_text  # noqa: E402


BUNDLE_SCHEMA = "tmcp-composition-benchmark-bundle-v0.1"
BUNDLE_RELATIVE_PATH = Path("docs") / "COMPOSITION_BENCHMARK_BUNDLE"
ADVISORY_EVIDENCE_TRUST = "advisory_untrusted"
MAX_BENCHMARK_ARTIFACT_BYTES = 16 * 1024 * 1024

# Keep the six release inputs explicit.  The logical labels align with the
# benchmark CLI arguments; filenames are the external review contract.
BUNDLE_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("run_plan", "benchmark-run-plan.json"),
    ("semantic_proposals", "semantic-proposals.json"),
    ("control_plan", "benchmark-control-plan.json"),
    ("host_results", "host-results.json"),
    ("evaluator_artifacts", "evaluator-artifacts.json"),
    ("observations", "benchmark-observations.json"),
)
BUNDLE_FILENAMES = frozenset(filename for _, filename in BUNDLE_ARTIFACTS)
_SENSITIVE_FILENAMES = frozenset({"host-results.json", "evaluator-artifacts.json"})
_MANIFEST_FIELDS = frozenset({"schema", "path", "artifacts", "evidence_trust"})
_EVIDENCE_RECORD_FIELDS = _MANIFEST_FIELDS | {"manifest_digest"}


class CompositionBenchmarkBundleError(ValueError):
    """Raised when the fixed benchmark bundle is unsafe or incomplete."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CompositionBenchmarkBundleError(
            "benchmark bundle manifest must be JSON serializable."
        ) from exc


def canonical_manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Return the digest of the canonical manifest fields, never its digest field."""

    observed = set(manifest)
    if observed != _MANIFEST_FIELDS:
        raise CompositionBenchmarkBundleError(
            "benchmark bundle manifest fields must be exactly "
            f"{sorted(_MANIFEST_FIELDS)}; observed {sorted(observed)}."
        )
    return hashlib.sha256(_canonical_bytes(manifest)).hexdigest()


def _relative_path_text(path: Path) -> str:
    return path.as_posix()


def _resolved_root(plugin_root: Path) -> Path:
    try:
        root = Path(plugin_root).resolve(strict=True)
    except OSError as exc:
        raise CompositionBenchmarkBundleError(
            f"benchmark bundle root cannot be resolved: {plugin_root}"
        ) from exc
    if not root.is_dir():
        raise CompositionBenchmarkBundleError(
            f"benchmark bundle root must be a directory: {root}"
        )
    return root


def _inside_root(root: Path, candidate: Path, *, label: str) -> Path:
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CompositionBenchmarkBundleError(
            f"{label} cannot be resolved: {candidate}"
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CompositionBenchmarkBundleError(
            f"{label} resolves outside the repository root: {candidate}"
        ) from exc
    return resolved


def _bundle_directory(root: Path) -> Path:
    expected = root / BUNDLE_RELATIVE_PATH
    try:
        metadata = expected.lstat()
    except FileNotFoundError as exc:
        raise CompositionBenchmarkBundleError(
            "missing composition benchmark bundle directory: "
            f"{BUNDLE_RELATIVE_PATH.as_posix()}"
        ) from exc
    except OSError as exc:
        raise CompositionBenchmarkBundleError(
            f"could not inspect composition benchmark bundle directory: {expected}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise CompositionBenchmarkBundleError(
            "composition benchmark bundle directory must not be a symlink."
        )
    if not stat.S_ISDIR(metadata.st_mode):
        raise CompositionBenchmarkBundleError(
            "composition benchmark bundle path must be a directory."
        )
    resolved = _inside_root(root, expected, label="benchmark bundle directory")
    if resolved != expected:
        # A symlink in an ancestor can make the visible repo-relative path point
        # elsewhere.  Reject it rather than producing an ambiguous review path.
        raise CompositionBenchmarkBundleError(
            "composition benchmark bundle path must resolve to its canonical "
            "repository location."
        )
    return resolved


def _regular_artifact_bytes(path: Path, *, filename: str) -> bytes:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise CompositionBenchmarkBundleError(
            f"missing composition benchmark artifact: {filename}"
        ) from exc
    except OSError as exc:
        raise CompositionBenchmarkBundleError(
            f"could not inspect composition benchmark artifact: {filename}"
        ) from exc
    if stat.S_ISLNK(before.st_mode):
        raise CompositionBenchmarkBundleError(
            f"composition benchmark artifact must not be a symlink: {filename}"
        )
    if not stat.S_ISREG(before.st_mode):
        raise CompositionBenchmarkBundleError(
            f"composition benchmark artifact must be a regular file: {filename}"
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CompositionBenchmarkBundleError(
            f"could not safely open composition benchmark artifact: {filename}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CompositionBenchmarkBundleError(
                f"composition benchmark artifact must be a regular file: {filename}"
            )
        if metadata.st_size > MAX_BENCHMARK_ARTIFACT_BYTES:
            raise CompositionBenchmarkBundleError(
                "composition benchmark artifact exceeds "
                f"{MAX_BENCHMARK_ARTIFACT_BYTES} bytes: {filename}"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(MAX_BENCHMARK_ARTIFACT_BYTES + 1)
        if (
            len(content) != metadata.st_size
            or len(content) > MAX_BENCHMARK_ARTIFACT_BYTES
        ):
            raise CompositionBenchmarkBundleError(
                f"composition benchmark artifact changed while reading: {filename}"
            )
        return content
    finally:
        os.close(descriptor)


def _scan_sensitive_serialization(filename: str, content: bytes) -> dict[str, object]:
    try:
        serialized = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompositionBenchmarkBundleError(
            f"{filename} must be UTF-8 so TMCP can scan it for sensitive text."
        ) from exc
    _redacted, redactions = redact_sensitive_text(serialized, enabled=True)
    if redactions:
        labels = ", ".join(sorted(redactions))
        raise CompositionBenchmarkBundleError(
            f"{filename} contains sensitive or high-entropy text ({labels}); "
            "redact it before creating a release bundle."
        )
    return {"status": "clear", "redactions": {}}


def _manifest_fields(
    *, artifact_hashes: Mapping[str, str]
) -> dict[str, Any]:
    artifacts = {
        filename: {
            "path": _relative_path_text(BUNDLE_RELATIVE_PATH / filename),
            "sha256": artifact_hashes[filename],
        }
        for _, filename in BUNDLE_ARTIFACTS
    }
    return {
        "schema": BUNDLE_SCHEMA,
        "path": _relative_path_text(BUNDLE_RELATIVE_PATH),
        "artifacts": artifacts,
        "evidence_trust": ADVISORY_EVIDENCE_TRUST,
    }


def _git_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


def _git_returncode(root: Path, arguments: list[str]) -> int | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            env=_git_environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.returncode


def validate_bundle_git_state(
    plugin_root: Path, bundle: Mapping[str, Any]
) -> list[str]:
    """Return Git tracking/HEAD-clean errors for every canonical artifact."""

    root = _resolved_root(plugin_root)
    record = bundle_evidence_record(bundle)
    artifacts = record["artifacts"]
    if not isinstance(artifacts, Mapping):  # Defensive; the projection fixes it.
        raise CompositionBenchmarkBundleError("benchmark bundle artifacts are invalid.")
    errors: list[str] = []
    for _, filename in BUNDLE_ARTIFACTS:
        entry = artifacts[filename]
        if not isinstance(entry, Mapping):
            raise CompositionBenchmarkBundleError(
                "benchmark bundle artifacts are invalid."
            )
        path = str(entry["path"])
        if _git_returncode(root, ["ls-files", "--error-unmatch", "--", path]) != 0:
            errors.append(f"benchmark bundle artifact must be Git-tracked: {path}")
            continue
        if _git_returncode(root, ["diff", "--quiet", "HEAD", "--", path]) != 0:
            errors.append(
                f"benchmark bundle artifact must be unchanged from HEAD: {path}"
            )
    return errors


def resolve_composition_benchmark_bundle(
    plugin_root: Path,
    *,
    require_git_clean: bool = False,
) -> dict[str, Any]:
    """Resolve the exact six-artifact bundle without following external paths.

    The returned manifest is JSON-safe and can be passed directly to
    :func:`bundle_evidence_record`.  It does not validate benchmark schemas or
    replay compiler inputs; those responsibilities remain with the assembler
    and runner.
    """

    root = _resolved_root(plugin_root)
    bundle_directory = _bundle_directory(root)
    try:
        entries = {entry.name: entry for entry in bundle_directory.iterdir()}
    except OSError as exc:
        raise CompositionBenchmarkBundleError(
            "could not enumerate composition benchmark bundle directory."
        ) from exc
    observed = set(entries)
    missing = sorted(BUNDLE_FILENAMES.difference(observed))
    unexpected = sorted(observed.difference(BUNDLE_FILENAMES))
    if missing or unexpected:
        raise CompositionBenchmarkBundleError(
            "composition benchmark bundle must contain exactly the six canonical "
            f"artifacts; missing={missing}, unexpected={unexpected}."
        )

    hashes: dict[str, str] = {}
    sizes: dict[str, int] = {}
    secret_scan: dict[str, object] = {}
    for _, filename in BUNDLE_ARTIFACTS:
        artifact = entries[filename]
        try:
            metadata = artifact.lstat()
        except OSError as exc:
            raise CompositionBenchmarkBundleError(
                f"could not inspect composition benchmark artifact: {filename}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise CompositionBenchmarkBundleError(
                f"composition benchmark artifact must not be a symlink: {filename}"
            )
        resolved = _inside_root(root, artifact, label=f"benchmark artifact {filename}")
        if resolved.parent != bundle_directory:
            raise CompositionBenchmarkBundleError(
                f"benchmark artifact resolves outside the canonical bundle: {filename}"
            )
        content = _regular_artifact_bytes(artifact, filename=filename)
        hashes[filename] = hashlib.sha256(content).hexdigest()
        sizes[filename] = len(content)
        if filename in _SENSITIVE_FILENAMES:
            secret_scan[filename] = _scan_sensitive_serialization(filename, content)

    fields = _manifest_fields(artifact_hashes=hashes)
    manifest = {
        **fields,
        "manifest_digest": canonical_manifest_digest(fields),
        "artifact_sizes": sizes,
        "secret_scan": secret_scan,
    }
    if require_git_clean:
        git_errors = validate_bundle_git_state(root, manifest)
        if git_errors:
            raise CompositionBenchmarkBundleError("; ".join(git_errors))
    return manifest


def bundle_evidence_record(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Project a resolved bundle into the exact release-evidence bundle object."""

    required = _MANIFEST_FIELDS | {
        "manifest_digest",
        "artifact_sizes",
        "secret_scan",
    }
    missing = sorted(required.difference(bundle))
    if missing:
        raise CompositionBenchmarkBundleError(
            f"resolved benchmark bundle is missing fields: {missing}."
        )
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise CompositionBenchmarkBundleError(
            "resolved benchmark bundle artifacts are invalid."
        )
    fields = {
        "schema": bundle["schema"],
        "path": bundle["path"],
        "artifacts": {
            str(filename): dict(entry)
            for filename, entry in artifacts.items()
            if isinstance(entry, Mapping)
        },
        "evidence_trust": bundle["evidence_trust"],
    }
    if len(fields["artifacts"]) != len(artifacts):
        raise CompositionBenchmarkBundleError(
            "resolved benchmark bundle artifacts are invalid."
        )
    digest = canonical_manifest_digest(fields)
    if bundle.get("manifest_digest") != digest:
        raise CompositionBenchmarkBundleError(
            "resolved benchmark bundle manifest_digest does not match canonical fields."
        )
    return {**fields, "manifest_digest": digest}


def validate_bundle_evidence_record(
    record: object, bundle: Mapping[str, Any]
) -> list[str]:
    """Validate that a release record repeats the resolved paths and hashes exactly."""

    if not isinstance(record, Mapping):
        return ["composition_benchmark.bundle must be an object"]
    observed = set(record)
    if observed != _EVIDENCE_RECORD_FIELDS:
        return [
            "composition_benchmark.bundle fields must be exactly "
            f"{sorted(_EVIDENCE_RECORD_FIELDS)}"
        ]
    try:
        expected = bundle_evidence_record(bundle)
    except CompositionBenchmarkBundleError as exc:
        return [str(exc)]
    errors: list[str] = []
    for key in sorted(_EVIDENCE_RECORD_FIELDS):
        if record.get(key) != expected[key]:
            errors.append(f"composition_benchmark.bundle.{key} does not match bundle")
    return errors
