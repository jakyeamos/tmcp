from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import composition_benchmark_bundle as bundle
from tests.test_tmcp_composition_benchmark_assembly import (
    CompositionBenchmarkAssemblyTests,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_bundle(root: Path) -> Path:
    directory = root / bundle.BUNDLE_RELATIVE_PATH
    for index, (_, filename) in enumerate(bundle.BUNDLE_ARTIFACTS, start=1):
        _write_json(directory / filename, {"artifact": filename, "index": index})
    return directory


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _clear_secret_scan() -> dict[str, dict[str, object]]:
    return {
        filename: {"status": "clear", "redactions": {}}
        for _label, filename in bundle.BUNDLE_ARTIFACTS
    }


def _structured_sensitive_artifacts() -> tuple[dict[str, object], dict[str, object]]:
    receipt = {
        "schema": "tmcp-run-receipt-v0.1",
        "graph_digest": _digest("receipt-graph"),
        "content_digests": [_digest("receipt-content")],
        "context_accounting_digest": _digest("receipt-accounting"),
        "preflight_capsule_digest": _digest("receipt-preflight"),
        "phase_capsule_trace": [
            {
                "capsule_digest": _digest("receipt-phase"),
                "incoming_handoff_digests": [_digest("receipt-handoff")],
            }
        ],
        "benchmark_control_input_digest": _digest("receipt-control-input"),
        "benchmark_execution_recipe_digest": _digest("receipt-execution-recipe"),
        "execution_context": {
            "context_accounting_digest": _digest("context-accounting"),
            "preflight_capsule_digest": _digest("context-preflight"),
            "preflight_context_instance_id": "host-context-preflight",
            "phase_capsule_trace": [
                {
                    "capsule_digest": _digest("context-phase"),
                    "incoming_handoff_digests": [_digest("context-handoff")],
                    "context_instance_id": "host-context-stage",
                }
            ],
        },
    }
    host_results = {
        "schema": "tmcp-composition-benchmark-host-results-v0.1",
        "run_manifest_id": "benchmark-run-0123456789abcdef0123",
        "run_manifest_digest": _digest("host-manifest"),
        "control_plan_id": "benchmark-control-0123456789abcdef0123",
        "control_plan_digest": _digest("host-control"),
        "routing_runs": [
            {
                "case_id": "routing-case",
                "request_id": "routing-request",
                "input_digest": _digest("routing-input"),
                "selected_skill_ids": ["skill-routing"],
                "run_id": "routing-run",
                "outcome": "passed",
                "artifact": "verified routing artifact",
                "evidence": [
                    {"media_type": "text/plain", "content": "routing verified"}
                ],
            }
        ],
        "behavioral_runs": [
            {
                "fixture_id": "behavioral-fixture",
                "request_id": "behavioral-request",
                "variants": [
                    {
                        "variant_id": "full_composition",
                        "input_packet_digest": _digest("behavioral-input"),
                        "execution_recipe_digest": _digest("behavioral-recipe"),
                        "run_id": "behavioral-run",
                        "outcome": "passed",
                        "artifact": "verified behavioral artifact",
                        "tmcp_run_receipt": receipt,
                    }
                ],
            }
        ],
    }
    evaluator_artifacts = {
        "schema": "tmcp-composition-benchmark-evaluator-artifacts-v0.1",
        "run_manifest_id": "benchmark-run-0123456789abcdef0123",
        "run_manifest_digest": _digest("evaluator-manifest"),
        "control_plan_id": "benchmark-control-0123456789abcdef0123",
        "control_plan_digest": _digest("evaluator-control"),
        "fixture_evaluations": [
            {
                "fixture_id": "behavioral-fixture",
                "evaluator_id": "reviewer",
                "evaluator_version": "v1",
                "evaluation_run_id": "evaluation-run",
                "evaluated_at": "2026-07-17T00:00:00Z",
                "method": "structured-review",
                "rubric_id": "quality",
                "rubric_version": "v1",
                "rubric_digest": _digest("evaluator-rubric"),
                "variants": [
                    {
                        "variant_id": "full_composition",
                        "input_packet_digest": _digest("evaluator-input"),
                        "execution_recipe_digest": _digest("evaluator-recipe"),
                        "execution_artifact_digest": _digest("evaluator-artifact"),
                        "dimension_scores": {"quality": 1.0},
                        "evidence": [
                            {
                                "evidence_id": "evidence-1",
                                "media_type": "text/plain",
                                "content": "quality confirmed",
                            }
                        ],
                        "dimension_evidence": {
                            "quality": [
                                {
                                    "requirement": "quality",
                                    "evidence_ids": ["evidence-1"],
                                    "claim": "quality confirmed",
                                }
                            ]
                        },
                    }
                ],
            }
        ],
    }
    return host_results, evaluator_artifacts


def _git(root: Path, *arguments: str) -> None:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


class CompositionBenchmarkBundleTests(unittest.TestCase):
    def test_resolves_exact_bundle_and_projects_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)

            resolved = bundle.resolve_composition_benchmark_bundle(root)
            record = bundle.bundle_evidence_record(resolved)

            self.assertEqual(resolved["schema"], bundle.BUNDLE_SCHEMA)
            self.assertEqual(resolved["path"], "docs/COMPOSITION_BENCHMARK_BUNDLE")
            self.assertEqual(resolved["evidence_trust"], "advisory_untrusted")
            self.assertEqual(
                resolved["secret_scan"],
                _clear_secret_scan(),
            )
            self.assertEqual(
                record["artifacts"]["host-results.json"]["sha256"],
                hashlib.sha256(
                    (directory / "host-results.json").read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(
                bundle.validate_bundle_evidence_record(record, resolved), []
            )

    def test_rejects_missing_unexpected_and_nonregular_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            (directory / "unexpected.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "unexpected=.*unexpected.json"
            ):
                bundle.resolve_composition_benchmark_bundle(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            (directory / "benchmark-observations.json").unlink()
            (directory / "benchmark-observations.json").mkdir()
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "regular file"
            ):
                bundle.resolve_composition_benchmark_bundle(root)

    def test_rejects_symlink_and_out_of_root_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            directory = _write_bundle(root)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            (directory / "host-results.json").unlink()
            (directory / "host-results.json").symlink_to(target)
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "must not be a symlink"
            ):
                bundle.resolve_composition_benchmark_bundle(root)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            root.mkdir()
            outside = base / "outside"
            _write_bundle(outside)
            (root / "docs").symlink_to(outside / "docs", target_is_directory=True)
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "outside the repository root"
            ):
                bundle.resolve_composition_benchmark_bundle(root)

    def test_rejects_oversized_and_sensitive_host_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            (directory / "host-results.json").write_bytes(b"12345")
            with mock.patch.object(bundle, "MAX_BENCHMARK_ARTIFACT_BYTES", 4):
                with self.assertRaisesRegex(
                    bundle.CompositionBenchmarkBundleError, "exceeds 4 bytes"
                ):
                    bundle.resolve_composition_benchmark_bundle(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            _write_json(
                directory / "evaluator-artifacts.json",
                {"token": "sk-" + "a" * 24},
            )
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "sensitive or high-entropy"
            ):
                bundle.resolve_composition_benchmark_bundle(root)

    def test_allows_structural_sha256_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            host_results, evaluator_artifacts = _structured_sensitive_artifacts()
            _write_json(directory / "host-results.json", host_results)
            _write_json(directory / "evaluator-artifacts.json", evaluator_artifacts)

            resolved = bundle.resolve_composition_benchmark_bundle(root)

            self.assertEqual(
                resolved["secret_scan"],
                _clear_secret_scan(),
            )

    def test_rejects_secrets_and_high_entropy_outside_structural_digest_paths(
        self,
    ) -> None:
        secret = "sk-" + "a" * 24
        with self.subTest("evidence_content"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = _write_bundle(root)
                host_results, evaluator_artifacts = _structured_sensitive_artifacts()
                evaluator_artifacts["fixture_evaluations"][0]["variants"][0][
                    "evidence"
                ][0]["content"] = secret
                _write_json(directory / "host-results.json", host_results)
                _write_json(directory / "evaluator-artifacts.json", evaluator_artifacts)
                with self.assertRaisesRegex(
                    bundle.CompositionBenchmarkBundleError,
                    "sensitive or high-entropy",
                ):
                    bundle.resolve_composition_benchmark_bundle(root)

        with self.subTest("run_id"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = _write_bundle(root)
                host_results, evaluator_artifacts = _structured_sensitive_artifacts()
                host_results["routing_runs"][0]["run_id"] = _digest("opaque-run")
                _write_json(directory / "host-results.json", host_results)
                _write_json(directory / "evaluator-artifacts.json", evaluator_artifacts)
                with self.assertRaisesRegex(
                    bundle.CompositionBenchmarkBundleError,
                    "sensitive or high-entropy",
                ):
                    bundle.resolve_composition_benchmark_bundle(root)

    def test_scans_every_canonical_artifact_and_freezes_explicit_inputs(self) -> None:
        secret = "sk-" + "a" * 24
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            for _label, filename in bundle.BUNDLE_ARTIFACTS:
                _write_json(directory / filename, {"evidence": secret})
                with self.assertRaisesRegex(
                    bundle.CompositionBenchmarkBundleError,
                    "sensitive or high-entropy",
                ):
                    bundle.resolve_composition_benchmark_bundle(root)
                _write_json(directory / filename, {"artifact": filename})

            paths = {
                label: directory / filename
                for label, filename in bundle.BUNDLE_ARTIFACTS
            }
            frozen = bundle.freeze_composition_benchmark_artifacts(paths)
            self.assertEqual(set(frozen), set(paths))
            expected_sha256 = {
                label: hashlib.sha256(content).hexdigest()
                for label, content in frozen.items()
            }
            paths["host_results"].write_text('{"changed":true}', encoding="utf-8")
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError,
                "changed after canonical bundle resolution",
            ):
                bundle.freeze_composition_benchmark_artifacts(
                    paths,
                    expected_sha256=expected_sha256,
                )

    def test_freeze_rejects_an_explicit_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            paths = {
                label: directory / filename
                for label, filename in bundle.BUNDLE_ARTIFACTS
            }
            target = directory / "host-results-target.json"
            target.write_text("{}", encoding="utf-8")
            paths["host_results"].unlink()
            paths["host_results"].symlink_to(target)

            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "must not be a symlink"
            ):
                bundle.freeze_composition_benchmark_artifacts(paths)

    def test_scanner_accepts_a_compiler_bound_six_artifact_run(self) -> None:
        fixture = CompositionBenchmarkAssemblyTests()
        fixture.setUpClass()
        observations, host_results, evaluator_artifacts = fixture._assemble()
        payloads = {
            "benchmark-run-plan.json": fixture.run_plan,
            "semantic-proposals.json": fixture.proposals,
            "benchmark-control-plan.json": fixture.controls,
            "host-results.json": host_results,
            "evaluator-artifacts.json": evaluator_artifacts,
            "benchmark-observations.json": observations,
        }

        for filename, payload in payloads.items():
            self.assertEqual(
                bundle._scan_sensitive_serialization(
                    filename, json.dumps(payload, sort_keys=True).encode("utf-8")
                ),
                {"status": "clear", "redactions": {}},
            )

        with self.subTest("host_context_id"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = _write_bundle(root)
                host_results, evaluator_artifacts = _structured_sensitive_artifacts()
                host_results["behavioral_runs"][0]["variants"][0][
                    "tmcp_run_receipt"
                ]["execution_context"]["phase_capsule_trace"][0][
                    "context_instance_id"
                ] = _digest("opaque-context")
                _write_json(directory / "host-results.json", host_results)
                _write_json(directory / "evaluator-artifacts.json", evaluator_artifacts)
                with self.assertRaisesRegex(
                    bundle.CompositionBenchmarkBundleError,
                    "sensitive or high-entropy",
                ):
                    bundle.resolve_composition_benchmark_bundle(root)

        with self.subTest("arbitrary_key"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = _write_bundle(root)
                host_results, evaluator_artifacts = _structured_sensitive_artifacts()
                host_results["routing_runs"][0][_digest("arbitrary-key")] = "present"
                _write_json(directory / "host-results.json", host_results)
                _write_json(directory / "evaluator-artifacts.json", evaluator_artifacts)
                with self.assertRaisesRegex(
                    bundle.CompositionBenchmarkBundleError,
                    "sensitive or high-entropy",
                ):
                    bundle.resolve_composition_benchmark_bundle(root)

    def test_rejects_malformed_sensitive_artifact_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            (directory / "host-results.json").write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "valid JSON"
            ):
                bundle.resolve_composition_benchmark_bundle(root)

    def test_requires_tracked_head_clean_files_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _write_bundle(root)
            _git(root, "init", "--quiet")
            _git(root, "add", "--", "docs/COMPOSITION_BENCHMARK_BUNDLE")
            _git(
                root,
                "-c",
                "user.name=TMCP Test",
                "-c",
                "user.email=tmcp@example.test",
                "commit",
                "--quiet",
                "-m",
                "benchmark bundle fixture",
            )
            self.assertEqual(
                bundle.resolve_composition_benchmark_bundle(
                    root, require_git_clean=True
                )["path"],
                "docs/COMPOSITION_BENCHMARK_BUNDLE",
            )
            _write_json(directory / "host-results.json", {"changed": True})
            with self.assertRaisesRegex(
                bundle.CompositionBenchmarkBundleError, "unchanged from HEAD"
            ):
                bundle.resolve_composition_benchmark_bundle(
                    root, require_git_clean=True
                )

    def test_evidence_record_must_match_paths_hashes_and_digest_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_bundle(root)
            resolved = bundle.resolve_composition_benchmark_bundle(root)
            record = bundle.bundle_evidence_record(resolved)
            record["artifacts"]["host-results.json"]["sha256"] = "0" * 64
            self.assertEqual(
                bundle.validate_bundle_evidence_record(record, resolved),
                ["composition_benchmark.bundle.artifacts does not match bundle"],
            )
            record = bundle.bundle_evidence_record(resolved)
            record["unexpected"] = True
            self.assertEqual(
                bundle.validate_bundle_evidence_record(record, resolved),
                [
                    "composition_benchmark.bundle fields must be exactly "
                    "['artifacts', 'evidence_trust', 'manifest_digest', 'path', "
                    "'schema']"
                ],
            )
