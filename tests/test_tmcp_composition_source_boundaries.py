from __future__ import annotations

import json
import unittest

from tests.test_tmcp_compositional_intelligence import _edge, _node, _proposal, _role
from tmcp_runtime.domain import compositional_intelligence as ci


class CompositionSourceBoundaryTests(unittest.TestCase):
    def test_compiled_plan_excludes_unselected_seed_lifecycle_graph(self) -> None:
        selected_seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator produces migration evidence.",
            required_receipts=["migration receipt"],
        )
        deferred_seed = _node(
            "release-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#release-seed",
            "Release coordinator produces release evidence.",
            required_receipts=["release-only receipt"],
            route_affinity=["release_readiness"],
        )
        preflight = ci.prepare_composition(
            [selected_seed, deferred_seed],
            "Prepare migration evidence.",
            include_all_active_source_slices=True,
        )
        selected_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["migration evidence"],
            exit_gates=["migration evidence"],
            covers=["migration evidence"],
        )
        proposal = _proposal(preflight, [selected_role], [])
        proposal["task_model"] = {
            "deliverables": ["migration evidence"],
            "success_criteria": ["migration evidence"],
            "constraints": [],
            "subgoals": ["migration evidence"],
            "evidence_needs": ["migration evidence"],
        }
        proposal["coverage"] = {"facets": ["migration evidence"], "unresolved_gaps": []}

        self.assertIn(
            "release-seed",
            {
                seed["id"]
                for seed in preflight["scoped_seed_graph_hints"]["scoped_seeds"]
            },
        )
        plan = ci.build_composition_plan(proposal, preflight)

        self.assertEqual(
            [seed["id"] for seed in plan["scoped_seed_graph_hints"]["scoped_seeds"]],
            ["migration-seed"],
        )
        self.assertNotIn(
            "release-only receipt",
            json.dumps(plan["scoped_seed_graph_hints"], sort_keys=True),
        )

    def test_selected_seed_rejects_an_unresolved_declared_dependency(self) -> None:
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator produces checksum handoff evidence.",
            chains_after=["missing-checksum"],
        )
        preflight = ci.prepare_composition(
            [seed],
            "Prepare migration evidence.",
        )
        role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            outputs=["checksum handoff"],
            exit_gates=["checksum handoff evidence"],
            covers=["checksum handoff"],
        )
        proposal = _proposal(preflight, [role], [])
        proposal["task_model"] = {
            "deliverables": ["checksum handoff"],
            "success_criteria": ["checksum handoff"],
            "constraints": [],
            "subgoals": [],
            "evidence_needs": [],
        }
        proposal["coverage"] = {"facets": ["checksum handoff"], "unresolved_gaps": []}

        result = ci.validate_semantic_proposal(proposal, preflight)

        self.assertFalse(result["valid"])
        self.assertIn(
            "unresolved_declared_dependency",
            {item["code"] for item in result["errors"]},
        )

    def test_harvested_incompatibility_resolves_skill_slug_aliases(self) -> None:
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator prepares a migration handoff.",
            use_when=["Prepare migration handoff"],
            do_not_activate_with=["fast-ship"],
        )
        target = _node(
            "opaque-id",
            "skill_definition",
            "skills/fast-ship/SKILL.md",
            "Fast ship procedure prepares a migration handoff.",
        )
        preflight = ci.prepare_composition(
            [seed, target],
            "Prepare migration handoff with fast ship evidence.",
        )
        seed_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            outputs=["migration handoff"],
            exit_gates=["migration handoff evidence"],
        )
        target_role = _role(
            preflight,
            "opaque-id",
            "fast ship procedure",
            "implementation",
            inputs=["migration handoff"],
            outputs=["fast ship evidence"],
            exit_gates=["fast ship evidence"],
            covers=["fast ship evidence"],
        )
        proposal = _proposal(
            preflight,
            [seed_role, target_role],
            [_edge(preflight, "migration-seed", "opaque-id", "complements")],
        )
        proposal["task_model"] = {
            "deliverables": ["fast ship evidence"],
            "success_criteria": ["fast ship evidence"],
            "constraints": [],
            "subgoals": [],
            "evidence_needs": [],
        }
        proposal["coverage"] = {"facets": ["fast ship evidence"], "unresolved_gaps": []}

        result = ci.validate_semantic_proposal(proposal, preflight)

        self.assertFalse(result["valid"])
        self.assertIn(
            "same_phase_conflict",
            {item["code"] for item in result["errors"]},
        )

    def test_multiple_governing_sources_are_independent_graph_roots(self) -> None:
        root = _node(
            "root-rules",
            "agent_operating_contract",
            "AGENTS.md",
            "Root authority receives root authority and produces root constraints.",
        )
        local = _node(
            "local-rules",
            "cursor_rule",
            ".cursor/rules/local.md",
            "Local authority receives local authority and produces local constraints.",
        )
        worker = _node(
            "worker",
            "skill_definition",
            "skills/worker/SKILL.md",
            "Implementation worker consumes root constraints and produces worker handoff.",
        )
        preflight = ci.prepare_composition(
            [root, local, worker],
            "Produce worker handoff from root constraints.",
            include_all_active_source_slices=True,
        )
        roles = [
            _role(
                preflight,
                "root-rules",
                "root authority",
                "start",
                inputs=["root authority"],
                outputs=["root constraints"],
                exit_gates=["root constraints"],
            ),
            _role(
                preflight,
                "local-rules",
                "local authority",
                "start",
                inputs=["local authority"],
                outputs=["local constraints"],
                exit_gates=["local constraints"],
            ),
            _role(
                preflight,
                "worker",
                "implementation worker",
                "implementation",
                inputs=["root constraints"],
                outputs=["worker handoff"],
                exit_gates=["worker handoff"],
                covers=["worker handoff"],
            ),
        ]
        proposal = _proposal(
            preflight,
            roles,
            [_edge(preflight, "root-rules", "worker", "enables")],
        )
        proposal["task_model"] = {
            "deliverables": ["worker handoff"],
            "success_criteria": ["worker handoff"],
            "constraints": ["root constraints"],
            "subgoals": ["worker handoff"],
            "evidence_needs": ["worker handoff"],
        }
        proposal["coverage"] = {"facets": ["worker handoff"], "unresolved_gaps": []}

        result = ci.validate_semantic_proposal(proposal, preflight)

        self.assertTrue(result["valid"], result["errors"])

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
