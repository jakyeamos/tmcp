from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_policy as evaluation_policy


ANTI_PATTERNS = [
    {
        "pattern_id": "verification.vague-quality-language",
        "classification": "anti_pattern",
        "internal_atoms": ("behavior-verification",),
        "detection_terms": ("make sure",),
    }
]
EFFECTIVE_PATTERNS = [
    {
        "pattern_id": "verification.concrete-command",
        "classification": "effective_pattern",
        "internal_atoms": ("behavior-verification",),
        "detection_terms": ("run `",),
    }
]


class EvaluationPolicyServiceTests(unittest.TestCase):
    def test_decomposition_and_static_review_are_text_only(self) -> None:
        text = """---
name: approval-before-edit
description: Use before editing.
---

## Required reads
Read AGENTS.md first.

## Verification
Make sure everything works.
"""

        decomposition = evaluation_policy.decompose_skill("skills/SKILL.md", text)
        findings = evaluation_policy.static_review(
            decomposition,
            text,
            anti_patterns=ANTI_PATTERNS,
            effective_patterns=EFFECTIVE_PATTERNS,
        )

        self.assertEqual(decomposition["title"], "approval-before-edit")
        self.assertIn("AGENTS.md", decomposition["routing_slices"]["required_reads"])
        self.assertEqual(
            findings[0]["pattern_id"], "verification.vague-quality-language"
        )

    def test_decomposition_derives_title_without_frontmatter(self) -> None:
        decomposition = evaluation_policy.decompose_skill(
            "skills/plain-skill.md",
            "# Plain skill\n\nRun the command.\n",
        )

        self.assertEqual(decomposition["title"], "plain-skill")

    def test_variant_payloads_and_observables_preserve_contracts(self) -> None:
        decomposition = {
            "title": "example",
            "frontmatter": {"description": "Use for a task."},
            "sections": [
                {"id": "verification", "title": "Verification", "text": "Run tests."}
            ],
            "routing_slices": {
                "required_reads": ["AGENTS.md"],
                "verification_gates": ["Run tests."],
                "output_contract": ["Report results."],
            },
        }

        variant = evaluation_policy._variant_payload(
            "verification-only",
            decomposition,
            "body",
        )
        observables = evaluation_policy._observable_contract(decomposition, [])

        self.assertEqual(variant["included_slices"], ["verification_gates"])
        self.assertIn(
            "read_required_file", {item["observable_id"] for item in observables}
        )

    def test_rewritten_trigger_prefers_narrow_body_trigger(self) -> None:
        text = """---
name: release
description: Use for any task in a repository.
---

Use this skill when the user asks you to prepare or validate a release.
"""
        decomposition = evaluation_policy.decompose_skill("skills/SKILL.md", text)

        variant = evaluation_policy._variant_payload("rewritten", decomposition, text)

        self.assertIn(
            "Use this skill when the user asks you to prepare or validate a release.",
            variant["content"],
        )
        self.assertNotIn("Use for any task in a repository.", variant["content"])
        self.assertIn(
            "Always include these labeled fields in the final response:",
            variant["content"],
        )

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_policy))
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
