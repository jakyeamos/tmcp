"""Composition-benchmark input and replay checks for release packages."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Protocol

from scripts.composition_benchmark_bundle import (
    BUNDLE_ARTIFACTS,
    BUNDLE_RELATIVE_PATH,
    CompositionBenchmarkBundleError,
    freeze_composition_benchmark_artifacts,
    resolve_composition_benchmark_bundle,
)


COMPOSITION_BENCHMARK_MINIMUM_VERSION = (0, 6, 0)
COMPOSITION_BENCHMARK_SUMMARY_SCHEMA = "tmcp-composition-benchmark-summary-v0.1"


class BenchmarkArtifactPaths(dict[str, Path]):
    """Resolved paths plus optional canonical hashes for a one-time freeze."""

    def __init__(
        self,
        paths: dict[str, Path],
        *,
        expected_sha256: dict[str, str] | None = None,
    ) -> None:
        super().__init__(paths)
        self.expected_sha256 = expected_sha256


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


def materialize_frozen_composition_benchmark_artifacts(
    artifacts: dict[str, bytes], directory: Path
) -> dict[str, Path]:
    """Write previously verified bytes into one private runner-input directory."""

    directory.mkdir(parents=True, exist_ok=False)
    paths: dict[str, Path] = {}
    for label, filename in BUNDLE_ARTIFACTS:
        content = artifacts.get(label)
        if not isinstance(content, bytes):
            raise CompositionBenchmarkBundleError(
                f"frozen composition benchmark artifact is missing: {label}"
            )
        path = directory / filename
        path.write_bytes(content)
        paths[label] = path
    if set(artifacts) != set(paths):
        raise CompositionBenchmarkBundleError(
            "frozen composition benchmark artifacts contain unexpected labels."
        )
    return paths


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
            BenchmarkArtifactPaths(
                {label: path for label, path in supplied.items() if path is not None}
            ),
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
        bundle = resolve_composition_benchmark_bundle(
            source_root,
            require_git_clean=True,
        )
        artifacts = bundle.get("artifacts")
        if not isinstance(artifacts, dict):
            raise CompositionBenchmarkBundleError("benchmark bundle artifacts are invalid.")
        expected_sha256 = {
            label: str(artifacts[filename]["sha256"])
            for label, filename in BUNDLE_ARTIFACTS
            if isinstance(artifacts.get(filename), dict)
        }
        if len(expected_sha256) != len(BUNDLE_ARTIFACTS):
            raise CompositionBenchmarkBundleError("benchmark bundle artifact hashes are invalid.")
        paths = BenchmarkArtifactPaths(
            {
                label: source_root / BUNDLE_RELATIVE_PATH / filename
                for label, filename in BUNDLE_ARTIFACTS
            },
            expected_sha256=expected_sha256,
        )
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
        frozen_artifacts = freeze_composition_benchmark_artifacts(
            artifact_paths,
            expected_sha256=getattr(artifact_paths, "expected_sha256", None),
        )
    except (CompositionBenchmarkBundleError, OSError) as exc:
        return False, f"could not freeze composition benchmark artifacts: {exc}"
    observations_digest = hashlib.sha256(frozen_artifacts["observations"]).hexdigest()
    with tempfile.TemporaryDirectory(prefix="tmcp-benchmark-inputs-") as temporary:
        try:
            runner_paths = materialize_frozen_composition_benchmark_artifacts(
                frozen_artifacts,
                Path(temporary) / "inputs",
            )
        except (CompositionBenchmarkBundleError, OSError) as exc:
            return False, f"could not materialize composition benchmark artifacts: {exc}"
        ok, output, payload = run_json(
            [
                sys.executable,
                "scripts/run_composition_benchmark.py",
                str(runner_paths["observations"]),
                "--run-plan",
                str(runner_paths["run_plan"]),
                "--semantic-proposals",
                str(runner_paths["semantic_proposals"]),
                "--control-plan",
                str(runner_paths["control_plan"]),
                "--host-results",
                str(runner_paths["host_results"]),
                "--evaluator-artifacts",
                str(runner_paths["evaluator_artifacts"]),
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
