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
        self.assertFalse(variant["intervention"]["causal_attribution"])
        self.assertEqual(
            variant["intervention"]["confounders"],
            ["frontmatter", "document_scaffold"],
        )
        self.assertIn(
            "read_required_file", {item["observable_id"] for item in observables}
        )

    def test_ablation_preserves_frontmatter_and_removes_one_named_section(self) -> None:
        text = """---
name: example
description: Use for an example.
---

# Example

## Verification
Run first check.

## Verification
Run second check.

## Output Contract
Report pass or fail.
"""
        decomposition = evaluation_policy.decompose_skill("SKILL.md", text)

        self.assertEqual(
            [section["id"] for section in decomposition["sections"]],
            ["preamble", "verification", "verification-2", "output-contract"],
        )
        variant = evaluation_policy._variant_payload(
            "ablated", decomposition, text, "verification"
        )

        self.assertTrue(variant["content"].startswith("---\nname: example"))
        self.assertNotIn("Run first check.", variant["content"])
        self.assertIn("Run second check.", variant["content"])
        self.assertIn("Report pass or fail.", variant["content"])
        self.assertEqual(
            variant["intervention"],
            {
                "kind": "single_section_ablation",
                "target": "verification",
                "causal_attribution": True,
            },
        )

    def test_ablation_preserves_irregular_formatting_outside_removed_section(
        self,
    ) -> None:
        text = (
            "---\nname: irregular\n---\n\n\n"
            "# Irregular\n\n\n"
            "## Workflow\n"
            "First line.  \n\n\nSecond line.\n\n"
            "## Output\n\n"
            "  Keep this indentation.\n"
        )
        decomposition = evaluation_policy.decompose_skill("SKILL.md", text)

        variant = evaluation_policy._variant_payload(
            "ablated", decomposition, text, "workflow"
        )

        self.assertEqual(
            variant["content"],
            "---\nname: irregular\n---\n\n\n# Irregular\n\n\n## Output\n\n"
            "  Keep this indentation.\n",
        )
        self.assertTrue(variant["intervention"]["causal_attribution"])

    def test_trigger_only_is_skill_frontmatter_not_json(self) -> None:
        text = """---
name: example
description: Use for an example.
---

# Example
"""
        decomposition = evaluation_policy.decompose_skill("SKILL.md", text)

        variant = evaluation_policy._variant_payload(
            "trigger-only", decomposition, text
        )

        self.assertEqual(
            variant["content"],
            "---\nname: example\ndescription: Use for an example.\n---",
        )
        self.assertFalse(variant["intervention"]["causal_attribution"])
        self.assertIn(
            "forced_attachment_bypasses_host_routing",
            variant["intervention"]["confounders"],
        )

    def test_unknown_variant_is_rejected(self) -> None:
        decomposition = evaluation_policy.decompose_skill("SKILL.md", "# Example\n")

        with self.assertRaisesRegex(ValueError, "Unsupported evaluation variant"):
            evaluation_policy._variant_payload("made-up", decomposition, "# Example\n")

    def test_trigger_review_does_not_treat_use_when_as_inherently_overbroad(
        self,
    ) -> None:
        trigger_pattern = {
            "pattern_id": "trigger.overbroad-description",
            "classification": "anti_pattern",
            "internal_atoms": ("tool-use-policy",),
            "detection_terms": ("always use", "any task"),
        }
        scoped = """---
name: release-review
description: Use when the user asks for release readiness.
---
"""
        broad = """---
name: everything
description: Always use for any task in the repository.
---
"""

        scoped_findings = evaluation_policy.static_review(
            evaluation_policy.decompose_skill("scoped/SKILL.md", scoped),
            scoped,
            anti_patterns=[trigger_pattern],
            effective_patterns=[],
        )
        broad_findings = evaluation_policy.static_review(
            evaluation_policy.decompose_skill("broad/SKILL.md", broad),
            broad,
            anti_patterns=[trigger_pattern],
            effective_patterns=[],
        )

        self.assertEqual(scoped_findings, [])
        self.assertEqual(
            broad_findings[0]["pattern_id"], "trigger.overbroad-description"
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
