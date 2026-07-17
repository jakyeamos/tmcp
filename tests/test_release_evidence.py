from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

from tests import test_tmcp_composition_benchmarks as benchmark_test_support
from tmcp_runtime.domain.composition_benchmarks import score_composition_benchmark

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECK_RELEASE_EVIDENCE_PATH = PLUGIN_ROOT / "scripts" / "check_release_evidence.py"
ACTIVE_RELEASE_VERSION = "0.5.7"


def load_check_release_evidence_module():
    spec = importlib.util.spec_from_file_location(
        "check_release_evidence", CHECK_RELEASE_EVIDENCE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load check_release_evidence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_verification_workflow(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "name: Verify",
                "",
                "on:",
                "  pull_request:",
                "  push:",
                "    branches:",
                "      - main",
                "    tags:",
                '      - "v*"',
                '      - "[0-9]*"',
                "",
                "jobs:",
                "  verify:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - name: Active release evidence",
                "        run: python scripts/check_release_evidence.py .",
                "",
            ]
        ),
        encoding="utf-8",
    )


def commit_file(root: Path, relative_path: str) -> None:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    home = root.parent / f"{root.name}-git-home"
    template = root.parent / f"{root.name}-git-template"
    home.mkdir()
    template.mkdir()
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["HOME"] = str(home)
    environment["XDG_CONFIG_HOME"] = str(home / "config")
    subprocess.run(
        ["git", "init", "--quiet", f"--template={template}"],
        cwd=root,
        env=environment,
        check=True,
    )
    subprocess.run(
        ["git", "add", "--", relative_path],
        cwd=root,
        env=environment,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            f"core.hooksPath={template}",
            "-c",
            "user.name=TMCP Test",
            "-c",
            "user.email=tmcp@example.test",
            "commit",
            "--quiet",
            "-m",
            "benchmark summary fixture",
        ],
        cwd=root,
        env=environment,
        check=True,
    )


def copy_release_evidence_fixture(root: Path) -> None:
    for relative in (
        ".codex-plugin/plugin.json",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
    ):
        source = PLUGIN_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    write_verification_workflow(root / ".github" / "workflows" / "verify.yml")
    write_json(
        root / "mcp-registry" / "draft-server.json",
        {
            "name": "io.github.jakyeamos/tmcp",
            "version": ACTIVE_RELEASE_VERSION,
        },
    )


def composition_benchmark_summary() -> dict[str, object]:
    builder = benchmark_test_support.CompositionBenchmarkTests()
    builder.setUpClass()
    summary = score_composition_benchmark(
        golden_cases=builder.golden_cases,
        fixture_definitions=builder.fixture_definitions,
        routing_results=builder._routing_results(),
        behavioral_results=builder._behavioral_results(),
    )
    return {"ok": True, **summary, "observations_sha256": "a" * 64}


def composition_benchmark_evidence(summary_digest: str) -> dict[str, object]:
    return {
        "composition_benchmark": {
            "schema": "tmcp-composition-benchmark-release-evidence-v0.1",
            "version": "0.6.0",
            "status": "reviewed",
            "summary_path": "docs/COMPOSITION_BENCHMARK_SUMMARY.json",
            "observations_sha256": "a" * 64,
            "summary_sha256": summary_digest,
            "review": {
                "status": "approved",
                "reviewer": "release-owner",
                "reviewed_at": "2026-07-17T12:00:00Z",
            },
        }
    }


class ReleaseEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load_check_release_evidence_module()

    def test_composition_benchmark_evidence_becomes_mandatory_at_0_6(self) -> None:
        self.assertFalse(self.checker.composition_benchmark_required("0.5.7"))
        self.assertTrue(self.checker.composition_benchmark_required("0.6.0"))
        errors = self.checker.validate_composition_benchmark_evidence(
            PLUGIN_ROOT,
            "0.6.0",
            {},
        )
        self.assertEqual(
            errors,
            ["docs/RELEASE_EVIDENCE.json composition_benchmark must be an object"],
        )

    def test_composition_benchmark_evidence_accepts_reviewed_committed_summary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "docs" / "COMPOSITION_BENCHMARK_SUMMARY.json"
            write_json(summary_path, composition_benchmark_summary())
            summary_digest = hashlib.sha256(summary_path.read_bytes()).hexdigest()
            commit_file(root, "docs/COMPOSITION_BENCHMARK_SUMMARY.json")

            errors = self.checker.validate_composition_benchmark_evidence(
                root,
                "0.6.0",
                composition_benchmark_evidence(summary_digest),
            )

        self.assertEqual(errors, [])

    def test_composition_benchmark_evidence_rejects_incomplete_handcrafted_summary(
        self,
    ) -> None:
        summary = {
            "schema": "tmcp-composition-benchmark-summary-v0.1",
            "eligible": True,
            "failed_checks": [],
            "acceptance_checks": {"expected_skill_recall": True},
            "routing_metrics": {
                "case_count": 25,
                "observed_case_count": 25,
                "missing_case_ids": [],
            },
            "behavioral_metrics": {"fixture_count": 5},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "docs" / "COMPOSITION_BENCHMARK_SUMMARY.json"
            write_json(summary_path, summary)
            summary_digest = hashlib.sha256(summary_path.read_bytes()).hexdigest()
            commit_file(root, "docs/COMPOSITION_BENCHMARK_SUMMARY.json")

            errors = self.checker.validate_composition_benchmark_evidence(
                root,
                "0.6.0",
                composition_benchmark_evidence(summary_digest),
            )

        self.assertIn(
            "composition benchmark summary fields must match bundled schema", errors
        )
        self.assertIn("composition benchmark summary must be fully eligible", errors)

    def test_composition_benchmark_evidence_binds_observations_digest(self) -> None:
        summary = composition_benchmark_summary()
        summary["observations_sha256"] = "b" * 64
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "docs" / "COMPOSITION_BENCHMARK_SUMMARY.json"
            write_json(summary_path, summary)
            summary_digest = hashlib.sha256(summary_path.read_bytes()).hexdigest()
            commit_file(root, "docs/COMPOSITION_BENCHMARK_SUMMARY.json")

            errors = self.checker.validate_composition_benchmark_evidence(
                root,
                "0.6.0",
                composition_benchmark_evidence(summary_digest),
            )

        self.assertIn(
            "composition_benchmark.observations_sha256 does not match summary",
            errors,
        )

    def test_composition_benchmark_evidence_rejects_changed_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "docs" / "COMPOSITION_BENCHMARK_SUMMARY.json"
            write_json(summary_path, composition_benchmark_summary())
            summary_digest = hashlib.sha256(summary_path.read_bytes()).hexdigest()
            commit_file(root, "docs/COMPOSITION_BENCHMARK_SUMMARY.json")
            changed = composition_benchmark_summary()
            changed["eligible"] = False
            write_json(summary_path, changed)

            errors = self.checker.validate_composition_benchmark_evidence(
                root,
                "0.6.0",
                composition_benchmark_evidence(summary_digest),
            )

        self.assertIn(
            "composition benchmark summary must be committed and unchanged at "
            "docs/COMPOSITION_BENCHMARK_SUMMARY.json",
            errors,
        )
        self.assertIn(
            "composition_benchmark.summary_sha256 does not match summary", errors
        )
        self.assertIn("composition benchmark summary must be fully eligible", errors)

    def test_release_evidence_accepts_current_tag_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": ACTIVE_RELEASE_VERSION,
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "tag",
                        "ref": f"v{ACTIVE_RELEASE_VERSION}",
                        "pr_number": None,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": 123456,
                        "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                        "notes": "Hosted tag run.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "pass")
        self.assertEqual(result["errors"], [])

    def test_release_evidence_accepts_main_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": ACTIVE_RELEASE_VERSION,
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "main",
                        "ref": "main",
                        "pr_number": None,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": 123456,
                        "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                        "notes": "Hosted main run accepted by release owner.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "pass")
        self.assertEqual(result["errors"], [])

    def test_release_evidence_workflow_contract_is_posix_on_windows_paths(
        self,
    ) -> None:
        original_workflow_path = getattr(self.checker, "WORKFLOW_PATH")
        setattr(
            self.checker,
            "WORKFLOW_PATH",
            PureWindowsPath(".github/workflows/verify.yml"),
        )
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                copy_release_evidence_fixture(root)
                write_json(
                    root / "docs" / "RELEASE_EVIDENCE.json",
                    {
                        "schema": "tmcp-release-evidence-v0.1",
                        "version": ACTIVE_RELEASE_VERSION,
                        "hosted_verification": {
                            "status": "completed",
                            "conclusion": "success",
                            "source": "tag",
                            "ref": f"v{ACTIVE_RELEASE_VERSION}",
                            "pr_number": None,
                            "workflow": ".github/workflows/verify.yml",
                            "run_id": 123456,
                            "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                            "notes": "Hosted tag run.",
                        },
                    },
                )

                result = self.checker.check_release_evidence(root)
        finally:
            setattr(self.checker, "WORKFLOW_PATH", original_workflow_path)

        self.assertEqual(result["hosted_release_evidence"], "pass")
        self.assertEqual(result["errors"], [])

    def test_release_evidence_requires_version_agnostic_tag_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            workflow = root / ".github" / "workflows" / "verify.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    '      - "v*"', '      - "v0.5.7"'
                ),
                encoding="utf-8",
            )
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": ACTIVE_RELEASE_VERSION,
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "tag",
                        "ref": f"v{ACTIVE_RELEASE_VERSION}",
                        "pr_number": None,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": 123456,
                        "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                        "notes": "Hosted tag run.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "fail")
        self.assertIn(
            ".github/workflows/verify.yml does not include tag trigger pattern 'v*'",
            result["errors"],
        )

    def test_release_evidence_rejects_non_semver_manifest_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            codex_manifest = root / ".codex-plugin" / "plugin.json"
            payload = json.loads(codex_manifest.read_text(encoding="utf-8"))
            payload["version"] = "0.4.0-invalid"
            write_json(codex_manifest, payload)

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "fail")
        self.assertTrue(
            any(
                "version is not a semver release" in error for error in result["errors"]
            )
        )

    def test_release_evidence_requires_premerge_ci_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            workflow = root / ".github" / "workflows" / "verify.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "python scripts/check_release_evidence.py .",
                    "python scripts/check_release_evidence.py --disabled",
                ),
                encoding="utf-8",
            )
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": ACTIVE_RELEASE_VERSION,
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "main",
                        "ref": "main",
                        "pr_number": None,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": 123456,
                        "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                        "notes": "Hosted main run accepted by release owner.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "fail")
        self.assertIn(
            ".github/workflows/verify.yml must run "
            "'python scripts/check_release_evidence.py .'",
            result["errors"],
        )

    def test_release_evidence_rejects_post_merge_only_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            workflow = root / ".github" / "workflows" / "verify.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "      - name: Active release evidence\n",
                    "      - name: Active release evidence\n"
                    "        if: github.event_name == 'push'\n",
                ),
                encoding="utf-8",
            )
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": ACTIVE_RELEASE_VERSION,
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "pull_request",
                        "ref": "codex/release-candidate",
                        "pr_number": 42,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": 123456,
                        "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                        "notes": "Hosted release PR run.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "fail")
        self.assertIn(
            ".github/workflows/verify.yml must run active release evidence on "
            "pull requests",
            result["errors"],
        )

    def test_release_evidence_requires_pull_request_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            workflow = root / ".github" / "workflows" / "verify.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "  pull_request:\n", "  workflow_dispatch:\n"
                ),
                encoding="utf-8",
            )
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": ACTIVE_RELEASE_VERSION,
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "pull_request",
                        "ref": "codex/release-candidate",
                        "pr_number": 42,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": 123456,
                        "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                        "notes": "Hosted release PR run.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "fail")
        self.assertIn(
            ".github/workflows/verify.yml must verify release evidence on pull "
            "requests",
            result["errors"],
        )

    def test_release_evidence_rejects_pending_current_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": ACTIVE_RELEASE_VERSION,
                    "hosted_verification": {
                        "status": "pending",
                        "conclusion": None,
                        "source": None,
                        "ref": None,
                        "pr_number": None,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": None,
                        "url": None,
                        "notes": "Pending hosted evidence.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "fail")
        self.assertIn(
            "hosted_verification.run_id must be a positive integer",
            result["errors"],
        )

    def test_release_evidence_requires_active_version_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": "0.3.0",
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "tag",
                        "ref": "v0.3.0",
                        "pr_number": None,
                        "workflow": ".github/workflows/verify.yml",
                        "run_id": 123456,
                        "url": "https://github.com/jakyeamos/tmcp/actions/runs/123456",
                        "notes": "Stale hosted tag run.",
                    },
                },
            )

            result = self.checker.check_release_evidence(root)

        self.assertEqual(result["hosted_release_evidence"], "fail")
        self.assertIn(
            f"docs/RELEASE_EVIDENCE.json version must match active release {ACTIVE_RELEASE_VERSION}",
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
