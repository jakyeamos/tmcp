from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path, PureWindowsPath


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECK_RELEASE_EVIDENCE_PATH = PLUGIN_ROOT / "scripts" / "check_release_evidence.py"


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


def copy_release_evidence_fixture(root: Path) -> None:
    for relative in (
        ".codex-plugin/plugin.json",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".github/workflows/verify.yml",
        "mcp-registry/draft-server.json",
    ):
        source = PLUGIN_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


class ReleaseEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load_check_release_evidence_module()

    def test_release_evidence_accepts_current_tag_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            write_json(
                root / "docs" / "RELEASE_EVIDENCE.json",
                {
                    "schema": "tmcp-release-evidence-v0.1",
                    "version": "0.3.1",
                    "hosted_verification": {
                        "status": "completed",
                        "conclusion": "success",
                        "source": "tag",
                        "ref": "v0.3.1",
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

    def test_release_evidence_workflow_contract_is_posix_on_windows_paths(
        self,
    ) -> None:
        original_workflow_path = self.checker.WORKFLOW_PATH
        self.checker.WORKFLOW_PATH = PureWindowsPath(".github/workflows/verify.yml")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                copy_release_evidence_fixture(root)
                write_json(
                    root / "docs" / "RELEASE_EVIDENCE.json",
                    {
                        "schema": "tmcp-release-evidence-v0.1",
                        "version": "0.3.1",
                        "hosted_verification": {
                            "status": "completed",
                            "conclusion": "success",
                            "source": "tag",
                            "ref": "v0.3.1",
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
            self.checker.WORKFLOW_PATH = original_workflow_path

        self.assertEqual(result["hosted_release_evidence"], "pass")
        self.assertEqual(result["errors"], [])

    def test_release_evidence_rejects_pending_current_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy_release_evidence_fixture(root)
            (root / "docs").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(
                PLUGIN_ROOT / "docs" / "RELEASE_EVIDENCE.json",
                root / "docs" / "RELEASE_EVIDENCE.json",
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
            "docs/RELEASE_EVIDENCE.json version must match active release 0.3.1",
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
