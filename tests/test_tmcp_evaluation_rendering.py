from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_rendering as evaluation_rendering


class EvaluationRenderingServiceTests(unittest.TestCase):
    def test_guidebook_and_catalog_render_supplied_data(self) -> None:
        entries = [
            {
                "title": "Concrete gates",
                "status": "recommended",
                "evidence_level": "static_review",
                "applies_to": ["implementation"],
                "internal_atoms": ["behavior-verification"],
                "prefer": "Run the command.",
                "avoid": "Make it good.",
            }
        ]
        patterns = [
            {
                "pattern_id": "verification.concrete-command",
                "label": "Concrete command",
                "classification": "effective_pattern",
                "internal_atoms": ("behavior-verification",),
                "good_example": "Run the command.",
                "weak_example": "Make it good.",
                "detection_terms": ("run",),
            }
        ]

        markdown = evaluation_rendering.render_guidebook_markdown(
            entries,
            evidence_levels=["static_review"],
        )
        catalog = evaluation_rendering.build_pattern_catalog(
            entries,
            patterns=patterns,
            created_at="now",
        )

        self.assertIn("# TMCP Skill Writing Guidebook", markdown)
        self.assertIn("### Concrete gates", markdown)
        self.assertEqual(catalog["created_at"], "now")
        self.assertEqual(catalog["patterns"][0]["pattern_id"], "verification.concrete-command")

    def test_pattern_merge_and_warning_formatting_are_pure(self) -> None:
        builtins = [{"pattern_id": "p1", "label": "Built-in"}]
        discovered = [{"pattern_id": "p1", "label": "Catalog", "detection_terms": ["make sure"]}]
        merged = evaluation_rendering.merge_pattern_catalog(builtins, discovered)
        warning = evaluation_rendering.format_harvest_warning(
            {
                "skill_path": "SKILL.md",
                "location": {"excerpt": "Make sure everything works."},
                "message": "Needs a gate.",
            },
            {
                "pattern_id": "p1",
                "label": "A warning",
                "suggested_harvest_warning": "Needs a concrete gate.",
                "detection_terms": ["make sure"],
            },
        )

        self.assertEqual(merged["p1"]["label"], "Catalog")
        self.assertIn("Needs a concrete gate.", warning)

    def test_harvest_advisories_filter_and_format_supplied_findings(self) -> None:
        findings = [
            {
                "pattern_id": "p1",
                "classification": "anti_pattern",
                "skill_path": "SKILL.md",
                "message": "Needs a gate.",
                "evidence_level": "static_review",
            },
            {"pattern_id": "p2", "classification": "effective_pattern"},
        ]
        advisories = evaluation_rendering.build_harvest_advisories(
            findings,
            {
                "p1": {
                    "pattern_id": "p1",
                    "label": "A warning",
                    "suggested_harvest_warning": "Needs a concrete gate.",
                    "safe_to_auto_warn": True,
                },
                "p2": {
                    "pattern_id": "p2",
                    "safe_to_auto_warn": True,
                },
            },
        )

        self.assertEqual(len(advisories), 1)
        self.assertEqual(advisories[0]["pattern_id"], "p1")
        self.assertIn("Needs a concrete gate.", advisories[0]["warning"])

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_rendering))
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
