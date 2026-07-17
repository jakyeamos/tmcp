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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_bundle(root: Path) -> Path:
    directory = root / bundle.BUNDLE_RELATIVE_PATH
    for index, (_, filename) in enumerate(bundle.BUNDLE_ARTIFACTS, start=1):
        _write_json(directory / filename, {"artifact": filename, "index": index})
    return directory


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
                {
                    "host-results.json": {"status": "clear", "redactions": {}},
                    "evaluator-artifacts.json": {
                        "status": "clear",
                        "redactions": {},
                    },
                },
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
            (directory / "host-results.json").write_text("changed", encoding="utf-8")
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
