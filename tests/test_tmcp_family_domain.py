from __future__ import annotations

import copy
import unittest

from tmcp_runtime.domain import families


def _signal_text(node: dict[str, object]) -> str:
    return str(node.get("signal") or "").lower()


class FamilyDomainTests(unittest.TestCase):
    def test_seed_resolution_uses_threshold_then_stable_tie_break_without_mutation(self) -> None:
        first = {
            "source_type": "scoped_packet_seed",
            "seed_id": "alpha",
            "title": "Alpha",
            "objective_patterns": ["launch"],
            "use_when": ["launch"],
            "source_references": ["skills/alpha/SKILL.md"],
            "loads": ["guides/"],
        }
        second = {
            "source_type": "scoped_packet_seed",
            "seed_id": "zeta",
            "title": "Zeta",
            "objective_patterns": ["launch"],
            "use_when": ["launch"],
            "source_references": ["skills/zeta/SKILL.md"],
            "loads": ["notes/"],
        }
        router = {
            "source_type": "skill_definition",
            "relative_path": "skills/router/SKILL.md",
            "signal": "Choose exactly one primary mode. → alpha",
        }
        source_nodes = [first, second, router]
        before = copy.deepcopy(source_nodes)

        family_context = families.compose_family_context(
            source_nodes,
            "Prepare the launch packet.",
            active_routes=[],
            node_signal_text=_signal_text,
        )

        self.assertEqual(family_context["active_seed_id"], "zeta")
        self.assertEqual(family_context["primary_source_patterns"], ["skills/zeta/SKILL.md"])
        self.assertEqual(family_context["declared_loads"], ["notes/**"])
        self.assertEqual(source_nodes, before)

    def test_route_affinity_can_clear_scoped_seed_threshold(self) -> None:
        source_nodes = [
            {
                "source_type": "scoped_packet_seed",
                "seed_id": "redesign_seed",
                "title": "Redesign seed",
                "objective_patterns": ["redesign"],
                "route_affinity": ["ui_ux_redesign", "frontend_implementation"],
                "source_references": ["skills/redesign/SKILL.md"],
            }
        ]

        family_context = families.compose_family_context(
            source_nodes,
            "Redesign the dashboard.",
            active_routes=["ui_ux_redesign", "frontend_implementation"],
            node_signal_text=_signal_text,
        )

        self.assertEqual(family_context["active_seed_id"], "redesign_seed")
        self.assertEqual(
            family_context["route_affinity"],
            ["ui_ux_redesign", "frontend_implementation"],
        )

    def test_router_fallback_preserves_child_order_and_declared_loads(self) -> None:
        router = {
            "source_type": "skill_definition",
            "relative_path": ".agents/skills/product-judgment/SKILL.md",
            "signal": "Choose exactly one primary mode. → product-design-runtime → ui-implementation",
        }
        primary = {
            "source_type": "skill_definition",
            "relative_path": ".agents/skills/product-design-runtime/SKILL.md",
            "routing_metadata": {"declared_loads": ["product-decisions/**"]},
        }
        sibling = {
            "source_type": "skill_definition",
            "relative_path": ".agents/skills/ui-implementation/SKILL.md",
        }

        family_context = families.compose_family_context(
            [router, primary, sibling],
            "Use product design runtime before implementation.",
            node_signal_text=_signal_text,
        )

        self.assertEqual(family_context["kind"], "router_skill")
        self.assertEqual(family_context["primary_skill_slugs"], ["product-design-runtime"])
        self.assertEqual(
            family_context["primary_source_patterns"],
            [".agents/skills/product-design-runtime/SKILL.md"],
        )
        self.assertEqual(family_context["declared_loads"], ["product-decisions/**"])
        self.assertEqual(
            family_context["deferred_skill_slugs"],
            ["ui-implementation"],
        )
        self.assertEqual(
            family_context["router_relative_paths"],
            [".agents/skills/product-judgment/SKILL.md"],
        )

    def test_non_skill_source_cannot_activate_router_family(self) -> None:
        source_nodes = [
            {
                "source_type": "project_doc",
                "relative_path": "docs/routing.md",
                "signal": "Choose exactly one primary mode. → product-design-runtime",
            },
            {
                "source_type": "skill_definition",
                "relative_path": "skills/product-design-runtime/SKILL.md",
            },
        ]

        family_context = families.compose_family_context(
            source_nodes,
            "Use product design runtime.",
            node_signal_text=_signal_text,
        )

        self.assertIsNone(family_context)

    def test_primary_sibling_and_support_document_deferral_respects_explicit_objective(self) -> None:
        family_context = {
            "primary_skill_slugs": ["product-design-runtime"],
            "primary_source_patterns": ["skills/product-design-runtime/SKILL.md"],
            "deferred_skill_slugs": ["ui-implementation"],
            "family_skills_root": "skills/",
        }
        primary = {"relative_path": "skills/product-design-runtime/SKILL.md"}
        sibling = {"relative_path": "skills/ui-implementation/SKILL.md"}
        install = {"relative_path": "INSTALL.md"}

        self.assertTrue(
            families.node_matches_family_primary(
                primary,
                family_context,
                "Use product design runtime.",
            )
        )
        self.assertTrue(
            families.node_is_deferred_family_sibling(
                sibling,
                family_context,
                "Use product design runtime.",
            )
        )
        self.assertFalse(
            families.node_is_deferred_family_sibling(
                sibling,
                family_context,
                "Use ui implementation after product design runtime.",
            )
        )
        self.assertTrue(
            families.node_is_deferred_family_sibling(
                install,
                family_context,
                "Use product design runtime.",
            )
        )
        self.assertFalse(
            families.node_is_deferred_family_sibling(
                install,
                family_context,
                "Read the install guide for product design runtime.",
            )
        )

    def test_declared_load_normalization_preserves_path_semantics(self) -> None:
        self.assertEqual(
            families.normalize_declared_load_pattern(" `product-decisions\\surfaces\\` "),
            "product-decisions/surfaces/**",
        )
        self.assertEqual(
            families.normalize_declared_load_pattern("coverage-gaps.md"),
            "coverage-gaps.md",
        )


if __name__ == "__main__":
    unittest.main()
