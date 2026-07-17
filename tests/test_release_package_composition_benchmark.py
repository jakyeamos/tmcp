from __future__ import annotations

import hashlib
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import composition_benchmark_bundle as benchmark_bundle_support
from tests import test_tmcp_composition_benchmarks as benchmark_test_support
from tests.test_release_package import (
    PLUGIN_ROOT,
    commit_fixture,
    load_release_archive_module,
    load_release_package_check_module,
    write_test_archive,
)
from tmcp_runtime.domain.composition_benchmarks import score_composition_benchmark


def write_composition_benchmark_bundle(root: Path) -> dict[str, Path]:
    bundle_root = root / benchmark_bundle_support.BUNDLE_RELATIVE_PATH
    paths: dict[str, Path] = {}
    for index, (label, filename) in enumerate(
        benchmark_bundle_support.BUNDLE_ARTIFACTS,
        start=1,
    ):
        path = bundle_root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"artifact": filename, "index": index}) + "\n",
            encoding="utf-8",
        )
        paths[label] = path
    return paths


class ReleasePackageCompositionBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = load_release_archive_module()
        cls.checker = load_release_package_check_module()

    def test_composition_benchmark_is_mandatory_for_zero_six(self) -> None:
        self.assertFalse(self.checker.composition_benchmark_required("0.5.7"))
        self.assertTrue(self.checker.composition_benchmark_required("0.6.0"))
        self.assertTrue(self.checker.composition_benchmark_required("1.0.0"))

        current_ok, current_output = self.checker.check_composition_benchmark(
            PLUGIN_ROOT,
            None,
            release_version="0.5.7",
        )
        with tempfile.TemporaryDirectory() as tmp:
            future_root = Path(tmp) / "source"
            future_root.mkdir()
            future_ok, future_output = self.checker.check_composition_benchmark(
                future_root,
                None,
                release_version="0.6.0",
            )

        self.assertTrue(current_ok, current_output)
        self.assertFalse(future_ok)
        self.assertIn("canonical composition benchmark bundle", future_output)

    def test_composition_benchmark_defaults_to_source_bundle_for_zero_six(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary_root = Path(tmp)
            source_root = temporary_root / "source"
            package_root = temporary_root / "extracted-package"
            source_root.mkdir()
            package_root.mkdir()
            bundle_paths = write_composition_benchmark_bundle(source_root)
            commit_fixture(source_root)
            observations_digest = hashlib.sha256(
                bundle_paths["observations"].read_bytes()
            ).hexdigest()
            summary = {"observations_sha256": observations_digest}

            with (
                patch.object(
                    self.checker,
                    "run_json",
                    return_value=(True, json.dumps(summary), summary),
                ) as benchmark_runner,
                patch.object(
                    self.checker,
                    "validate_benchmark_summary",
                    return_value=[],
                ),
            ):
                ok, output = self.checker.check_composition_benchmark(
                    package_root,
                    None,
                    source_plugin_root=source_root,
                    release_version="0.6.0",
                )

            self.assertTrue(ok, output)
        command, runner_root = benchmark_runner.call_args.args
        self.assertEqual(runner_root, package_root)
        self.assertNotEqual(command[2], str(bundle_paths["observations"].resolve()))
        self.assertEqual(Path(command[2]).name, "benchmark-observations.json")
        self.assertEqual(Path(command[4]).name, "benchmark-run-plan.json")
        self.assertEqual(Path(command[6]).name, "semantic-proposals.json")
        self.assertEqual(Path(command[8]).name, "benchmark-control-plan.json")
        self.assertEqual(Path(command[10]).name, "host-results.json")
        self.assertEqual(Path(command[12]).name, "evaluator-artifacts.json")

    def test_composition_benchmark_runner_uses_frozen_bundle_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary_root = Path(tmp)
            source_root = temporary_root / "source"
            package_root = temporary_root / "extracted-package"
            source_root.mkdir()
            package_root.mkdir()
            bundle_paths = write_composition_benchmark_bundle(source_root)
            commit_fixture(source_root)
            observations_digest = hashlib.sha256(
                bundle_paths["observations"].read_bytes()
            ).hexdigest()
            summary = {"observations_sha256": observations_digest}

            def runner(
                command: list[str], _root: Path
            ) -> tuple[bool, str, dict[str, object]]:
                bundle_paths["host_results"].write_text(
                    '{"token":"sk-' + "a" * 24 + '"}\n', encoding="utf-8"
                )
                host_index = command.index("--host-results") + 1
                frozen_host = Path(command[host_index]).read_text(encoding="utf-8")
                self.assertNotIn("sk-", frozen_host)
                self.assertNotEqual(
                    Path(command[host_index]), bundle_paths["host_results"]
                )
                return True, json.dumps(summary), summary

            with (
                patch.object(self.checker, "run_json", side_effect=runner),
                patch.object(
                    self.checker,
                    "validate_benchmark_summary",
                    return_value=[],
                ),
            ):
                ok, output = self.checker.check_composition_benchmark(
                    package_root,
                    None,
                    source_plugin_root=source_root,
                    release_version="0.6.0",
                )

        self.assertTrue(ok, output)

    def test_package_resolves_bundle_before_extracting_the_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary_root = Path(tmp)
            archive_path = temporary_root / "tmcp.tar.gz"
            write_test_archive(self.package, archive_path, [], [])
            resolved_paths = {
                "observations": temporary_root / "benchmark-observations.json",
                "run_plan": temporary_root / "benchmark-run-plan.json",
                "semantic_proposals": temporary_root / "semantic-proposals.json",
                "control_plan": temporary_root / "benchmark-control-plan.json",
                "host_results": temporary_root / "host-results.json",
                "evaluator_artifacts": temporary_root
                / "evaluator-artifacts.json",
            }
            for path in resolved_paths.values():
                path.write_text("{}\n", encoding="utf-8")
            events: list[str] = []

            def resolve_inputs(**_kwargs: object) -> tuple[dict[str, Path], None]:
                events.append("resolve")
                return resolved_paths, None

            def extract_archive(_archive: tarfile.TarFile, target: Path) -> None:
                events.append("extract")
                (target / "tmcp").mkdir()

            with (
                patch.object(
                    self.checker,
                    "check_archive_manifest",
                    return_value=(True, "manifest"),
                ),
                patch.object(
                    self.checker,
                    "resolve_composition_benchmark_inputs",
                    side_effect=resolve_inputs,
                ),
                patch.object(
                    self.checker,
                    "safe_extractall",
                    side_effect=extract_archive,
                ),
                patch.object(self.checker, "run", return_value=(True, "")),
                patch.object(
                    self.checker,
                    "check_frontmatter_and_workflow_status",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_no_hardcoded_user_paths",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_no_private_names",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_markdown_links",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_doctor_surface",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_sample_harvest",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_sample_expert_rubric",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_adaptive_workflow_surface",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_composition_surface",
                    return_value=(True, ""),
                ),
                patch.object(
                    self.checker,
                    "check_composition_benchmark",
                    return_value=(True, "benchmark"),
                ) as benchmark_check,
            ):
                result = self.checker.check_package(
                    archive_path,
                    source_plugin_root=temporary_root / "source",
                    release_version="0.6.0",
                )

        self.assertEqual(events, ["resolve", "extract"])
        self.assertEqual(result["composition_benchmark"], "pass")
        arguments = benchmark_check.call_args
        self.assertEqual(Path(arguments.args[1]).name, "benchmark-observations.json")
        self.assertEqual(Path(arguments.kwargs["run_plan_path"]).name, "benchmark-run-plan.json")
        self.assertEqual(
            Path(arguments.kwargs["semantic_proposals_path"]).name,
            "semantic-proposals.json",
        )
        self.assertEqual(
            Path(arguments.kwargs["control_plan_path"]).name,
            "benchmark-control-plan.json",
        )
        self.assertEqual(
            Path(arguments.kwargs["host_results_path"]).name,
            "host-results.json",
        )
        self.assertEqual(
            Path(arguments.kwargs["evaluator_artifacts_path"]).name,
            "evaluator-artifacts.json",
        )

    def test_composition_benchmark_rejects_partial_ad_hoc_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            observations = Path(tmp) / "observations.json"
            observations.write_text("{}\n", encoding="utf-8")

            ok, output = self.checker.check_composition_benchmark(
                PLUGIN_ROOT,
                observations,
                release_version="0.5.7",
            )

        self.assertFalse(ok)
        self.assertIn("must be supplied together", output)
        self.assertIn("run plan", output)

    def test_composition_benchmark_rejects_dirty_default_source_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "source"
            source_root.mkdir()
            bundle_paths = write_composition_benchmark_bundle(source_root)
            commit_fixture(source_root)
            bundle_paths["host_results"].write_text(
                '{"changed":true}\n', encoding="utf-8"
            )

            ok, output = self.checker.check_composition_benchmark(
                source_root,
                None,
                release_version="0.6.0",
            )

        self.assertFalse(ok)
        self.assertIn("unchanged from HEAD", output)

    def test_composition_benchmark_validates_supplied_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            observations = Path(tmp) / "observations.json"
            observations.write_text('{"schema":"observed"}\n', encoding="utf-8")
            benchmark_artifacts = {
                "run_plan_path": Path(tmp) / "run-plan.json",
                "semantic_proposals_path": Path(tmp) / "semantic-proposals.json",
                "control_plan_path": Path(tmp) / "control-plan.json",
                "host_results_path": Path(tmp) / "host-results.json",
                "evaluator_artifacts_path": Path(tmp) / "evaluator-artifacts.json",
            }
            for path in benchmark_artifacts.values():
                path.write_text("{}\n", encoding="utf-8")
            expected_digest = hashlib.sha256(observations.read_bytes()).hexdigest()
            builder = benchmark_test_support.CompositionBenchmarkTests()
            builder.setUpClass()
            summary = {
                "ok": True,
                **score_composition_benchmark(
                    golden_cases=builder.golden_cases,
                    fixture_definitions=builder.fixture_definitions,
                    routing_results=builder._routing_results(),
                    behavioral_results=builder._behavioral_results(),
                ),
                "observations_sha256": expected_digest,
            }
            with patch.object(
                self.checker,
                "run_json",
                return_value=(True, json.dumps(summary), summary),
            ) as benchmark_runner:
                ok, output = self.checker.check_composition_benchmark(
                    PLUGIN_ROOT,
                    observations,
                    **benchmark_artifacts,
                    release_version="0.6.0",
                )

        self.assertTrue(ok, output)
        self.assertEqual(json.loads(output)["observations_sha256"], expected_digest)
        benchmark_runner.assert_called_once()

    def test_package_excludes_composition_benchmark_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            benchmark_bundle = write_composition_benchmark_bundle(root)
            output_path = Path(tmp) / "tmcp.tar.gz"

            commit_fixture(root)
            self.package.create_package(root, output_path)

            with tarfile.open(output_path, "r:gz") as archive:
                names = archive.getnames()

        self.assertIn("tmcp/README.md", names)
        for artifact in benchmark_bundle.values():
            relative = artifact.relative_to(root).as_posix()
            self.assertEqual(
                self.package.inclusion_reason(
                    self.package._validate_relative_path(relative)
                ),
                "release evidence is external to the immutable package",
            )
            self.assertNotIn(f"tmcp/{relative}", names)


if __name__ == "__main__":
    unittest.main()
