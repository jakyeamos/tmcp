from __future__ import annotations

import unittest

from tmcp_runtime.domain import composition


class CompositionDomainTests(unittest.TestCase):
    def test_ui_classifiers_preserve_signal_boundaries_and_astro_support(self) -> None:
        self.assertTrue(composition.is_uiish_text("Design a responsive frontend dashboard."))
        self.assertFalse(composition.is_uiish_text("Build a guide for the API service."))
        self.assertTrue(composition.is_ui_file("app/page.astro"))
        self.assertTrue(composition.is_ui_file("src/styles/site.CSS"))
        self.assertFalse(composition.is_ui_file("src/service.py"))

    def test_contextual_gates_prioritize_hosted_evidence_over_debugging(self) -> None:
        atoms, reads, gates = composition.contextual_atoms_and_gates(
            "Fix the final release failure.",
            "final",
            {"failures": ["No hosted evidence is pending for this release."]},
        )

        self.assertIn("explicit-evidence-gaps", atoms)
        self.assertNotIn("debugging-regression", atoms)
        self.assertIn("verification-before-completion", atoms)
        self.assertIn(
            "Hosted release evidence record and release evidence checker output.",
            reads,
        )
        self.assertIn(
            "Do not claim release readiness until hosted evidence is recorded for release.",
            gates,
        )
        self.assertIn("Run the highest-signal verification gate before final response.", gates)

    def test_contextual_gates_cover_ui_files_and_browser_evidence(self) -> None:
        atoms, reads, gates = composition.contextual_atoms_and_gates(
            "Design the dashboard.",
            "start",
            {"files_changed": ["app/dashboard.astro"]},
        )

        self.assertEqual(atoms, ["ui-browser-verification"])
        self.assertIn("UI/browser verification guidance for changed surfaces.", reads)
        self.assertIn("Verify contrast on visible UI states.", gates)
        self.assertIn("Verify reduced motion behavior where animation is present.", gates)
        self.assertIn("Verify responsive behavior across relevant viewport sizes.", gates)

        evidence_atoms, _, evidence_gates = composition.contextual_atoms_and_gates(
            "Review the release notes.",
            "start",
            {"browser_evidence": ["screenshot captured"]},
        )
        self.assertEqual(evidence_atoms, ["ui-browser-verification"])
        self.assertEqual(
            evidence_gates, ["Use browser evidence to confirm the next claim."]
        )

    def test_source_gate_filtering_requires_matching_context(self) -> None:
        gates = [
            "Verify browser screenshot after interaction.",
            "Maintain canonical spreadsheet coverage.",
            "Run the focused unit test.",
        ]

        self.assertEqual(
            composition.filter_source_verification_gates(
                gates,
                "Improve release packaging.",
                {},
            ),
            ["Run the focused unit test."],
        )
        self.assertEqual(
            composition.filter_source_verification_gates(
                gates,
                "Audit the canonical spreadsheet behavior sweep.",
                {},
            ),
            ["Maintain canonical spreadsheet coverage.", "Run the focused unit test."],
        )
        self.assertEqual(
            composition.filter_source_verification_gates(
                gates,
                "Polish the frontend dashboard.",
                {"files_changed": ["app/page.tsx"]},
            ),
            ["Verify browser screenshot after interaction.", "Run the focused unit test."],
        )

    def test_matching_reference_reads_selects_only_relevant_references(self) -> None:
        source_nodes = [
            {"relative_path": "docs/reference/craft.md"},
            {"relative_path": "docs/references/brand.md"},
            {"relative_path": "docs/reference/product.md"},
            {"relative_path": "docs/reference/verification.md"},
            {"relative_path": "docs/other/brand.md"},
        ]

        self.assertEqual(
            composition.matching_reference_reads(
                source_nodes,
                "Craft a landing site dashboard and verify browser behavior.",
            ),
            [
                "docs/reference/craft.md",
                "docs/references/brand.md",
                "docs/reference/product.md",
                "docs/reference/verification.md",
            ],
        )


if __name__ == "__main__":
    unittest.main()
