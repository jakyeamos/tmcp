#!/usr/bin/env python3
"""Validate observable contract facts in a completed skill-fixture artifact.

This is intentionally a post-run check. The runner receives only the blind
prompt; this validator receives the artifact and a separate, reviewable spec.
It does not call a model or attempt to interpret the fixture bar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "tmcp-skill-fixture-artifact-validation-v0.1"
_MUTATION_PATTERN = re.compile(
    r"\b(?:wrote|overwrote|deleted|removed|changed|modified)\s+"
    r"(?:the\s+|any\s+|a\s+)?(?:file|files|target|artifact)\b",
    re.IGNORECASE,
)


def _text_fragments(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        fragments: list[str] = []
        for item in value:
            fragments.extend(_text_fragments(item))
        return fragments
    if isinstance(value, dict):
        fragments = []
        for key, item in value.items():
            if isinstance(key, str):
                fragments.append(key)
            fragments.extend(_text_fragments(item))
        return fragments
    return []


def _text_container_is_valid(
    value: object,
    *,
    allow_scalar: bool = False,
    allow_metadata: bool = False,
) -> bool:
    if allow_scalar and isinstance(value, str):
        return True
    if allow_metadata and (value is None or isinstance(value, (bool, int, float))):
        return True
    if isinstance(value, list):
        return all(
            isinstance(item, str)
            or _text_container_is_valid(item, allow_metadata=allow_metadata)
            for item in value
        )
    if isinstance(value, dict):
        return all(
            isinstance(key, str)
            and (
                isinstance(item, str)
                or _text_container_is_valid(item, allow_metadata=allow_metadata)
            )
            for key, item in value.items()
        )
    return False


def _has_final_label(response: str, label: str) -> bool:
    prefix = f"{label}:".casefold()
    return any(
        line.strip().casefold().startswith(prefix) for line in response.splitlines()
    )


def _contains_exact_value(response: str, expected: object) -> bool:
    if not isinstance(expected, str) or not expected:
        return False
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(expected)}(?![A-Za-z0-9_])"
    return re.search(pattern, response) is not None


def _mutation_matches(text: str) -> list[str]:
    matches: list[str] = []
    for line in text.splitlines():
        if _MUTATION_PATTERN.search(line):
            matches.append(line.strip())
    return matches


def _forbidden_matches(text: str, markers: Sequence[str]) -> list[str]:
    """Find forbidden markers unless the same line explicitly negates execution."""

    matches: list[str] = []
    for line in text.splitlines():
        lowered = line.casefold()
        for marker in markers:
            marker_lower = marker.casefold()
            marker_position = lowered.find(marker_lower)
            if marker_position < 0:
                continue
            before = lowered[max(0, marker_position - 70) : marker_position]
            after = lowered[
                marker_position + len(marker_lower) : marker_position
                + len(marker_lower)
                + 70
            ]
            negated_before = re.search(
                r"\b(?:did\s+not|not|never|no)\s+(?:run|perform|attempt|execute|activate|conduct|do)\b",
                before,
            )
            negated_after = re.search(
                r"\b(?:was|were|is|are)\s+not\s+(?:run|performed|attempted|executed|activated|conducted)\b",
                after,
            )
            if not negated_before and not negated_after:
                matches.append(line.strip())
                break
    return matches


def validate_fixture_artifact(
    artifact: Mapping[str, object],
    spec: Mapping[str, object],
) -> dict[str, Any]:
    """Return deterministic checks over one runner artifact.

    The spec contains only observable assertions needed after execution; it is
    never passed to the blind runner. Missing or malformed artifact fields
    fail closed rather than being coerced into a passing result.
    """

    configured_required_fields = _text_fragments(spec.get("required_artifact_fields"))
    required_fields = configured_required_fields or [
        "observations",
        "actions",
        "final_response",
    ]
    if spec.get("allow_missing_observations") is True:
        required_fields = [
            field for field in required_fields if field != "observations"
        ]
    missing_fields = [field for field in required_fields if field not in artifact]
    observations = _text_fragments(artifact.get("observations"))
    actions = _text_fragments(artifact.get("actions"))
    final_response = artifact.get("final_response")
    final_response_text = "\n".join(_text_fragments(final_response))
    allow_metadata = spec.get("allow_metadata_values") is True
    schema_passed = (
        not missing_fields
        and (
            "observations" not in artifact
            or _text_container_is_valid(
                artifact.get("observations"),
                allow_scalar=True,
                allow_metadata=allow_metadata,
            )
        )
        and (
            "actions" not in artifact
            or _text_container_is_valid(
                artifact.get("actions"),
                allow_scalar=True,
                allow_metadata=allow_metadata,
            )
        )
        and (
            "final_response" not in artifact
            or _text_container_is_valid(
                artifact.get("final_response"),
                allow_scalar=True,
                allow_metadata=allow_metadata,
            )
        )
    )

    labels = _text_fragments(spec.get("required_final_labels"))
    missing_labels = [
        label for label in labels if not _has_final_label(final_response_text, label)
    ]

    exact_value_configured = "exact_value" in spec
    exact_value = spec.get("exact_value")
    artifact_text = "\n".join(_text_fragments(artifact))
    exact_value_text = (
        artifact_text
        if spec.get("exact_value_scope") == "artifact"
        else final_response_text
    )
    exact_value_passed = (
        _contains_exact_value(exact_value_text, exact_value)
        if exact_value_configured
        else True
    )

    disclosure_terms = _text_fragments(spec.get("required_disclosure_terms"))
    disclosure_text = (
        artifact_text
        if spec.get("disclosure_scope") == "artifact"
        else final_response_text
    )
    disclosure_lower = disclosure_text.casefold()
    missing_disclosure_terms = [
        term for term in disclosure_terms if term.casefold() not in disclosure_lower
    ]
    disclosure_patterns = _text_fragments(spec.get("required_disclosure_patterns"))
    missing_disclosure_patterns: list[str] = []
    for pattern in disclosure_patterns:
        try:
            matched = (
                re.search(pattern, disclosure_text, flags=re.IGNORECASE) is not None
            )
        except re.error:
            matched = False
        if not matched:
            missing_disclosure_patterns.append(pattern)

    final_patterns = _text_fragments(spec.get("required_final_patterns"))
    missing_final_patterns: list[str] = []
    for pattern in final_patterns:
        try:
            matched = (
                re.search(pattern, final_response_text, flags=re.IGNORECASE) is not None
            )
        except re.error:
            matched = False
        if not matched:
            missing_final_patterns.append(pattern)

    activity_text = "\n".join((*observations, *actions))
    required_activity_markers = _text_fragments(spec.get("required_activity_markers"))
    missing_activity_markers = [
        marker
        for marker in required_activity_markers
        if marker.casefold() not in activity_text.casefold()
    ]
    required_activity_patterns = _text_fragments(spec.get("required_activity_patterns"))
    missing_activity_patterns: list[str] = []
    for pattern in required_activity_patterns:
        try:
            matched = re.search(pattern, activity_text, flags=re.IGNORECASE) is not None
        except re.error:
            matched = False
        if not matched:
            missing_activity_patterns.append(pattern)

    forbidden_markers = _text_fragments(spec.get("forbidden_action_markers"))
    forbidden_matches = _forbidden_matches(activity_text, forbidden_markers)

    mutation_matches = _mutation_matches(activity_text)

    boolean_expectations = spec.get("required_boolean_fields")
    if not isinstance(boolean_expectations, dict):
        boolean_expectations = {}
    boolean_failures: dict[str, object] = {}
    for field, expected in boolean_expectations.items():
        actual = artifact.get(field)
        if (
            not isinstance(expected, bool)
            or not isinstance(actual, bool)
            or actual is not expected
        ):
            boolean_failures[field] = {"expected": expected, "actual": actual}

    checks: dict[str, Any] = {
        "schema": {"passed": schema_passed, "missing_fields": missing_fields},
        "required_final_labels": {
            "passed": not missing_labels,
            "required": labels,
            "missing": missing_labels,
        },
        "exact_value": {
            "passed": exact_value_passed,
            "expected": exact_value,
            "configured": exact_value_configured,
            "scope": spec.get("exact_value_scope", "final_response"),
        },
        "required_activity": {
            "passed": not missing_activity_markers and not missing_activity_patterns,
            "required": required_activity_markers,
            "missing": missing_activity_markers,
            "required_patterns": required_activity_patterns,
            "missing_patterns": missing_activity_patterns,
        },
        "required_boolean_fields": {
            "passed": not boolean_failures,
            "expected": boolean_expectations,
            "failures": boolean_failures,
        },
        "required_disclosure": {
            "passed": not missing_disclosure_terms and not missing_disclosure_patterns,
            "required_terms": disclosure_terms,
            "missing_terms": missing_disclosure_terms,
            "required_patterns": disclosure_patterns,
            "missing_patterns": missing_disclosure_patterns,
        },
        "required_final_patterns": {
            "passed": not missing_final_patterns,
            "required": final_patterns,
            "missing": missing_final_patterns,
        },
        "forbidden_actions": {
            "passed": not forbidden_matches,
            "markers": forbidden_markers,
            "matches": forbidden_matches,
        },
        "mutations": {
            "passed": not mutation_matches,
            "matches": mutation_matches,
        },
    }
    passed = all(check["passed"] for check in checks.values())
    return {
        "schema": SCHEMA,
        "case_id": spec.get("case_id"),
        "passed": passed,
        "failed_observables": [
            name for name, check in checks.items() if not check["passed"]
        ],
        "checks": checks,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact_bytes = args.artifact.read_bytes()
    artifact = json.loads(artifact_bytes)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if not isinstance(artifact, dict) or not isinstance(spec, dict):
        raise SystemExit("artifact and spec must contain JSON objects")
    result = validate_fixture_artifact(artifact, spec)
    result["artifact"] = {
        "path": str(args.artifact),
        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
