from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tmcp_runtime.domain import declared_loads, families


def _signal_text(node: dict[str, object]) -> str:
    return str(node.get("signal") or "").lower()


class FamilyDomainTests(unittest.TestCase):
    def test_seed_resolution_uses_threshold_then_stable_tie_break_without_mutation(
        self,
    ) -> None:
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

        assert family_context is not None
        self.assertEqual(family_context["active_seed_id"], "zeta")
        self.assertEqual(
            family_context["primary_source_patterns"], ["skills/zeta/SKILL.md"]
        )
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

        assert family_context is not None
        self.assertEqual(family_context["active_seed_id"], "redesign_seed")
        self.assertEqual(
            family_context["route_affinity"],
            ["ui_ux_redesign", "frontend_implementation"],
        )

    def test_inactive_source_roles_cannot_activate_scoped_seed_families(self) -> None:
        for source_role in ("evidence_only", "supporting_reference"):
            with self.subTest(source_role=source_role):
                family_context = families.compose_family_context(
                    [
                        {
                            "source_type": "scoped_packet_seed",
                            "source_role": source_role,
                            "seed_id": "redesign_seed",
                            "objective_patterns": ["redesign"],
                            "route_affinity": ["ui_ux_redesign"],
                            "source_references": ["skills/redesign/SKILL.md"],
                        }
                    ],
                    "Redesign the dashboard.",
                    active_routes=["ui_ux_redesign"],
                    node_signal_text=_signal_text,
                )

                self.assertIsNone(family_context)

    def test_explicit_activation_flag_cannot_enable_supporting_seed(self) -> None:
        family_context = families.compose_family_context(
            [
                {
                    "source_type": "scoped_packet_seed",
                    "source_role": "supporting_reference",
                    "activation_eligible": True,
                    "seed_id": "reviewed_seed",
                    "objective_patterns": ["reviewed"],
                    "source_references": ["skills/reviewed/SKILL.md"],
                }
            ],
            "Use the reviewed seed.",
            node_signal_text=_signal_text,
        )

        self.assertIsNone(family_context)

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

        assert family_context is not None
        self.assertEqual(family_context["kind"], "router_skill")
        self.assertEqual(
            family_context["primary_skill_slugs"], ["product-design-runtime"]
        )
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

    def test_primary_sibling_and_support_document_deferral_respects_explicit_objective(
        self,
    ) -> None:
        family_context = {
            "primary_skill_slugs": ["product-design-runtime"],
            "primary_source_patterns": ["skills/product-design-runtime/SKILL.md"],
            "deferred_skill_slugs": ["ui-implementation"],
            "family_skills_root": "skills/",
        }
        primary = {
            "relative_path": "skills/product-design-runtime/SKILL.md",
            "source_type": "skill_definition",
        }
        sibling = {
            "relative_path": "skills/ui-implementation/SKILL.md",
            "source_type": "skill_definition",
        }
        install = {
            "relative_path": "INSTALL.md",
            "source_type": "project_documentation",
        }

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
            declared_loads.normalize_declared_load_pattern(
                " `product-decisions\\surfaces\\` "
            ),
            "product-decisions/surfaces/**",
        )
        self.assertEqual(
            declared_loads.normalize_declared_load_pattern("coverage-gaps.md"),
            "coverage-gaps.md",
        )

    def test_runtime_seed_context_uses_phase_alias_for_transition_only_seed(
        self,
    ) -> None:
        source_nodes = [
            {
                "source_type": "scoped_packet_seed",
                "seed_id": "runtime_only",
                "title": "Runtime only",
                "source_references": ["skills/runtime/SKILL.md"],
                "phase_transitions": {"runtime": {"next_phases": ["implementation"]}},
            }
        ]

        family_context, seed_node = families.runtime_family_seed_context(
            source_nodes,
            "Inspect unrelated service logs.",
            "start",
            node_signal_text=_signal_text,
        )

        assert family_context is not None
        assert seed_node is not None
        self.assertEqual(seed_node["seed_id"], "runtime_only")
        self.assertEqual(family_context["active_seed_id"], "runtime_only")
        self.assertEqual(
            family_context["primary_source_patterns"], ["skills/runtime/SKILL.md"]
        )

    def test_transition_only_inactive_seed_cannot_activate_at_runtime(self) -> None:
        family_context, seed_node = families.runtime_family_seed_context(
            [
                {
                    "source_type": "scoped_packet_seed",
                    "source_role": "evidence_only",
                    "seed_id": "fixture-seed",
                    "phase_transitions": {
                        "runtime": {"next_phases": ["implementation"]}
                    },
                }
            ],
            "Inspect unrelated service logs.",
            "start",
            node_signal_text=_signal_text,
        )

        self.assertIsNone(family_context)
        self.assertIsNone(seed_node)

    def test_runtime_delta_preserves_phase_and_read_order_without_mutation(
        self,
    ) -> None:
        family_context = {
            "active_seed_id": "runtime",
            "primary_skill_slugs": ["runtime"],
            "deferred_skill_slugs": ["ui-polish-verification", "ui-review"],
        }
        source_nodes = [
            {
                "relative_path": "skills/ui-polish-verification/SKILL.md",
                "source_type": "skill_definition",
                "routing_metadata": {
                    "declared_loads": ["decisions/**"],
                    "required_reads": ["references/frame-audit-checklist.md"],
                },
            },
            {
                "relative_path": "skills/unrelated/SKILL.md",
                "source_type": "skill_definition",
            },
            {
                "relative_path": "decisions/dashboard.md",
                "source_type": "project_documentation",
            },
        ]
        seed_node = {
            "phase_transitions": {
                "implementation": {
                    "next_phases": ["implementation", "polish-verify", "review"],
                    "activate_skills": ["ui-polish-verification"],
                    "verification_gates": ["Capture browser evidence."],
                }
            }
        }
        before_nodes = copy.deepcopy(source_nodes)
        delta = families.runtime_family_packet_delta(
            current_phase="implementation",
            family_context=family_context,
            seed_node=seed_node,
            source_nodes=source_nodes,
            objective="Polish the dashboard with a screenshot.",
            context={"browser_evidence": ["desktop screenshot"]},
            latest_user_message="The implementation is ready.",
        )

        self.assertEqual(delta["suggested_phase"], "polish-verify")
        self.assertEqual(delta["suggested_skills"], ["ui-polish-verification"])
        self.assertEqual(delta["deferred_skills"], ["ui-review"])
        self.assertEqual(delta["activated_atoms"], ["skill:ui-polish-verification"])
        self.assertEqual(delta["deactivated_atoms"], ["skill:runtime"])
        self.assertEqual(
            delta["newly_required_reads"],
            [
                "skills/ui-polish-verification/SKILL.md",
                "decisions/dashboard.md",
                "references/frame-audit-checklist.md",
            ],
        )
        self.assertEqual(source_nodes, before_nodes)

    def test_runtime_delta_holds_before_resolving_declared_reads(self) -> None:
        with patch(
            "tmcp_runtime.domain.families.resolve_declared_load_paths",
            side_effect=AssertionError(
                "hold language must skip declared-read resolution"
            ),
        ):
            delta = families.runtime_family_packet_delta(
                current_phase="runtime",
                family_context={"active_seed_id": "runtime"},
                seed_node={
                    "phase_transitions": {
                        "runtime": {
                            "next_phases": ["implementation"],
                            "activate_skills": ["ui-implementation"],
                        }
                    }
                },
                source_nodes=[],
                objective="Implement the dashboard.",
                context={},
                latest_user_message="Hold on before implementing.",
            )

        self.assertEqual(delta, {})

    def test_runtime_delta_uses_chains_after_fallback_from_start_alias(self) -> None:
        family_context = {
            "active_seed_id": "runtime",
            "chains_after": ["ui-implementation"],
            "primary_skill_slugs": ["runtime"],
            "deferred_skill_slugs": ["ui-implementation", "ui-review"],
        }
        source_nodes = [
            {
                "relative_path": "skills/ui-implementation/SKILL.md",
                "source_type": "skill_definition",
            }
        ]
        delta = families.runtime_family_packet_delta(
            current_phase="start",
            family_context=family_context,
            seed_node={"seed_id": "runtime"},
            source_nodes=source_nodes,
            objective="Implement the dashboard.",
            context={},
            latest_user_message="The runtime brief is ready.",
        )

        self.assertEqual(delta["suggested_phase"], "implementation")
        self.assertEqual(delta["suggested_skills"], ["ui-implementation"])
        self.assertEqual(delta["deferred_skills"], ["ui-review"])
        self.assertEqual(delta["activated_atoms"], ["skill:ui-implementation"])
        self.assertEqual(delta["deactivated_atoms"], ["skill:runtime"])
        self.assertEqual(
            delta["newly_required_reads"], ["skills/ui-implementation/SKILL.md"]
        )
        self.assertEqual(
            delta["verification_gates"],
            ["Complete the current family phase before advancing."],
        )


if __name__ == "__main__":
    unittest.main()
