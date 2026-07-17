#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tmcp_runtime.api.registry import VERSION  # noqa: E402
from scripts.composition_benchmark_bundle import (  # noqa: E402
    BUNDLE_ARTIFACTS,
    CompositionBenchmarkBundleError,
    resolve_composition_benchmark_bundle,
    validate_bundle_evidence_record,
)
from scripts.run_composition_benchmark import run_benchmark  # noqa: E402
from scripts.schema_contract_support import SchemaAssertionError  # noqa: E402

VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EVIDENCE_PATH = Path("docs") / "RELEASE_EVIDENCE.json"
WORKFLOW_PATH = Path(".github") / "workflows" / "verify.yml"
WORKFLOW_CONTRACT_PATH = ".github/workflows/verify.yml"
REQUIRED_RELEASE_TAG_PATTERNS = ("v*", "[0-9]*")
REQUIRED_RELEASE_EVIDENCE_COMMAND = "python scripts/check_release_evidence.py ."
REQUIRED_RELEASE_EVIDENCE_STEP_NAME = "Active release evidence"
COMPOSITION_BENCHMARK_MINIMUM_VERSION = (0, 6, 0)
COMPOSITION_BENCHMARK_EVIDENCE_SCHEMA = (
    "tmcp-composition-benchmark-release-evidence-v0.1"
)
COMPOSITION_BENCHMARK_SUMMARY_SCHEMA = "tmcp-composition-benchmark-summary-v0.1"
COMPOSITION_BENCHMARK_SUMMARY_PATH = Path("docs") / "COMPOSITION_BENCHMARK_SUMMARY.json"
COMPOSITION_ROUTING_GOLDEN_PATH = (
    Path("tests") / "fixtures" / "composition_routing_golden_v0_6.json"
)
COMPOSITION_BEHAVIORAL_FIXTURES_PATH = (
    Path("tests") / "fixtures" / "composition_behavioral_fixtures_v0_6.json"
)
COMPOSITION_ACCEPTANCE_CHECKS = frozenset(
    {
        "expected_skill_recall",
        "selected_skill_precision",
        "active_conflict_violations",
        "incoming_provenance_relationships",
        "expected_order",
        "context_ratio",
        "context_execution_mode",
        "synergy_lift",
        "compiler_lift",
        "order_lift",
    }
)
COMPOSITION_THRESHOLDS = {
    "expected_skill_recall": 1.0,
    "selected_skill_precision": 0.90,
    "provenance_relationship_coverage": 1.0,
    "synergy_lift": 0.10,
    "compiler_lift": 0.05,
    "order_lift": 0.05,
    "maximum_context_ratio": 0.75,
    "order_match_rate": 1.0,
}
COMPOSITION_SUMMARY_KEYS = frozenset(
    {
        "ok",
        "schema",
        "observations_sha256",
        "eligible",
        "failed_checks",
        "acceptance_checks",
        "thresholds",
        "routing_metrics",
        "behavioral_metrics",
    }
)
ROUTING_METRIC_KEYS = frozenset(
    {
        "case_count",
        "observed_case_count",
        "missing_case_ids",
        "expected_skill_count",
        "selected_skill_count",
        "matched_skill_count",
        "expected_skill_recall",
        "selected_skill_precision",
        "cases",
    }
)
BEHAVIORAL_METRIC_KEYS = frozenset(
    {
        "fixture_count",
        "active_conflict_violation_count",
        "active_conflict_violations",
        "selected_non_root_skill_count",
        "incoming_provenance_relationship_count",
        "missing_incoming_relationships",
        "expected_relationship_count",
        "matched_expected_relationship_count",
        "missing_expected_relationships",
        "expected_relationship_coverage",
        "provenance_relationship_coverage",
        "context_ratio",
        "maximum_fixture_context_ratio",
        "qualified_context_execution_count",
        "unqualified_context_execution_fixtures",
        "quality_metrics",
        "order_match_rate",
        "fixtures",
    }
)
VERSION_SOURCES = (
    Path(".codex-plugin") / "plugin.json",
    Path(".claude-plugin") / "plugin.json",
    Path(".claude-plugin") / "marketplace.json",
    Path("mcp-registry") / "draft-server.json",
)


def read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return payload


def string_field(payload: dict[str, object], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{path} must define string field {key!r}")
    return value


def release_version(raw_version: str) -> str:
    release, separator, build = raw_version.partition("+")
    if separator and not build:
        raise RuntimeError(f"version has empty build metadata: {raw_version}")
    if VERSION_RE.fullmatch(release) is None:
        raise RuntimeError(f"version is not a semver release: {raw_version}")
    return release


def version_tuple(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise RuntimeError(f"version is not a semver release: {version}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def composition_benchmark_required(version: str) -> bool:
    return version_tuple(version) >= COMPOSITION_BENCHMARK_MINIMUM_VERSION


def active_release_version(plugin_root: Path) -> tuple[str | None, list[str]]:
    versions: dict[str, str] = {}
    errors: list[str] = []
    for relative in VERSION_SOURCES:
        path = plugin_root / relative
        try:
            payload = read_json_object(path)
            versions[str(relative)] = release_version(
                string_field(payload, "version", path)
            )
        except RuntimeError as exc:
            errors.append(str(exc))
    unique_versions = sorted(set(versions.values()))
    if len(unique_versions) != 1:
        errors.append(f"release version mismatch across manifests: {versions}")
        return None, errors
    if unique_versions[0] != VERSION.release:
        errors.append(
            "release version does not match the canonical version descriptor: "
            f"{unique_versions[0]} != {VERSION.release}"
        )
    return unique_versions[0], errors


def workflow_has_release_tags(plugin_root: Path) -> list[str]:
    workflow = plugin_root / WORKFLOW_PATH
    try:
        text = workflow.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing workflow file: {WORKFLOW_CONTRACT_PATH}"]
    errors: list[str] = []
    for pattern in REQUIRED_RELEASE_TAG_PATTERNS:
        if pattern not in text:
            errors.append(
                f"{WORKFLOW_CONTRACT_PATH} does not include tag trigger pattern {pattern!r}"
            )
    return errors


def workflow_has_release_evidence_gate(plugin_root: Path) -> list[str]:
    workflow = plugin_root / WORKFLOW_PATH
    try:
        text = workflow.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing workflow file: {WORKFLOW_CONTRACT_PATH}"]
    lines = text.splitlines()
    errors: list[str] = []
    if not any(line.strip() == "pull_request:" for line in lines):
        errors.append(
            f"{WORKFLOW_CONTRACT_PATH} must verify release evidence on pull requests"
        )
    step_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == f"- name: {REQUIRED_RELEASE_EVIDENCE_STEP_NAME}"
        ),
        None,
    )
    if step_index is None:
        return errors + [
            f"{WORKFLOW_CONTRACT_PATH} must define an {REQUIRED_RELEASE_EVIDENCE_STEP_NAME!r} step"
        ]
    next_step = next(
        (
            index
            for index in range(step_index + 1, len(lines))
            if lines[index].startswith("      - ")
        ),
        len(lines),
    )
    step_lines = lines[step_index:next_step]
    if f"run: {REQUIRED_RELEASE_EVIDENCE_COMMAND}" not in {
        line.strip() for line in step_lines
    }:
        errors.append(
            f"{WORKFLOW_CONTRACT_PATH} must run {REQUIRED_RELEASE_EVIDENCE_COMMAND!r}"
        )
    if any(line.strip().startswith("if:") for line in step_lines):
        errors.append(
            f"{WORKFLOW_CONTRACT_PATH} must run active release evidence on pull requests"
        )
    return errors


def positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and value not in {float("inf"), float("-inf")}
    )


def validate_benchmark_summary(summary: dict[str, object]) -> list[str]:
    """Strictly validate the committed output of the bundled benchmark runner."""

    errors: list[str] = []
    if set(summary) != COMPOSITION_SUMMARY_KEYS:
        errors.append("composition benchmark summary fields must match bundled schema")
    if summary.get("ok") is not True:
        errors.append("composition benchmark summary ok must be true")
    if summary.get("schema") != COMPOSITION_BENCHMARK_SUMMARY_SCHEMA:
        errors.append("composition benchmark summary schema is invalid")
    observations_digest = summary.get("observations_sha256")
    if (
        not isinstance(observations_digest, str)
        or re.fullmatch(r"[a-f0-9]{64}", observations_digest) is None
    ):
        errors.append("composition benchmark summary observations_sha256 is invalid")
    checks = summary.get("acceptance_checks")
    if (
        summary.get("eligible") is not True
        or summary.get("failed_checks") != []
        or not isinstance(checks, dict)
        or set(checks) != COMPOSITION_ACCEPTANCE_CHECKS
        or any(value is not True for value in checks.values())
    ):
        errors.append("composition benchmark summary must be fully eligible")
    thresholds = summary.get("thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != set(
        COMPOSITION_THRESHOLDS
    ):
        errors.append("composition benchmark summary thresholds are incomplete")
    elif any(
        not finite_number(thresholds[key]) or float(thresholds[key]) != expected
        for key, expected in COMPOSITION_THRESHOLDS.items()
    ):
        errors.append(
            "composition benchmark summary thresholds must match release policy"
        )

    routing = summary.get("routing_metrics")
    if not isinstance(routing, dict) or set(routing) != ROUTING_METRIC_KEYS:
        errors.append("composition benchmark routing metrics must match bundled schema")
    else:
        cases = routing.get("cases")
        if (
            not positive_int(routing.get("case_count"))
            or int(routing["case_count"]) < 20
            or routing.get("observed_case_count") != routing.get("case_count")
            or routing.get("missing_case_ids") != []
            or not isinstance(cases, list)
            or len(cases) != routing["case_count"]
            or not positive_int(routing.get("expected_skill_count"))
            or not isinstance(routing.get("selected_skill_count"), int)
            or not isinstance(routing.get("matched_skill_count"), int)
            or routing.get("expected_skill_recall") != 1.0
            or not finite_number(routing.get("selected_skill_precision"))
            or float(routing["selected_skill_precision"]) < 0.90
        ):
            errors.append(
                "composition benchmark summary requires 20 complete routing cases"
            )

    behavioral = summary.get("behavioral_metrics")
    if not isinstance(behavioral, dict) or set(behavioral) != BEHAVIORAL_METRIC_KEYS:
        errors.append(
            "composition benchmark behavioral metrics must match bundled schema"
        )
    else:
        fixtures = behavioral.get("fixtures")
        quality = behavioral.get("quality_metrics")
        if (
            not positive_int(behavioral.get("fixture_count"))
            or int(behavioral["fixture_count"]) < 5
            or not isinstance(fixtures, list)
            or len(fixtures) != behavioral["fixture_count"]
            or behavioral.get("active_conflict_violation_count") != 0
            or behavioral.get("active_conflict_violations") != []
            or behavioral.get("missing_incoming_relationships") != []
            or behavioral.get("missing_expected_relationships") != []
            or behavioral.get("expected_relationship_coverage") != 1.0
            or behavioral.get("provenance_relationship_coverage") != 1.0
            or behavioral.get("order_match_rate") != 1.0
            or not finite_number(behavioral.get("context_ratio"))
            or float(behavioral["context_ratio"]) > 0.75
            or not finite_number(behavioral.get("maximum_fixture_context_ratio"))
            or float(behavioral["maximum_fixture_context_ratio"]) > 0.75
            or behavioral.get("qualified_context_execution_count")
            != behavioral.get("fixture_count")
            or behavioral.get("unqualified_context_execution_fixtures") != []
            or not isinstance(quality, dict)
            or set(quality) != {"synergy_lift", "compiler_lift", "order_lift"}
            or any(not finite_number(value) for value in quality.values())
            or float(quality.get("synergy_lift", -1)) < 0.10
            or float(quality.get("compiler_lift", -1)) < 0.05
            or float(quality.get("order_lift", -1)) < 0.05
        ):
            errors.append(
                "composition benchmark summary requires five fully passing fixtures"
            )
    return errors


def _git_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


def committed_file(plugin_root: Path, relative_path: Path) -> bool:
    path_text = relative_path.as_posix()
    environment = _git_environment()
    try:
        tracked = subprocess.run(
            [
                "git",
                "-C",
                str(plugin_root),
                "ls-files",
                "--error-unmatch",
                "--",
                path_text,
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        clean = subprocess.run(
            ["git", "-C", str(plugin_root), "diff", "--quiet", "HEAD", "--", path_text],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return tracked.returncode == 0 and clean.returncode == 0


def validate_composition_benchmark_evidence(
    plugin_root: Path,
    version: str,
    evidence: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    record = evidence.get("composition_benchmark")
    if not isinstance(record, dict):
        return ["docs/RELEASE_EVIDENCE.json composition_benchmark must be an object"]
    if record.get("schema") != COMPOSITION_BENCHMARK_EVIDENCE_SCHEMA:
        errors.append(
            "composition_benchmark.schema must be "
            f"{COMPOSITION_BENCHMARK_EVIDENCE_SCHEMA}"
        )
    if record.get("version") != version:
        errors.append(
            f"composition_benchmark.version must match active release {version}"
        )
    if record.get("status") != "reviewed":
        errors.append("composition_benchmark.status must be reviewed")
    if record.get("summary_path") != COMPOSITION_BENCHMARK_SUMMARY_PATH.as_posix():
        errors.append(
            "composition_benchmark.summary_path must be "
            f"{COMPOSITION_BENCHMARK_SUMMARY_PATH.as_posix()}"
        )
    digest_pattern = re.compile(r"[a-f0-9]{64}")
    observations_digest = record.get("observations_sha256")
    if (
        not isinstance(observations_digest, str)
        or digest_pattern.fullmatch(observations_digest) is None
    ):
        errors.append("composition_benchmark.observations_sha256 must be SHA-256")
    expected_summary_digest = record.get("summary_sha256")
    if (
        not isinstance(expected_summary_digest, str)
        or digest_pattern.fullmatch(expected_summary_digest) is None
    ):
        errors.append("composition_benchmark.summary_sha256 must be SHA-256")

    review = record.get("review")
    if not isinstance(review, dict):
        errors.append("composition_benchmark.review must be an object")
    else:
        if review.get("status") != "approved":
            errors.append("composition_benchmark.review.status must be approved")
        if (
            not isinstance(review.get("reviewer"), str)
            or not str(review.get("reviewer")).strip()
        ):
            errors.append("composition_benchmark.review.reviewer must be non-empty")
        reviewed_at = review.get("reviewed_at")
        if (
            not isinstance(reviewed_at, str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", reviewed_at)
            is None
        ):
            errors.append(
                "composition_benchmark.review.reviewed_at must be a UTC timestamp"
            )

    summary_path = plugin_root / COMPOSITION_BENCHMARK_SUMMARY_PATH
    if not committed_file(plugin_root, COMPOSITION_BENCHMARK_SUMMARY_PATH):
        errors.append(
            "composition benchmark summary must be committed and unchanged at "
            f"{COMPOSITION_BENCHMARK_SUMMARY_PATH.as_posix()}"
        )
    try:
        summary_bytes = summary_path.read_bytes()
        summary = json.loads(summary_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"could not read composition benchmark summary: {exc}")
        return errors
    if not isinstance(summary, dict):
        errors.append("composition benchmark summary must be a JSON object")
        return errors
    actual_summary_digest = hashlib.sha256(summary_bytes).hexdigest()
    if expected_summary_digest != actual_summary_digest:
        errors.append("composition_benchmark.summary_sha256 does not match summary")
    errors.extend(validate_benchmark_summary(summary))
    if observations_digest != summary.get("observations_sha256"):
        errors.append(
            "composition_benchmark.observations_sha256 does not match summary"
        )
    try:
        bundle = resolve_composition_benchmark_bundle(
            plugin_root,
            require_git_clean=True,
        )
    except CompositionBenchmarkBundleError as exc:
        errors.append(f"composition benchmark bundle is invalid: {exc}")
        return errors
    errors.extend(validate_bundle_evidence_record(record.get("bundle"), bundle))
    bundle_digest = bundle.get("manifest_digest")
    if (
        not isinstance(review, dict)
        or review.get("bundle_manifest_digest") != bundle_digest
    ):
        errors.append(
            "composition_benchmark.review.bundle_manifest_digest must match bundle"
        )
    artifact_paths = bundle.get("artifacts")
    if not isinstance(artifact_paths, dict):
        errors.append("composition benchmark bundle artifacts are invalid")
        return errors
    resolved_paths: dict[str, Path] = {}
    for label, filename in BUNDLE_ARTIFACTS:
        artifact = artifact_paths.get(filename)
        if not isinstance(artifact, dict) or not isinstance(
            artifact.get("path"), str
        ):
            errors.append(f"composition benchmark bundle {filename} is invalid")
            return errors
        resolved_paths[label] = plugin_root / str(artifact["path"])
    try:
        replay = {
            "ok": True,
            **run_benchmark(
                routing_golden_path=plugin_root / COMPOSITION_ROUTING_GOLDEN_PATH,
                behavioral_fixtures_path=plugin_root / COMPOSITION_BEHAVIORAL_FIXTURES_PATH,
                observations_path=resolved_paths["observations"],
                run_plan_path=resolved_paths["run_plan"],
                semantic_proposals_path=resolved_paths["semantic_proposals"],
                control_plan_path=resolved_paths["control_plan"],
                host_results_path=resolved_paths["host_results"],
                evaluator_artifacts_path=resolved_paths["evaluator_artifacts"],
            ),
        }
    except (OSError, SchemaAssertionError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"could not replay composition benchmark bundle: {exc}")
        return errors
    if summary != replay:
        errors.append(
            "composition benchmark summary does not exactly match bundle replay"
        )
    observations_entry = artifact_paths.get("benchmark-observations.json")
    bundle_observations_digest = (
        observations_entry.get("sha256")
        if isinstance(observations_entry, dict)
        else None
    )
    if observations_digest != bundle_observations_digest:
        errors.append(
            "composition_benchmark.observations_sha256 does not match bundle"
        )
    if replay.get("observations_sha256") != bundle_observations_digest:
        errors.append(
            "composition benchmark replay does not bind bundle observations"
        )
    return errors


def validate_hosted_evidence(
    plugin_root: Path, version: str, evidence: dict[str, object]
) -> list[str]:
    errors: list[str] = []
    schema = evidence.get("schema")
    if schema != "tmcp-release-evidence-v0.1":
        errors.append(
            "docs/RELEASE_EVIDENCE.json schema must be tmcp-release-evidence-v0.1"
        )
    if evidence.get("version") != version:
        errors.append(
            f"docs/RELEASE_EVIDENCE.json version must match active release {version}"
        )
    hosted = evidence.get("hosted_verification")
    if not isinstance(hosted, dict):
        return errors + [
            "docs/RELEASE_EVIDENCE.json hosted_verification must be an object"
        ]

    if hosted.get("workflow") != WORKFLOW_CONTRACT_PATH:
        errors.append(f"hosted_verification.workflow must be {WORKFLOW_CONTRACT_PATH}")
    if hosted.get("status") != "completed":
        errors.append("hosted_verification.status must be completed")
    if hosted.get("conclusion") != "success":
        errors.append("hosted_verification.conclusion must be success")

    run_id = hosted.get("run_id")
    if not positive_int(run_id):
        errors.append("hosted_verification.run_id must be a positive integer")
    url = hosted.get("url")
    if not isinstance(url, str) or not url:
        errors.append("hosted_verification.url must be a non-empty string")
    elif positive_int(run_id) and f"/actions/runs/{run_id}" not in url:
        errors.append("hosted_verification.url must contain the recorded run_id")

    source = hosted.get("source")
    ref = hosted.get("ref")
    if source == "tag":
        if ref not in {version, f"v{version}"}:
            errors.append(
                f"tag release evidence ref must be {version!r} or {f'v{version}'!r}"
            )
    elif source == "pull_request":
        if not isinstance(ref, str) or not ref:
            errors.append("pull request release evidence requires a non-empty ref")
        if not positive_int(hosted.get("pr_number")):
            errors.append("pull request release evidence requires a positive pr_number")
    elif source == "main":
        if ref != "main":
            errors.append("main release evidence ref must be 'main'")
        if hosted.get("pr_number") is not None:
            errors.append("main release evidence must not set pr_number")
    else:
        errors.append("hosted_verification.source must be tag, pull_request, or main")

    errors.extend(workflow_has_release_tags(plugin_root))
    errors.extend(workflow_has_release_evidence_gate(plugin_root))
    return errors


def check_release_evidence(plugin_root: Path) -> dict[str, object]:
    version, errors = active_release_version(plugin_root)
    if version is None:
        return {
            "schema": "tmcp-release-evidence-check-v0.1",
            "plugin_root": str(plugin_root),
            "active_version": None,
            "hosted_release_evidence": "fail",
            "errors": errors,
        }
    try:
        evidence = read_json_object(plugin_root / EVIDENCE_PATH)
    except RuntimeError as exc:
        errors.append(str(exc))
        evidence = {}
    if evidence:
        errors.extend(validate_hosted_evidence(plugin_root, version, evidence))
    benchmark_required = composition_benchmark_required(version)
    benchmark_supplied = "composition_benchmark" in evidence
    benchmark_errors: list[str] = []
    if benchmark_required or benchmark_supplied:
        benchmark_errors = validate_composition_benchmark_evidence(
            plugin_root,
            version,
            evidence,
        )
        if benchmark_required and not committed_file(plugin_root, EVIDENCE_PATH):
            benchmark_errors.append(
                "composition benchmark release evidence must be committed and "
                "unchanged at docs/RELEASE_EVIDENCE.json"
            )
        errors.extend(benchmark_errors)
    return {
        "schema": "tmcp-release-evidence-check-v0.1",
        "plugin_root": str(plugin_root),
        "active_version": version,
        "hosted_release_evidence": "pass" if not errors else "fail",
        "composition_benchmark_evidence": (
            "fail"
            if benchmark_errors
            else "pass"
            if benchmark_required or benchmark_supplied
            else "not_required"
        ),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that the active TMCP release has recorded hosted CI evidence."
    )
    parser.add_argument(
        "plugin_root", nargs="?", default=".", help="Path to the TMCP plugin root"
    )
    args = parser.parse_args()
    plugin_root = Path(args.plugin_root).expanduser().resolve()
    result = check_release_evidence(plugin_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["hosted_release_evidence"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
