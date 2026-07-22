"""Bounded secret scanning for composition-benchmark bundle artifacts.

This module deliberately owns only the untrusted JSON scanning policy.  Bundle
path resolution, bounded file reads, manifests, and Git-state checks remain in
``composition_benchmark_bundle`` so callers keep one stable boundary API.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from tmcp_runtime.safety.redaction import merge_redactions, redact_sensitive_text


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_SHA256_DIGEST_RE = re.compile(r"[a-f0-9]{64}")
_JSON_PATH_INDEX = "*"
_MAX_SENSITIVE_JSON_DEPTH = 48


class CompositionBenchmarkBundleError(ValueError):
    """Raised when the fixed benchmark bundle is unsafe or incomplete."""


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
        "source_digests",
        "source_slice_digests",
        "task_context_digest",
        "task_context_artifact",
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
    return (
        _schema_pointer(
            _schema_document(candidate), f"#{fragment}" if separator else ""
        ),
        candidate,
    )


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


def scan_sensitive_serialization(filename: str, content: bytes) -> dict[str, object]:
    """Reject secret-like JSON evidence while allowing contract-bound digests."""

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
