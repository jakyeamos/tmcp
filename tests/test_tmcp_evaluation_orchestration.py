from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_orchestration as evaluation_orchestration


class EvaluationOrchestrationTests(unittest.TestCase):
    def test_auto_mode_selects_plan_and_preserves_artifact_injection(self) -> None:
        calls: list[str] = []

        def build_plan(arguments: dict[str, object]) -> dict[str, object]:
            calls.append("plan")
            return {"schema": "plan"}

        def load_plan(arguments: dict[str, object]) -> dict[str, object]:
            calls.append("load")
            return {"schema": "plan"}

        def build_report(
            arguments: dict[str, object], plan: dict[str, object]
        ) -> dict[str, object]:
            calls.append("report")
            return {"schema": "report"}

        def write_artifacts(
            plan: dict[str, object] | None, report: dict[str, object] | None
        ) -> dict[str, str]:
            calls.append("write")
            return {"report": "report.json"}

        result = evaluation_orchestration.evaluate_mode(
            {"write_artifacts": True},
            build_plan=build_plan,
            load_plan=load_plan,
            build_report=build_report,
            artifact_writer=write_artifacts,
        )

        self.assertEqual(result["mode"], "plan")
        self.assertEqual(result["artifact_paths"], {"report": "report.json"})
        self.assertEqual(calls, ["plan", "write"])

    def test_score_mode_loads_plan_before_report(self) -> None:
        calls: list[str] = []

        def load_plan(arguments: dict[str, object]) -> dict[str, object]:
            calls.append("load")
            return {"schema": "plan"}

        def build_report(
            arguments: dict[str, object], plan: dict[str, object]
        ) -> dict[str, object]:
            self.assertEqual(plan["schema"], "plan")
            calls.append("report")
            return {"schema": "report"}

        result = evaluation_orchestration.evaluate_mode(
            {"mode": "score", "run_evidence_json": [{}]},
            build_plan=lambda arguments: {"schema": "unused"},
            load_plan=load_plan,
            build_report=build_report,
        )

        self.assertEqual(result["mode"], "score")
        self.assertEqual(calls, ["load", "report"])

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_orchestration))
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
