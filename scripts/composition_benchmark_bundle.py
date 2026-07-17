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
import re
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

from tmcp_runtime.safety.redaction import (  # noqa: E402
    merge_redactions,
    redact_sensitive_text,
)


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
# Every external artifact is untrusted until it has passed the same bounded
# JSON/text scan.  The benchmark runner validates semantics later; this guard
# prevents credentials and opaque host material from being carried into that
# runner in the first place.
_SENSITIVE_FILENAMES = BUNDLE_FILENAMES
_MANIFEST_FIELDS = frozenset({"schema", "path", "artifacts", "evidence_trust"})
_EVIDENCE_RECORD_FIELDS = _MANIFEST_FIELDS | {"manifest_digest"}
_SHA256_DIGEST_RE = re.compile(r"[a-f0-9]{64}")
_JSON_PATH_INDEX = "*"
_MAX_SENSITIVE_JSON_DEPTH = 48

# These are closed, contract-owned fields whose values can legitimately carry
# a deterministic identifier, a digest-backed JSON envelope, or an artifact
# reference longer than the generic high-entropy heuristic allows.  Explicit
# credential patterns are still rejected in these fields.  Do not replace this
# with a suffix match: unknown ``*_digest`` fields remain subject to scanning.
_STRUCTURED_HIGH_ENTROPY_VALUE_FIELDS = frozenset(
    {
        "artifact",
        "artifact_digest",
        "benchmark_control_input_digest",
        "benchmark_execution_recipe_digest",
        "binding_digest",
        "canonical_json",
        "capsule",
        "capsule_digest",
        "compiler_contract_digest",
        "composition_plan_digest",
        "content_digest",
        "content_digests",
        "context_accounting_digest",
        "context_digest",
        "contract_digest",
        "control_input_digest",
        "control_plan_digest",
        "evaluator_artifacts_digest",
        "evidence_refs",
        "execution_artifact_digest",
        "execution_digest",
        "execution_recipe_digest",
        "graph_digest",
        "handoff_digest",
        "host_artifact_digest",
        "host_receipt_digest",
        "host_results_digest",
        "index_digest",
        "incoming_handoff_digests",
        "input_digest",
        "naive_union_capsule_digest",
        "observation_payload_digest",
        "packet_digest",
        "phase_capsule_trace",
        "preflight_artifact",
        "preflight_capsule_digest",
        "preflight_digest",
        "phase_capsule_binding_digest",
        "raw_sha256",
        "receipt_digest",
        "request_id",
        "result_digest",
        "run_manifest_digest",
        "semantic_proposals_digest",
        "slice_digest",
        "source_digest",
    }
)
_SAFE_RUN_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+){2,}")

# The scanner permits SHA-256 strings only where the public contracts declare
# a digest.  These exact path rules cover the two host-provided evidence files;
# the remaining compiler artifacts are additionally checked against their
# contract schema below.  Never widen this to a suffix-based ``*_digest`` rule:
# that would let a caller hide an opaque identifier in an arbitrary field.
_ARTIFACT_SCHEMA_FILENAMES = {
    "benchmark-run-plan.json": "tmcp-composition-benchmark-run-plan-v0.1.schema.json",
    "semantic-proposals.json": "tmcp-composition-benchmark-semantic-proposals-v0.1.schema.json",
    "benchmark-control-plan.json": "tmcp-composition-benchmark-control-plan-v0.1.schema.json",
    "host-results.json": "tmcp-composition-benchmark-host-results-v0.1.schema.json",
    "evaluator-artifacts.json": "tmcp-composition-benchmark-evaluator-artifacts-v0.1.schema.json",
    "benchmark-observations.json": "tmcp-composition-benchmark-observations-v0.1.schema.json",
}

# These are deliberately path-scoped rather than a permissive ``*_digest``
# rule.  Host evidence regularly contains SHA-256 values required by the
# benchmark contracts, while arbitrary evidence, IDs, or extension fields must
# remain subject to the normal sensitive-text scan.  If a contract adds a
# digest-bearing field, it fails closed here until this small allowlist is
# reviewed alongside that schema change.
_HOST_RESULT_DIGEST_PATHS = frozenset(
    {
        ("run_manifest_digest",),
        ("control_plan_digest",),
        ("routing_runs", _JSON_PATH_INDEX, "input_digest"),
        (
            "behavioral_runs",
            _JSON_PATH_INDEX,
            "variants",
            _JSON_PATH_INDEX,
            "input_packet_digest",
        ),
        (
            "behavioral_runs",
            _JSON_PATH_INDEX,
            "variants",
            _JSON_PATH_INDEX,
            "execution_recipe_digest",
        ),
    }
)
_HOST_RECEIPT_PREFIX = (
    "behavioral_runs",
    _JSON_PATH_INDEX,
    "variants",
    _JSON_PATH_INDEX,
    "tmcp_run_receipt",
)
_HOST_RECEIPT_DIGEST_SUFFIXES = frozenset(
    {
        ("graph_digest",),
        ("content_digests", _JSON_PATH_INDEX),
        ("context_accounting_digest",),
        ("preflight_capsule_digest",),
        ("phase_capsule_trace", _JSON_PATH_INDEX, "capsule_digest"),
        (
            "phase_capsule_trace",
            _JSON_PATH_INDEX,
            "incoming_handoff_digests",
            _JSON_PATH_INDEX,
        ),
        ("benchmark_control_input_digest",),
        ("benchmark_execution_recipe_digest",),
        ("execution_context", "context_accounting_digest"),
        ("execution_context", "preflight_capsule_digest"),
        (
            "execution_context",
            "phase_capsule_trace",
            _JSON_PATH_INDEX,
            "capsule_digest",
        ),
        (
            "execution_context",
            "phase_capsule_trace",
            _JSON_PATH_INDEX,
            "incoming_handoff_digests",
            _JSON_PATH_INDEX,
        ),
    }
)
_EVALUATOR_ARTIFACT_DIGEST_PATHS = frozenset(
    {
        ("run_manifest_digest",),
        ("control_plan_digest",),
        ("fixture_evaluations", _JSON_PATH_INDEX, "rubric_digest"),
        (
            "fixture_evaluations",
            _JSON_PATH_INDEX,
            "variants",
            _JSON_PATH_INDEX,
            "input_packet_digest",
        ),
        (
            "fixture_evaluations",
            _JSON_PATH_INDEX,
            "variants",
            _JSON_PATH_INDEX,
            "execution_recipe_digest",
        ),
        (
            "fixture_evaluations",
            _JSON_PATH_INDEX,
            "variants",
            _JSON_PATH_INDEX,
            "execution_artifact_digest",
        ),
    }
)


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


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object while rejecting duplicate keys hidden by ``json``."""

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


def _parse_sensitive_artifact(filename: str, serialized: str) -> Mapping[str, object]:
    """Parse sensitive release evidence without silently dropping JSON data."""

    try:
        payload = json.loads(
            serialized,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise CompositionBenchmarkBundleError(
            f"{filename} must be valid JSON with unique object keys so TMCP can "
            "scan it for sensitive text."
        ) from exc
    if not isinstance(payload, Mapping):
        raise CompositionBenchmarkBundleError(
            f"{filename} must be a JSON object so TMCP can scan it for sensitive text."
        )
    return payload


def _normalized_json_path(path: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(
        _JSON_PATH_INDEX if isinstance(item, int) else str(item) for item in path
    )


def _is_structural_digest(
    filename: str, path: tuple[object, ...], value: str
) -> bool:
    """Return whether an exact SHA-256 is allowed at this schema path only."""

    if _SHA256_DIGEST_RE.fullmatch(value) is None:
        return False
    normalized = _normalized_json_path(path)
    if filename == "host-results.json":
        if normalized in _HOST_RESULT_DIGEST_PATHS:
            return True
        if normalized[: len(_HOST_RECEIPT_PREFIX)] != _HOST_RECEIPT_PREFIX:
            return False
        return normalized[len(_HOST_RECEIPT_PREFIX) :] in _HOST_RECEIPT_DIGEST_SUFFIXES
    if filename == "evaluator-artifacts.json":
        return normalized in _EVALUATOR_ARTIFACT_DIGEST_PATHS
    return False


_SCHEMA_CACHE: dict[Path, Mapping[str, object]] = {}


def _schema_document(path: Path) -> Mapping[str, object]:
    """Load a bundled contract schema without accepting a caller-controlled path."""

    cached = _SCHEMA_CACHE.get(path)
    if cached is not None:
        return cached
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompositionBenchmarkBundleError(
            f"could not load benchmark artifact schema: {path.name}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise CompositionBenchmarkBundleError(
            f"benchmark artifact schema must be an object: {path.name}"
        )
    document = dict(payload)
    _SCHEMA_CACHE[path] = document
    return document


def _schema_pointer(document: Mapping[str, object], fragment: str) -> Mapping[str, object]:
    if fragment in {"", "#"}:
        return document
    if not fragment.startswith("#/"):
        raise CompositionBenchmarkBundleError(
            "benchmark artifact schema contains an unsupported reference fragment."
        )
    value: object = document
    for raw_part in fragment[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or part not in value:
            raise CompositionBenchmarkBundleError(
                "benchmark artifact schema contains an unresolved reference."
            )
        value = value[part]
    if not isinstance(value, Mapping):
        raise CompositionBenchmarkBundleError(
            "benchmark artifact schema reference must resolve to an object."
        )
    return value


def _schema_reference(
    reference: str, current_path: Path
) -> tuple[Mapping[str, object], Path]:
    target, separator, fragment = reference.partition("#")
    schema_root = PLUGIN_ROOT / "schemas"
    if target:
        candidate = (current_path.parent / target).resolve()
        try:
            candidate.relative_to(schema_root.resolve())
        except ValueError as exc:
            raise CompositionBenchmarkBundleError(
                "benchmark artifact schema reference escapes the bundled schema root."
            ) from exc
    else:
        candidate = current_path
    return _schema_pointer(_schema_document(candidate), f"#{fragment}" if separator else ""), candidate


def _expanded_schema_contexts(
    contexts: list[tuple[Mapping[str, object], Path]],
) -> list[tuple[Mapping[str, object], Path]]:
    """Expand local contract references for one JSON value.

    This is intentionally a narrow schema walker, not a general JSON-Schema
    validator.  Its only authority is deciding whether a value is at an exact
    contract-declared SHA-256 position before the sensitive-text scanner skips
    it.  Unknown/additional fields deliberately receive no digest exemption.
    """

    expanded: list[tuple[Mapping[str, object], Path]] = []
    pending = list(contexts)
    seen: set[tuple[Path, int]] = set()
    while pending:
        schema, schema_path = pending.pop()
        marker = (schema_path, id(schema))
        if marker in seen:
            continue
        seen.add(marker)
        expanded.append((schema, schema_path))
        reference = schema.get("$ref")
        if isinstance(reference, str):
            pending.append(_schema_reference(reference, schema_path))
        for combinator in ("allOf", "anyOf", "oneOf"):
            branches = schema.get(combinator)
            if isinstance(branches, list):
                pending.extend(
                    (branch, schema_path)
                    for branch in branches
                    if isinstance(branch, Mapping)
                )
    return expanded


def _schema_child_contexts(
    contexts: list[tuple[Mapping[str, object], Path]], key: str | int
) -> list[tuple[Mapping[str, object], Path]]:
    children: list[tuple[Mapping[str, object], Path]] = []
    for schema, schema_path in _expanded_schema_contexts(contexts):
        if isinstance(key, int):
            items = schema.get("items")
            if isinstance(items, Mapping):
                children.append((items, schema_path))
            continue
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            property_schema = properties.get(key)
            if isinstance(property_schema, Mapping):
                children.append((property_schema, schema_path))
                continue
        additional = schema.get("additionalProperties")
        if isinstance(additional, Mapping):
            children.append((additional, schema_path))
    return children


def _schema_declares_sha256(
    contexts: list[tuple[Mapping[str, object], Path]],
) -> bool:
    return any(
        schema.get("type") == "string"
        and schema.get("pattern") == "^[a-f0-9]{64}$"
        for schema, _schema_path in _expanded_schema_contexts(contexts)
    )


def _artifact_schema_contexts(
    filename: str,
) -> list[tuple[Mapping[str, object], Path]]:
    schema_filename = _ARTIFACT_SCHEMA_FILENAMES.get(filename)
    if schema_filename is None:
        raise CompositionBenchmarkBundleError(
            f"missing bundled schema mapping for {filename}."
        )
    path = (PLUGIN_ROOT / "schemas" / schema_filename).resolve()
    return [(_schema_document(path), path)]


def _scan_sensitive_json_value(
    filename: str,
    value: object,
    *,
    path: tuple[object, ...] = (),
    depth: int = 0,
    schema_contexts: list[tuple[Mapping[str, object], Path]],
) -> dict[str, int]:
    """Scan every JSON key and non-structural value within a bounded tree."""

    if depth > _MAX_SENSITIVE_JSON_DEPTH:
        raise CompositionBenchmarkBundleError(
            f"{filename} exceeds the maximum JSON nesting depth for sensitive scanning."
        )
    redactions: dict[str, int] = {}
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _redacted_key, key_redactions = redact_sensitive_text(
                str(key), enabled=True
            )
            merge_redactions(redactions, key_redactions)
            child_path = (*path, str(key))
            child_contexts = _schema_child_contexts(schema_contexts, str(key))
            if isinstance(nested, str) and (
                _is_structural_digest(filename, child_path, nested)
                or (
                    _SHA256_DIGEST_RE.fullmatch(nested) is not None
                    and _schema_declares_sha256(child_contexts)
                )
            ):
                continue
            merge_redactions(
                redactions,
                _scan_sensitive_json_value(
                    filename,
                    nested,
                    path=child_path,
                    depth=depth + 1,
                    schema_contexts=child_contexts,
                ),
            )
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child_path = (*path, index)
            child_contexts = _schema_child_contexts(schema_contexts, index)
            if isinstance(nested, str) and (
                _is_structural_digest(filename, child_path, nested)
                or (
                    _SHA256_DIGEST_RE.fullmatch(nested) is not None
                    and _schema_declares_sha256(child_contexts)
                )
            ):
                continue
            merge_redactions(
                redactions,
                _scan_sensitive_json_value(
                    filename,
                    nested,
                    path=child_path,
                    depth=depth + 1,
                    schema_contexts=child_contexts,
                ),
            )
    elif isinstance(value, str):
        _redacted, value_redactions = redact_sensitive_text(value, enabled=True)
        field_name = next(
            (str(item) for item in reversed(path) if isinstance(item, str)),
            "",
        )
        if field_name in _STRUCTURED_HIGH_ENTROPY_VALUE_FIELDS or (
            field_name == "run_id" and _SAFE_RUN_ID_RE.fullmatch(value) is not None
        ):
            value_redactions.pop("long_high_entropy", None)
        merge_redactions(redactions, value_redactions)
    return redactions


def _scan_sensitive_serialization(filename: str, content: bytes) -> dict[str, object]:
    try:
        serialized = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompositionBenchmarkBundleError(
            f"{filename} must be UTF-8 so TMCP can scan it for sensitive text."
        ) from exc
    payload = _parse_sensitive_artifact(filename, serialized)
    redactions = _scan_sensitive_json_value(
        filename,
        payload,
        schema_contexts=_artifact_schema_contexts(filename),
    )
    if redactions:
        labels = ", ".join(sorted(redactions))
        raise CompositionBenchmarkBundleError(
            f"{filename} contains sensitive or high-entropy text ({labels}); "
            "redact it before creating a release bundle."
        )
    return {"status": "clear", "redactions": {}}


def freeze_composition_benchmark_artifacts(
    artifact_paths: Mapping[str, Path],
    *,
    expected_sha256: Mapping[str, str] | None = None,
) -> dict[str, bytes]:
    """Read, scan, and freeze exactly the six benchmark inputs.

    Release checks must never validate a mutable external path and later hand
    that same path to the benchmark runner.  This helper returns the verified
    bytes so callers can materialize a private, temporary runner input set.
    Explicit artifact paths use the same regular-file, bounded-size, and
    secret-scan boundary as the canonical source bundle.
    """

    expected_labels = {label for label, _filename in BUNDLE_ARTIFACTS}
    observed_labels = set(artifact_paths)
    if observed_labels != expected_labels:
        raise CompositionBenchmarkBundleError(
            "composition benchmark artifact labels must be exactly "
            f"{sorted(expected_labels)}; observed {sorted(observed_labels)}."
        )
    if expected_sha256 is not None and set(expected_sha256) != expected_labels:
        raise CompositionBenchmarkBundleError(
            "composition benchmark artifact digest labels must match the six inputs."
        )
    frozen: dict[str, bytes] = {}
    for label, filename in BUNDLE_ARTIFACTS:
        path = artifact_paths[label]
        if not isinstance(path, Path):
            raise CompositionBenchmarkBundleError(
                f"composition benchmark artifact path must be a Path: {label}"
            )
        content = _regular_artifact_bytes(path.expanduser(), filename=filename)
        _scan_sensitive_serialization(filename, content)
        digest = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None and expected_sha256[label] != digest:
            raise CompositionBenchmarkBundleError(
                "composition benchmark artifact changed after canonical bundle "
                f"resolution: {filename}"
            )
        frozen[label] = content
    return frozen


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
