from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tmcp_runtime.domain.routes import (
    derive_task_identity,
    score_routes,
    source_boost_for_node,
    task_identity_delta,
)
from tests import test_tmcp_mcp_server as helpers


REDESIGN_OBJECTIVE = (
    "Redesign these pages. Make them visually striking, interactive, modern, "
    "motion-rich, and production-ready."
)
ROUTING_GOLDEN = (
    Path(__file__).resolve().parent / "fixtures" / "composition_routing_golden_v0_6.json"
)


class TmcpRouteCatalogTests(unittest.TestCase):
    def test_redesign_prompt_scores_multiple_routes(self) -> None:
        signals = score_routes(REDESIGN_OBJECTIVE)
        routes = {item["route"] for item in signals}
        self.assertIn("ui_ux_redesign", routes)
        self.assertIn("motion_interaction", routes)
        self.assertIn("frontend_implementation", routes)

    def test_derive_task_identity_uses_composite_primary(self) -> None:
        identity = derive_task_identity(REDESIGN_OBJECTIVE)
        self.assertEqual(identity["primary"], "frontend_product_redesign")
        self.assertIn("motion_interaction", identity["active_routes"])
        self.assertIn("ui_ux_redesign", identity["active_routes"])
        self.assertIn("frontend_implementation", identity["active_routes"])
        self.assertGreater(float(identity["confidence"]), 0.5)

    def test_ui_file_changes_keep_implementation_route(self) -> None:
        intake = derive_task_identity(REDESIGN_OBJECTIVE)
        runtime = derive_task_identity(
            REDESIGN_OBJECTIVE,
            {"files_changed": ["app/page.tsx"]},
        )
        self.assertIn("frontend_implementation", runtime["active_routes"])
        self.assertIn("frontend_implementation", intake["active_routes"])

    def test_task_identity_delta_reports_primary_change(self) -> None:
        previous = derive_task_identity("Debug the failing login test")
        current = derive_task_identity("Redesign the login page")
        delta = task_identity_delta(previous, current, reason="user_redirect")
        self.assertIsNotNone(delta)
        assert delta is not None
        self.assertNotEqual(delta["previous"]["primary"], delta["current"]["primary"])
        self.assertEqual(delta["reason"], "user_redirect")

    def test_embedded_route_terms_do_not_create_unrelated_routes(self) -> None:
        identity = derive_task_identity(
            "Run a promotion-grade multi-configuration skill evaluation."
        )

        self.assertEqual(identity["primary"], "general_task")
        self.assertEqual(identity["active_routes"], [])
        self.assertEqual(identity["confidence"], 0.0)

    def test_lexical_stems_still_match_suffix_forms(self) -> None:
        routes = {
            item["route"] for item in score_routes("Build components with animations.")
        }

        self.assertIn("frontend_implementation", routes)
        self.assertIn("motion_interaction", routes)

    def test_intended_prefix_compounds_have_explicit_routes(self) -> None:
        cases = {
            "Rebuild the webpage.": "frontend_implementation",
            "Diagnose underperformance.": "performance_validation",
            "Prepare the prerelease.": "release_readiness",
        }

        for objective, expected_route in cases.items():
            with self.subTest(objective=objective):
                routes = {item["route"] for item in score_routes(objective)}
                self.assertIn(expected_route, routes)

    def test_source_boosts_reject_embedded_route_terms(self) -> None:
        motion_boost = source_boost_for_node(
            "motion_interaction",
            relative_path="skills/promotion/SKILL.md",
            source_type="skill_definition",
            text="Guide a promotion campaign.",
        )
        release_boost = source_boost_for_node(
            "release_readiness",
            relative_path="skills/relationships/SKILL.md",
            source_type="skill_definition",
            text="Review relationship and leadership guidance.",
        )

        self.assertEqual(motion_boost, 0.0)
        self.assertEqual(release_boost, 0.0)
        self.assertGreater(
            source_boost_for_node(
                "motion_interaction",
                relative_path="skills/product-motion/SKILL.md",
                source_type="skill_definition",
                text="Design motion-safe interactions.",
            ),
            0.0,
        )

    def test_statistical_contrast_does_not_activate_accessibility(self) -> None:
        identity = derive_task_identity(
            "Score the workflow-section contrast in a skill evaluation."
        )

        self.assertEqual(identity["primary"], "general_task")
        self.assertNotIn("accessibility_validation", identity["active_routes"])

    def test_visual_contrast_still_activates_accessibility(self) -> None:
        cases = (
            ("Verify color contrast in the browser.", None),
            ("Verify contrast.", {"files_changed": ["app/page.tsx"]}),
        )

        for objective, context in cases:
            with self.subTest(objective=objective):
                routes = {item["route"] for item in score_routes(objective, context)}
                self.assertIn("accessibility_validation", routes)

    def test_compound_fallback_keeps_weak_route_signals_advisory(self) -> None:
        identity = derive_task_identity(
            "Research the evidence, write a decision brief, and review every claim."
        )

        self.assertEqual(identity["primary"], "compound_task")
        self.assertEqual(identity["routing_status"], "compound_fallback")
        self.assertEqual(identity["active_routes"], [])
        self.assertEqual(identity["validated_routes"], [])
        self.assertGreater(float(identity["confidence"]), 0.0)
        self.assertEqual(
            [item["facet"] for item in identity["facet_signals"]],
            identity["intent_facets"],
        )
        self.assertTrue(
            all(
                evidence.startswith("objective:")
                for item in identity["facet_signals"]
                for evidence in item["evidence"]
            )
        )
        self.assertIn("freshness_research", [item["route"] for item in identity["signals"]])

    def test_weak_single_route_signal_remains_unresolved(self) -> None:
        identity = derive_task_identity("Research a generic work item.")

        self.assertEqual(identity["primary"], "general_task")
        self.assertEqual(identity["routing_status"], "unresolved")
        self.assertEqual(identity["active_routes"], [])
        self.assertEqual(identity["validated_routes"], [])
        self.assertTrue(identity["signals"])

    def test_skill_composition_route_uses_narrow_compound_phrases(self) -> None:
        identity = derive_task_identity(
            "Build a compositional intelligence skill graph and validate a semantic proposal."
        )

        self.assertEqual(identity["primary"], "skill_composition")
        self.assertEqual(identity["routing_status"], "catalog_match")
        self.assertEqual(identity["active_routes"], ["skill_composition"])
        self.assertEqual(identity["validated_routes"], ["skill_composition"])
        self.assertNotIn(
            "skill_composition",
            {item["route"] for item in score_routes("Run a skill evaluation.")},
        )

    def test_scoped_seed_remains_a_separate_safe_identity_source(self) -> None:
        identity = derive_task_identity(
            "Review the readiness record.",
            family_context={
                "active_seed_id": "review-seed",
                "seed_name": "Review seed",
                "route_affinity": ["skill_composition"],
            },
        )

        self.assertEqual(identity["primary"], "review-seed")
        self.assertEqual(identity["routing_status"], "family_match")
        self.assertEqual(identity["validated_routes"], [])
        self.assertIn("review-seed", identity["active_routes"])

    def test_facet_only_task_identity_delta_is_material(self) -> None:
        previous = derive_task_identity("Research and write a brief.")
        current = derive_task_identity(
            "Research, write, verify, and release a brief."
        )

        delta = task_identity_delta(previous, current)

        self.assertIsNotNone(delta)
        assert delta is not None
        self.assertIn("verification", delta["changed_facets"])
        self.assertIn("lifecycle", delta["changed_facets"])
        self.assertEqual(delta["reason"], "task_identity_facets_changed")

    def test_every_composition_routing_golden_has_a_substantial_identity(self) -> None:
        golden = json.loads(ROUTING_GOLDEN.read_text(encoding="utf-8"))

        for case in golden["cases"]:
            with self.subTest(case_id=case["case_id"]):
                identity = derive_task_identity(case["objective"])
                self.assertNotEqual(identity["primary"], "general_task")
                self.assertGreaterEqual(len(identity["intent_facets"]), 2)


class TmcpComposedPacketIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_compose_packet_includes_task_identity_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / ".agents" / "skills" / "frontend-design"
            skill_dir.mkdir(parents=True)
            skill_dir.joinpath("SKILL.md").write_text(
                "# Frontend Design\nUse existing components before redesigning.\n",
                encoding="utf-8",
            )
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": REDESIGN_OBJECTIVE,
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 10,
                }
            )

        identity = result["task_identity"]
        self.assertEqual(identity["primary"], "frontend_product_redesign")
        self.assertIn("task_identity", result)
        self.assertIn("compiled_from", result)
        self.assertIn("packet_markdown", result)
        markdown = result["packet_markdown"]
        self.assertIn("## Task Identity", markdown)
        self.assertIn("frontend_product_redesign", markdown)
        self.assertIn("## Active Routes", markdown)
        self.assertIn("## Selection Rationale", markdown)
        self.assertIn("## Required Receipts", markdown)

    def test_runtime_next_includes_task_identity_delta(self) -> None:
        previous_identity = derive_task_identity("Plan the onboarding redesign")
        result = self.server._runtime_next(
            {
                "objective": REDESIGN_OBJECTIVE,
                "project_path": ".",
                "current_phase": "runtime",
                "previous_packet_id": "packet-test",
                "previous_task_identity": previous_identity,
                "files_changed": ["app/onboarding/page.tsx"],
                "cache_policy": "none",
            }
        )
        self.assertIn("task_identity", result)
        self.assertIn("frontend_product_redesign", result["task_identity"]["primary"])
        if result.get("task_identity_delta") is not None:
            self.assertIn("current", result["task_identity_delta"])


if __name__ == "__main__":
    unittest.main()
