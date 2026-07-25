from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.validate_skill_fixture_artifact import validate_fixture_artifact


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_skill_fixture_artifact.py"
SPEC = {
    "schema": "tmcp-skill-fixture-structural-spec-v0.1",
    "case_id": "trigger-required-read-composition",
    "exact_value": "valid",
    "required_final_labels": [
        "Sources inspected",
        "Skipped sources and why",
        "Verification results",
        "Next actions",
    ],
    "required_disclosure_terms": ["AGENTS.md", "required", "unavailable"],
    "forbidden_action_markers": [
        "release check",
        "release verification",
        "check_release",
        "check_release_package",
    ],
}


def _artifact(final_response: str, *, actions: list[str] | None = None) -> dict[str, object]:
    return {
        "observations": ["The inspected target's exact value is valid."],
        "actions": actions or ["Read the target."],
        "final_response": final_response,
    }


class SkillFixtureArtifactValidatorTests(unittest.TestCase):
    def test_passes_when_all_observable_contracts_are_present(self) -> None:
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt\n"
                "Skipped sources and why: AGENTS.md was required but unavailable.\n"
                "Verification results: exact target value is valid.\n"
                "Next actions: None."
            ),
            SPEC,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["failed_observables"], [])

    def test_requires_labels_as_separate_structural_lines(self) -> None:
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt; Skipped sources and why: AGENTS.md was required but unavailable; "
                "Verification results: valid; Next actions: None."
            ),
            SPEC,
        )
        self.assertFalse(result["passed"])
        self.assertIn("required_final_labels", result["failed_observables"])

    def test_rejects_forbidden_release_activity(self) -> None:
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt\n"
                "Skipped sources and why: AGENTS.md was required but unavailable.\n"
                "Verification results: exact target value is valid.\n"
                "Next actions: None.",
                actions=["Ran check_release_package.py."],
            ),
            SPEC,
        )
        self.assertFalse(result["passed"])
        self.assertIn("forbidden_actions", result["failed_observables"])

    def test_allows_explicitly_not_running_release_checks(self) -> None:
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt\n"
                "Skipped sources and why: AGENTS.md was required but unavailable.\n"
                "Verification results: exact target value is valid.\n"
                "Next actions: None.",
                actions=["Did not run broader release checks."],
            ),
            SPEC,
        )
        self.assertTrue(result["passed"])

    def test_rejects_missing_explicit_unavailability(self) -> None:
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt\n"
                "Skipped sources and why: AGENTS.md was not present.\n"
                "Verification results: exact target value is valid.\n"
                "Next actions: None."
            ),
            SPEC,
        )
        self.assertFalse(result["passed"])
        self.assertIn("required_disclosure", result["failed_observables"])

    def test_does_not_treat_embedded_value_as_exact_value(self) -> None:
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt\n"
                "Skipped sources and why: AGENTS.md was required but unavailable.\n"
                "Verification results: exact target value is invalid.\n"
                "Next actions: None."
            ),
            SPEC,
        )
        self.assertFalse(result["passed"])
        self.assertIn("exact_value", result["failed_observables"])

    def test_rejects_positive_file_mutation_action(self) -> None:
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt\n"
                "Skipped sources and why: AGENTS.md was required but unavailable.\n"
                "Verification results: exact target value is valid.\n"
                "Next actions: None.",
                actions=["Wrote the file with a corrected value."],
            ),
            SPEC,
        )
        self.assertFalse(result["passed"])
        self.assertIn("mutations", result["failed_observables"])

    def test_cli_returns_nonzero_for_failed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.json"
            spec = root / "spec.json"
            artifact.write_text(json.dumps(_artifact("not compliant")), encoding="utf-8")
            spec.write_text(json.dumps(SPEC), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(VALIDATOR), str(artifact), "--spec", str(spec)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertFalse(json.loads(completed.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
