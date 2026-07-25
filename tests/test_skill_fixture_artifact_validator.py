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
BATCH_VALIDATOR = ROOT / "scripts" / "validate_skill_fixture_batch.py"
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

    def test_accepts_reviewed_disclosure_pattern_alternatives(self) -> None:
        spec = {
            **SPEC,
            "required_disclosure_terms": [],
            "required_disclosure_patterns": [
                r"AGENTS\.md",
                r"required",
                r"(?:unavailable|missing|does not exist|not present)",
            ],
        }
        result = validate_fixture_artifact(
            _artifact(
                "Sources inspected: target.txt\n"
                "Skipped sources and why: AGENTS.md was required but missing.\n"
                "Verification results: exact target value is valid.\n"
                "Next actions: None."
            ),
            spec,
        )
        self.assertTrue(result["passed"])

    def test_accepts_structured_observations_and_requires_activity_marker(self) -> None:
        spec = {
            "case_id": "host-portability-inspection",
            "exact_value": "portable value",
            "required_activity_markers": ["portable file inspection"],
        }
        result = validate_fixture_artifact(
            {
                "observations": {
                    "Sources inspected": ["target.txt"],
                    "Verification results": "portable value",
                },
                "actions": ["Used ordinary portable file inspection."],
                "final_response": "portable value",
            },
            spec,
        )
        self.assertTrue(result["passed"])

    def test_fails_when_required_activity_is_only_claimed_in_final_response(self) -> None:
        result = validate_fixture_artifact(
            {
                "observations": ["The target was read."],
                "actions": ["Read the target."],
                "final_response": "portable value; used portable file inspection",
            },
            {"exact_value": "portable value", "required_activity_markers": ["portable file inspection"]},
        )
        self.assertFalse(result["passed"])
        self.assertIn("required_activity", result["failed_observables"])

    def test_accepts_reviewed_activity_pattern_alternatives(self) -> None:
        result = validate_fixture_artifact(
            {
                "observations": ["The target was located."],
                "actions": ["Inspected the file with ordinary portable shell commands."],
                "final_response": "portable value",
            },
            {
                "exact_value": "portable value",
                "required_activity_patterns": [r"portable\s+(?:file|shell)"],
            },
        )
        self.assertTrue(result["passed"])

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

    def test_batch_cli_preserves_per_artifact_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            passing = root / "passing.json"
            failing = root / "failing.json"
            spec = root / "spec.json"
            passing.write_text(
                json.dumps(_artifact(
                    "Sources inspected: target.txt\n"
                    "Skipped sources and why: AGENTS.md was required but unavailable.\n"
                    "Verification results: exact target value is valid.\n"
                    "Next actions: None."
                )),
                encoding="utf-8",
            )
            failing.write_text(json.dumps(_artifact("not compliant")), encoding="utf-8")
            spec.write_text(json.dumps(SPEC), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(BATCH_VALIDATOR), str(passing), str(failing), "--spec", str(spec)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(report["artifact_count"], 2)
            self.assertEqual(report["passed_count"], 1)
            self.assertEqual([item["passed"] for item in report["results"]], [True, False])


if __name__ == "__main__":
    unittest.main()
