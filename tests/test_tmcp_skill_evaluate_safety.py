from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_tmcp_skill_evaluate import EVALUATE_PATH, FIXTURE_SKILL, load_module
from tmcp_runtime.storage import ArtifactStorageError


class SkillEvaluateSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evaluate = load_module(EVALUATE_PATH, "tmcp_skill_evaluate_safety")

    def _plan_arguments(self, skill_path: Path) -> dict[str, object]:
        return {
            "skill_paths": [str(skill_path)],
            "task_fixtures": [
                {
                    "id": "approval-before-edit",
                    "prompt": "Fix the bug in this file.",
                    "expected_observables": [
                        "agent asks for approval before editing",
                    ],
                }
            ],
            "variants": ["baseline", "original", "negative_control"],
        }

    def _trace(self) -> list[dict[str, object]]:
        return [
            {
                "task_id": "approval-before-edit",
                "variant_id": "original",
                "observations": [
                    {"kind": "command_run", "value": "pnpm test"},
                ],
                "outcome": "passed",
            }
        ]

    def test_plan_redacts_source_fixture_and_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            secret = "sk-" + "C" * 40
            project = sandbox / secret
            project.mkdir()
            skill = project / "SKILL.md"
            skill.write_text(
                f"# {secret}\n\nUse {secret} only as an example.\n",
                encoding="utf-8",
            )
            output_dir = project / "artifacts"
            result = self.evaluate.evaluate_skills(
                {
                    "mode": "plan",
                    "project_path": str(project),
                    "skill_paths": [str(skill)],
                    "task_fixtures": [
                        {
                            "id": "redacted-fixture",
                            "prompt": secret,
                            "expected_observables": [secret],
                        }
                    ],
                    "variants": ["original"],
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                }
            )
            artifact_text = (output_dir / "tmcp-skill-evaluation-plan.json").read_text(
                encoding="utf-8"
            )

        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, artifact_text)
        self.assertGreater(result["redaction_summary"].get("openai_key", 0), 0)
        self.assertIn("[REDACTED:", artifact_text)

    def test_plan_rejects_non_skill_outside_project_and_oversized_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            project = sandbox / "project"
            outside = sandbox / "outside"
            project.mkdir()
            outside.mkdir()
            valid_skill = project / "SKILL.md"
            valid_skill.write_text("# Valid\n", encoding="utf-8")
            non_skill = project / "notes.md"
            non_skill.write_text("# Notes\n", encoding="utf-8")
            external_skill = outside / "SKILL.md"
            external_skill.write_text("# External\n", encoding="utf-8")
            oversized_skill = project / "nested" / "SKILL.md"
            oversized_skill.parent.mkdir()
            oversized_skill.write_text("# Oversized\n" + "x" * 262_145, encoding="utf-8")

            with self.assertRaises(ValueError):
                self.evaluate.build_evaluation_plan(
                    {**self._plan_arguments(non_skill), "project_path": str(project)}
                )
            with self.assertRaises(ValueError):
                self.evaluate.build_evaluation_plan(
                    {
                        **self._plan_arguments(external_skill),
                        "project_path": str(project),
                    }
                )
            with self.assertRaises(ValueError):
                self.evaluate.build_evaluation_plan(
                    {
                        **self._plan_arguments(oversized_skill),
                        "project_path": str(project),
                    }
                )

            plan = self.evaluate.build_evaluation_plan(
                {**self._plan_arguments(valid_skill), "project_path": str(project)}
            )

        self.assertEqual(plan["schema"], self.evaluate.EVAL_PLAN_SCHEMA)

    def test_score_composes_tampered_rows_without_reading_their_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_skill = Path(tmp) / "outside" / "SKILL.md"
            plan = self.evaluate.build_evaluation_plan(
                self._plan_arguments(FIXTURE_SKILL)
            )
            for skill in plan["evaluated_skills"]:
                skill["skill_path"] = str(missing_skill)
            for contract in plan["packet_inclusion_contracts"]:
                contract["skill_path"] = str(missing_skill)
            for row in plan["task_matrix"]:
                row["skill_path"] = str(missing_skill)

            report = self.evaluate.score_evidence(
                {
                    "evaluation_plan": plan,
                    "project_path": str(Path(tmp) / "project"),
                    "run_evidence_json": self._trace(),
                }
            )

        packet_score = report["packet_inclusion_scores"][0]
        self.assertEqual(packet_score["confidence"], "high")
        self.assertTrue(packet_score["signals"]["skill_selected_in_packet"])

    def test_score_redacts_inline_plan_and_evidence_before_artifact_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "artifacts"
            secret = "sk-" + "D" * 40
            plan = self.evaluate.build_evaluation_plan(
                self._plan_arguments(FIXTURE_SKILL)
            )
            original_row = next(
                row for row in plan["task_matrix"] if row["variant_id"] == "original"
            )
            original_row["skill_attachment"] = secret
            result = self.evaluate.evaluate_skills(
                {
                    "mode": "score",
                    "evaluation_plan": plan,
                    "run_evidence_json": [
                        {
                            **self._trace()[0],
                            "observations": [
                                {"kind": "assistant_message", "value": secret},
                            ],
                        }
                    ],
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                }
            )
            artifact_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output_dir.iterdir()
                if path.is_file()
            )

        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, artifact_text)
        self.assertGreater(result["redaction_summary"].get("openai_key", 0), 0)
        self.assertIn("[REDACTED:", artifact_text)

    def test_score_reads_a_persisted_plan_once_and_reuses_plan_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "evaluation-plan.json"
            output_dir = root / "artifacts"
            plan = self.evaluate.build_evaluation_plan(
                self._plan_arguments(FIXTURE_SKILL)
            )
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with patch.object(
                self.evaluate,
                "read_json_input",
                wraps=self.evaluate.read_json_input,
            ) as read_plan:
                result = self.evaluate.evaluate_skills(
                    {
                        "mode": "score",
                        "project_path": str(root),
                        "evaluation_plan": str(plan_path),
                        "run_evidence_json": self._trace(),
                        "write_artifacts": True,
                        "output_dir": str(output_dir),
                    }
                )

            self.assertEqual(read_plan.call_count, 1)
            self.assertTrue(
                (output_dir / "tmcp-skill-evaluation-plan.json").exists()
            )
            self.assertTrue(
                (output_dir / "tmcp-skill-evaluation-report.json").exists()
            )
            self.assertIn("artifact_paths", result)

    def test_plan_artifacts_refuse_a_symlinked_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            outside = sandbox / "outside"
            output_link = sandbox / "output-link"
            outside.mkdir()
            try:
                output_link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"Symlinks are unavailable in this environment: {exc}")

            with self.assertRaises(ArtifactStorageError):
                self.evaluate.evaluate_skills(
                    {
                        **self._plan_arguments(FIXTURE_SKILL),
                        "mode": "plan",
                        "write_artifacts": True,
                        "output_dir": str(output_link),
                    }
                )

            self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
