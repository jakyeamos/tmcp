"""Composition-benchmark input and replay checks for release packages."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Protocol

from scripts.composition_benchmark_bundle import (
    BUNDLE_ARTIFACTS,
    BUNDLE_RELATIVE_PATH,
    CompositionBenchmarkBundleError,
    resolve_composition_benchmark_bundle,
)


COMPOSITION_BENCHMARK_MINIMUM_VERSION = (0, 6, 0)
COMPOSITION_BENCHMARK_SUMMARY_SCHEMA = "tmcp-composition-benchmark-summary-v0.1"

class JsonRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        cwd: Path,
    ) -> tuple[bool, str, dict[str, object] | None]: ...


class SummaryValidator(Protocol):
    def __call__(self, summary: dict[str, object]) -> list[str]: ...


class InputResolver(Protocol):
    def __call__(
        self,
        *,
        source_plugin_root: Path | None,
        observations_path: Path | None,
        run_plan_path: Path | None,
        semantic_proposals_path: Path | None,
        control_plan_path: Path | None,
        host_results_path: Path | None,
        evaluator_artifacts_path: Path | None,
        release_version: str,
    ) -> tuple[dict[str, Path] | None, str | None]: ...


def release_version_tuple(version: str) -> tuple[int, int, int]:
    release = version.partition("+")[0]
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", release)
    if match is None:
        raise ValueError(f"invalid release version: {version}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def composition_benchmark_required(version: str) -> bool:
    return release_version_tuple(version) >= COMPOSITION_BENCHMARK_MINIMUM_VERSION


def resolve_composition_benchmark_inputs(
    *,
    source_plugin_root: Path | None,
    observations_path: Path | None,
    run_plan_path: Path | None,
    semantic_proposals_path: Path | None,
    control_plan_path: Path | None,
    host_results_path: Path | None,
    evaluator_artifacts_path: Path | None,
    release_version: str,
) -> tuple[dict[str, Path] | None, str | None]:
    """Resolve explicit artifacts, or the required clean source bundle."""

    supplied = {
        "observations": observations_path,
        "run_plan": run_plan_path,
        "semantic_proposals": semantic_proposals_path,
        "control_plan": control_plan_path,
        "host_results": host_results_path,
        "evaluator_artifacts": evaluator_artifacts_path,
    }
    supplied_count = sum(path is not None for path in supplied.values())
    if supplied_count:
        missing = [
            label.replace("_", " ")
            for label, path in supplied.items()
            if path is None
        ]
        if missing:
            return (
                None,
                "composition benchmark artifact inputs must be supplied together; "
                f"missing {', '.join(missing)}.",
            )
        return (
            {label: path for label, path in supplied.items() if path is not None},
            None,
        )

    if not composition_benchmark_required(release_version):
        return None, None
    if source_plugin_root is None:
        return (
            None,
            "TMCP 0.6.0 and newer require a source worktree to resolve the "
            "canonical composition benchmark bundle.",
        )
    try:
        source_root = source_plugin_root.expanduser().resolve(strict=True)
        resolve_composition_benchmark_bundle(
            source_root,
            require_git_clean=True,
        )
        paths = {
            label: source_root / BUNDLE_RELATIVE_PATH / filename
            for label, filename in BUNDLE_ARTIFACTS
        }
    except (CompositionBenchmarkBundleError, OSError) as exc:
        return (
            None,
            "could not resolve the Git-clean canonical composition benchmark "
            f"bundle: {exc}",
        )
    return paths, None


def check_composition_benchmark(
    plugin_root: Path,
    observations_path: Path | None,
    *,
    run_plan_path: Path | None = None,
    semantic_proposals_path: Path | None = None,
    control_plan_path: Path | None = None,
    host_results_path: Path | None = None,
    evaluator_artifacts_path: Path | None = None,
    source_plugin_root: Path | None = None,
    release_version: str,
    run_json: JsonRunner,
    resolve_inputs: InputResolver = (
        resolve_composition_benchmark_inputs
    ),
    validate_summary: SummaryValidator,
) -> tuple[bool, str]:
    artifact_paths, input_error = resolve_inputs(
        source_plugin_root=source_plugin_root or plugin_root,
        observations_path=observations_path,
        run_plan_path=run_plan_path,
        semantic_proposals_path=semantic_proposals_path,
        control_plan_path=control_plan_path,
        host_results_path=host_results_path,
        evaluator_artifacts_path=evaluator_artifacts_path,
        release_version=release_version,
    )
    if input_error:
        return False, input_error
    if artifact_paths is None:
        return True, f"not required for TMCP {release_version}"
    try:
        observations = artifact_paths["observations"].expanduser().resolve(strict=True)
        if not observations.is_file():
            return False, "composition benchmark observations must be one regular file"
        artifact_paths = {
            label: path.expanduser().resolve(strict=True)
            for label, path in artifact_paths.items()
        }
        if any(not path.is_file() for path in artifact_paths.values()):
            return False, "composition benchmark artifacts must be regular files"
        observations_digest = hashlib.sha256(observations.read_bytes()).hexdigest()
    except OSError as exc:
        return False, f"could not resolve composition benchmark observations: {exc}"
    ok, output, payload = run_json(
        [
            sys.executable,
            "scripts/run_composition_benchmark.py",
            str(observations),
            "--run-plan",
            str(artifact_paths["run_plan"]),
            "--semantic-proposals",
            str(artifact_paths["semantic_proposals"]),
            "--control-plan",
            str(artifact_paths["control_plan"]),
            "--host-results",
            str(artifact_paths["host_results"]),
            "--evaluator-artifacts",
            str(artifact_paths["evaluator_artifacts"]),
        ],
        plugin_root,
    )
    if not ok or payload is None:
        return False, output
    if validate_summary(payload):
        return False, "composition benchmark runner did not return an eligible summary"
    if payload.get("observations_sha256") != observations_digest:
        return False, "composition benchmark summary does not bind observations digest"
    return (
        True,
        json.dumps(
            {
                "schema": COMPOSITION_BENCHMARK_SUMMARY_SCHEMA,
                "eligible": True,
                "observations_sha256": observations_digest,
                "summary": payload,
            },
            sort_keys=True,
        ),
    )
