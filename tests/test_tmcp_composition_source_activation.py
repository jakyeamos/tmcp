from __future__ import annotations

import unittest

from tests.test_tmcp_compositional_intelligence import _node, _proposal, _role
from tmcp_runtime.domain import compositional_intelligence as ci


class CompositionSourceActivationTests(unittest.TestCase):
    def test_scoped_seed_lifecycle_semantics_enter_the_composition_graph(self) -> None:
        seed = _node(
            "release-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#release-seed",
            "Release readiness verification receipt.",
            route_affinity=["release_readiness"],
            chains_before=["release-review"],
            chains_after=["research"],
            do_not_activate_with=["fast-ship"],
            phase_transitions={
                "verification": {
                    "next_phases": ["final"],
                    "activate_skills": ["release-review"],
                    "verification_gates": ["package verification passes"],
                }
            },
            verification_expectations=["package verification passes"],
            required_receipts=["verified release receipt"],
        )

        preflight = ci.prepare_composition([seed], "Verify release readiness")
        hints = preflight["scoped_seed_graph_hints"]
        role = _role(
            preflight,
            "release-seed",
            "release coordinator",
            "verification",
            covers=["Release is verified"],
        )
        proposal = _proposal(
            preflight,
            [role],
            [],
            current_phase="verification",
            success_criteria=["Release is verified"],
        )
        plan = ci.build_composition_plan(proposal, preflight)

        relations = {edge["relation"] for edge in hints["typed_edges"]}
        self.assertTrue(
            {
                "affinity_for_route",
                "precedes",
                "enables",
                "conflicts_with",
                "defines_phase_transition",
                "requires_verification",
                "requires_receipt",
            }.issubset(relations)
        )
        self.assertTrue(all(edge["citations"] for edge in hints["typed_edges"]))
        self.assertEqual(
            plan["scoped_seed_graph_hints"]["scoped_seeds"][0]["id"],
            "release-seed",
        )
        self.assertGreater(
            plan["provenance"]["normalized_scoped_seed_relationship_count"],
            0,
        )

    def test_source_roles_prevent_implicit_fixture_and_reference_activation(
        self,
    ) -> None:
        governing = _node(
            "governing",
            "agent_operating_contract",
            "AGENTS.md",
            "Keep main deployable.",
        )
        skill = _node(
            "ui-skill", "skill_definition", "skills/ui/SKILL.md", "Implement the UI."
        )
        fixture_skill = _node(
            "fixture-skill",
            "skill_definition",
            "tests/fixtures/ui/SKILL.md",
            "Fixture-only instructions.",
        )
        reference = _node(
            "reference",
            "project_documentation",
            "docs/ui.md",
            "Supporting UI examples.",
        )

        self.assertEqual(ci.source_role_for(governing), "governing_instruction")
        self.assertEqual(ci.source_role_for(skill), "active_skill")
        self.assertEqual(ci.source_role_for(fixture_skill), "evidence_only")
        self.assertEqual(ci.source_role_for(reference), "supporting_reference")
        self.assertEqual(
            ci.source_role_for(fixture_skill, explicitly_scoped=True), "active_skill"
        )

    def test_explicit_scope_can_activate_a_fixture_skill(self) -> None:
        path = "tests/fixtures/explicit/SKILL.md"
        preflight = ci.prepare_composition(
            [_node("explicit", "skill_definition", path, "Explicit fixture proof.")],
            "Run the explicit fixture proof",
            explicitly_scoped_paths=[path],
        )

        source = preflight["candidate_source_slices"][0]
        self.assertEqual(source["source_role"], "active_skill")
        self.assertTrue(source["explicitly_scoped"])


if __name__ == "__main__":
    unittest.main()
