from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_plan as evaluation_plan


class EvaluationPlanServiceTests(unittest.TestCase):
    def test_builds_plan_from_safe_sources_without_filesystem_access(self) -> None:
        plan = evaluation_plan.build_evaluation_plan_from_sources(
            [
                evaluation_plan.EvaluationSource(
                    display_path="skills/example/SKILL.md",
                    text=(
                        "---\nname: example\n---\n\n"
                        "## Required reads\nRead AGENTS.md first.\n\n"
                        "## Verification\nRun `pnpm test`.\n"
                    ),
                )
            ],
            [{"id": "task-1", "prompt": "Run the task.", "expected_observables": []}],
            ["original", "negative_control"],
            anti_patterns=[],
            effective_patterns=[],
            created_at="now",
            max_matrix_rows=10,
        )

        self.assertEqual(plan["schema"], "tmcp-skill-evaluation-plan-v0.1")
        self.assertEqual(plan["created_at"], "now")
        self.assertEqual(len(plan["task_matrix"]), 2)
        self.assertEqual(plan["variants"], ["negative_control", "original"])
        self.assertEqual(plan["evaluated_skills"][0]["title"], "example")

    def test_rejects_matrix_budget_before_rows_are_appended(self) -> None:
        with self.assertRaisesRegex(ValueError, "matrix"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [evaluation_plan.EvaluationSource("SKILL.md", "# Skill\n")],
                [{"id": "task-1", "expected_observables": []}],
                ["original"],
                anti_patterns=[],
                effective_patterns=[],
                created_at="now",
                max_matrix_rows=0,
            )

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_plan))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "datetime",
            "os",
            "pathlib",
            "scripts",
            "shutil",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "uuid",
        )
        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
