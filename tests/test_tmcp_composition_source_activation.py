from __future__ import annotations

import copy
import unittest

from tests.test_tmcp_compositional_intelligence import _edge, _node, _proposal, _role
from tmcp_runtime.domain import compositional_intelligence as ci
from tmcp_runtime.domain.composition_runtime import (
    advance_composition_runtime,
    composition_gate_catalog,
)


class CompositionSourceActivationTests(unittest.TestCase):
    def test_declared_dependency_phase_cannot_activate_early(self) -> None:
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            (
                "Migration coordinator uses migration evidence, produces checksum "
                "handoff, and exits when checksum handoff is ready."
            ),
            phase_transitions={
                "verification": {"activate_skills": ["checksum-verifier"]}
            },
        )
        verifier = _node(
            "checksum-verifier",
            "skill_definition",
            "skills/checksum-verifier/SKILL.md",
            (
                "Checksum verifier uses checksum handoff, produces verified checksum "
                "evidence, and exits when verified checksum evidence is ready."
            ),
        )
        preflight = ci.prepare_composition(
            [seed, verifier],
            "Prepare migration evidence and verify checksum evidence.",
        )
        seed_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["checksum handoff"],
            exit_gates=["checksum handoff is ready"],
        )
        early_verifier_role = _role(
            preflight,
            "checksum-verifier",
            "checksum verifier",
            "implementation",
            inputs=["checksum handoff"],
            outputs=["verified checksum evidence"],
            exit_gates=["verified checksum evidence is ready"],
            covers=["verified checksum evidence"],
        )
        task_model = {
            "deliverables": ["verified checksum evidence"],
            "success_criteria": ["verified checksum evidence"],
            "constraints": ["migration evidence"],
            "subgoals": ["checksum handoff"],
            "evidence_needs": ["verified checksum evidence"],
        }
        early = _proposal(
            preflight,
            [seed_role, early_verifier_role],
            [_edge(preflight, "migration-seed", "checksum-verifier", "enables")],
            current_phase="implementation",
        )
        early["task_model"] = task_model
        early["coverage"] = {"facets": ["checksum evidence"], "unresolved_gaps": []}
        early_result = ci.validate_semantic_proposal(early, preflight)

        self.assertIn(
            "declared_dependency_phase_inversion",
            {item["code"] for item in early_result["errors"]},
        )

        verifier_role = {**early_verifier_role, "phase_affinity": ["verification"]}
        valid = {
            **early,
            "skill_roles": [seed_role, verifier_role],
        }
        valid_result = ci.validate_semantic_proposal(valid, preflight)
        self.assertTrue(valid_result["valid"], valid_result["errors"])

    def test_selected_seed_rejects_a_tampered_dependency_closure(self) -> None:
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator produces checksum handoff evidence.",
            chains_after=["checksum-verifier"],
        )
        verifier = _node(
            "checksum-verifier",
            "skill_definition",
            "skills/checksum-verifier/SKILL.md",
            "Checksum verifier uses checksum handoff and produces checksum evidence.",
        )
        preflight = ci.prepare_composition(
            [seed, verifier],
            "Prepare migration checksum evidence.",
        )
        seed_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["checksum handoff"],
            exit_gates=["checksum handoff evidence"],
        )
        verifier_role = _role(
            preflight,
            "checksum-verifier",
            "checksum verifier",
            "verification",
            inputs=["checksum handoff"],
            outputs=["checksum evidence"],
            exit_gates=["checksum evidence"],
            covers=["checksum evidence"],
        )
        proposal = _proposal(
            preflight,
            [seed_role, verifier_role],
            [_edge(preflight, "migration-seed", "checksum-verifier", "enables")],
        )
        proposal["task_model"] = {
            "deliverables": ["checksum evidence"],
            "success_criteria": ["checksum evidence"],
            "constraints": ["migration evidence"],
            "subgoals": ["checksum handoff"],
            "evidence_needs": ["checksum evidence"],
        }
        proposal["coverage"] = {"facets": ["checksum evidence"], "unresolved_gaps": []}
        tampered = copy.deepcopy(preflight)
        tampered["scoped_seed_graph_hints"]["declared_dependency_closure"] = []

        result = ci.validate_semantic_proposal(proposal, tampered)
        self.assertIn(
            "invalid_declared_dependency_closure",
            {item["code"] for item in result["errors"]},
        )

    def test_selected_seed_rejects_missing_source_backed_lifecycle_hint(self) -> None:
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator produces checksum handoff evidence.",
            chains_after=["checksum-verifier"],
        )
        verifier = _node(
            "checksum-verifier",
            "skill_definition",
            "skills/checksum-verifier/SKILL.md",
            "Checksum verifier uses checksum handoff and produces checksum evidence.",
        )
        preflight = ci.prepare_composition(
            [seed, verifier],
            "Prepare migration checksum evidence.",
        )
        seed_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["checksum handoff"],
            exit_gates=["checksum handoff evidence"],
        )
        verifier_role = _role(
            preflight,
            "checksum-verifier",
            "checksum verifier",
            "verification",
            inputs=["checksum handoff"],
            outputs=["checksum evidence"],
            exit_gates=["checksum evidence"],
            covers=["checksum evidence"],
        )
        proposal = _proposal(
            preflight,
            [seed_role, verifier_role],
            [_edge(preflight, "migration-seed", "checksum-verifier", "enables")],
        )
        proposal["task_model"] = {
            "deliverables": ["checksum evidence"],
            "success_criteria": ["checksum evidence"],
            "constraints": ["migration evidence"],
            "subgoals": ["checksum handoff"],
            "evidence_needs": ["checksum evidence"],
        }
        proposal["coverage"] = {"facets": ["checksum evidence"], "unresolved_gaps": []}
        tampered = copy.deepcopy(preflight)
        tampered["scoped_seed_graph_hints"]["scoped_seeds"] = []
        tampered["scoped_seed_graph_hints"]["declared_dependency_closure"][
            "required_dependency_nodes"
        ] = []

        result = ci.validate_semantic_proposal(proposal, tampered)

        self.assertIn(
            "missing_selected_scoped_seed_hint",
            {item["code"] for item in result["errors"]},
        )

    def test_selected_dependency_seed_requires_its_declaring_parent(self) -> None:
        parent = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator prepares migration evidence.",
            use_when=["Prepare migration evidence."],
            chains_after=["checksum-seed"],
        )
        child = _node(
            "checksum-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#checksum-seed",
            "Checksum coordinator produces checksum evidence.",
        )
        preflight = ci.prepare_composition(
            [parent, child],
            "Prepare migration evidence.",
        )
        child_role = _role(
            preflight,
            "checksum-seed",
            "checksum coordinator",
            "verification",
            inputs=["migration evidence"],
            outputs=["checksum evidence"],
            exit_gates=["checksum evidence"],
            covers=["checksum evidence"],
        )
        proposal = _proposal(preflight, [child_role], [])
        proposal["task_model"] = {
            "deliverables": ["checksum evidence"],
            "success_criteria": ["checksum evidence"],
            "constraints": ["migration evidence"],
            "subgoals": ["checksum evidence"],
            "evidence_needs": ["checksum evidence"],
        }
        proposal["coverage"] = {"facets": ["checksum evidence"], "unresolved_gaps": []}

        result = ci.validate_semantic_proposal(proposal, preflight)

        self.assertIn(
            "missing_declared_dependency_parent",
            {item["code"] for item in result["errors"]},
        )

    def test_declared_relationship_semantics_change_all_composition_identities(
        self,
    ) -> None:
        def build_plan(field: str, relationship: str) -> tuple[dict[str, object], dict[str, object]]:
            seed = _node(
                "migration-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#migration-seed",
                (
                    "Migration coordinator uses migration evidence, produces checksum "
                    "handoff, and exits when checksum handoff is ready."
                ),
                **{field: ["checksum-verifier"]},
            )
            verifier = _node(
                "checksum-verifier",
                "skill_definition",
                "skills/checksum-verifier/SKILL.md",
                (
                    "Checksum verifier uses checksum handoff, produces verified checksum "
                    "evidence, and exits when verified checksum evidence is ready."
                ),
            )
            preflight = ci.prepare_composition(
                [seed, verifier],
                "Prepare migration evidence and verify checksum evidence.",
            )
            seed_role = _role(
                preflight,
                "migration-seed",
                "migration coordinator",
                "implementation",
                inputs=["migration evidence"],
                outputs=["checksum handoff"],
                exit_gates=["checksum handoff is ready"],
            )
            verifier_role = _role(
                preflight,
                "checksum-verifier",
                "checksum verifier",
                "verification",
                inputs=["checksum handoff"],
                outputs=["verified checksum evidence"],
                exit_gates=["verified checksum evidence is ready"],
                covers=["verified checksum evidence"],
            )
            proposal = _proposal(
                preflight,
                [seed_role, verifier_role],
                [_edge(preflight, "migration-seed", "checksum-verifier", relationship)],
            )
            proposal["task_model"] = {
                "deliverables": ["verified checksum evidence"],
                "success_criteria": ["verified checksum evidence"],
                "constraints": ["migration evidence"],
                "subgoals": ["checksum handoff"],
                "evidence_needs": ["verified checksum evidence"],
            }
            proposal["coverage"] = {
                "facets": ["checksum evidence"],
                "unresolved_gaps": [],
            }
            return preflight, ci.build_composition_plan(proposal, preflight)

        after_preflight, after_plan = build_plan("chains_after", "enables")
        before_preflight, before_plan = build_plan("chains_before", "precedes")

        self.assertNotEqual(after_preflight["preflight_id"], before_preflight["preflight_id"])
        self.assertNotEqual(
            after_plan["provenance"]["graph_digest"],
            before_plan["provenance"]["graph_digest"],
        )
        self.assertNotEqual(
            after_plan["provenance"]["recipe_digest"],
            before_plan["provenance"]["recipe_digest"],
        )
        self.assertNotEqual(
            after_plan["composition_plan_id"],
            before_plan["composition_plan_id"],
        )
        self.assertNotEqual(
            after_plan["phase_capsule_binding"]["composition_plan_digest"],
            before_plan["phase_capsule_binding"]["composition_plan_digest"],
        )

    def test_semantic_proposal_requires_selected_seed_dependency_role(self) -> None:
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            (
                "Migration coordinator uses migration evidence, produces checksum "
                "handoff, and exits when checksum handoff is ready."
            ),
            chains_after=["checksum-verifier"],
            verification_expectations=["Manual checksum review"],
        )
        verifier = _node(
            "checksum-verifier",
            "skill_definition",
            "skills/checksum-verifier/SKILL.md",
            (
                "Checksum verifier uses checksum handoff, produces verified checksum "
                "evidence, and exits when verified checksum evidence is ready."
            ),
        )
        preflight = ci.prepare_composition(
            [seed, verifier],
            "Prepare migration evidence and verify checksum evidence.",
        )
        seed_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["checksum handoff"],
            exit_gates=["checksum handoff is ready"],
        )
        verifier_role = _role(
            preflight,
            "checksum-verifier",
            "checksum verifier",
            "verification",
            inputs=["checksum handoff"],
            outputs=["verified checksum evidence"],
            exit_gates=["verified checksum evidence is ready"],
            covers=["verified checksum evidence"],
        )
        task_model = {
            "deliverables": ["verified checksum evidence"],
            "success_criteria": ["verified checksum evidence"],
            "constraints": ["migration evidence"],
            "subgoals": ["checksum handoff"],
            "evidence_needs": ["verified checksum evidence"],
        }
        partial = _proposal(
            preflight,
            [seed_role],
            [],
            current_phase="implementation",
        )
        partial["task_model"] = task_model
        partial["coverage"] = {"facets": ["checksum evidence"], "unresolved_gaps": []}
        partial_result = ci.validate_semantic_proposal(partial, preflight)

        self.assertFalse(partial_result["valid"])
        self.assertIn(
            "missing_declared_dependency",
            {item["code"] for item in partial_result["errors"]},
        )

        missing_edge = _proposal(
            preflight,
            [seed_role, verifier_role],
            [],
            current_phase="implementation",
        )
        missing_edge["task_model"] = task_model
        missing_edge["coverage"] = {
            "facets": ["checksum evidence"],
            "unresolved_gaps": [],
        }
        self.assertIn(
            "missing_declared_dependency_relationship",
            {
                item["code"]
                for item in ci.validate_semantic_proposal(missing_edge, preflight)["errors"]
            },
        )

        proposal = _proposal(
            preflight,
            [seed_role, verifier_role],
            [_edge(preflight, "migration-seed", "checksum-verifier", "enables")],
            current_phase="implementation",
        )
        proposal["task_model"] = task_model
        proposal["coverage"] = {"facets": ["checksum evidence"], "unresolved_gaps": []}
        result = ci.validate_semantic_proposal(proposal, preflight)
        plan = ci.build_composition_plan(proposal, preflight)

        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(
            plan["scoped_seed_graph_hints"]["declared_dependency_closure"][
                "required_dependency_nodes"
            ][0]["source_node_id"],
            "checksum-verifier",
        )
        self.assertIn(
            "Unbound verification obligation: Manual checksum review",
            plan["composition_diagnostics"]["missing_capabilities"],
        )

    def test_scoped_seed_lifecycle_semantics_enter_the_composition_graph(self) -> None:
        seed = _node(
            "release-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#release-seed",
            (
                "Release coordinator consumes release readiness evidence, "
                "produces a release readiness verification receipt, and exits "
                "when release readiness verification passes."
            ),
            use_when=["Verify release readiness"],
            route_affinity=["release_readiness"],
            do_not_activate_with=["fast-ship"],
            phase_transitions={
                "verification": {
                    "next_phases": ["final"],
                    "activate_skills": [],
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
            inputs=["release readiness evidence"],
            outputs=["release readiness verification receipt"],
            exit_gates=["Release readiness verification passes"],
            covers=["Release readiness verification passes"],
        )
        proposal = _proposal(
            preflight,
            [role],
            [],
            current_phase="verification",
            success_criteria=["Release readiness verification passes"],
        )
        plan = ci.build_composition_plan(proposal, preflight)

        self.assertEqual(hints["typed_edges"], [])
        relations = {
            edge["relation"]
            for edge in plan["scoped_seed_graph_hints"]["typed_edges"]
        }
        self.assertTrue(
            {
                "affinity_for_route",
                "conflicts_with",
                "defines_phase_transition",
                "requires_verification",
                "requires_receipt",
            }.issubset(relations)
        )
        self.assertTrue(
            all(
                edge["citations"]
                for edge in plan["scoped_seed_graph_hints"]["typed_edges"]
            )
        )
        self.assertEqual(
            plan["scoped_seed_graph_hints"]["scoped_seeds"][0]["id"],
            "release-seed",
        )
        self.assertGreater(
            plan["provenance"]["normalized_scoped_seed_relationship_count"],
            0,
        )

    def test_declared_phase_transition_gate_blocks_the_next_selected_stage(self) -> None:
        gate = "Migration artifact is ready for checksum verification."
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator produces a checksum handoff.",
            phase_transitions={
                "implementation": {
                    "next_phases": ["verification"],
                    "activate_skills": ["checksum-verifier"],
                    "verification_gates": [gate],
                }
            },
        )
        verifier = _node(
            "checksum-verifier",
            "skill_definition",
            "skills/checksum-verifier/SKILL.md",
            "Checksum verifier consumes the checksum handoff and produces evidence.",
        )
        preflight = ci.prepare_composition(
            [seed, verifier],
            "Prepare migration evidence and verify checksum evidence.",
        )
        seed_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["checksum handoff"],
            exit_gates=["checksum handoff is ready"],
        )
        verifier_role = _role(
            preflight,
            "checksum-verifier",
            "checksum verifier",
            "verification",
            inputs=["checksum handoff"],
            outputs=["checksum evidence"],
            exit_gates=["checksum evidence is ready"],
            covers=["checksum evidence"],
        )
        proposal = _proposal(
            preflight,
            [seed_role, verifier_role],
            [_edge(preflight, "migration-seed", "checksum-verifier", "enables")],
            current_phase="implementation",
        )
        proposal["task_model"] = {
            "deliverables": ["checksum evidence"],
            "success_criteria": ["checksum evidence"],
            "constraints": ["migration evidence"],
            "subgoals": ["checksum handoff"],
            "evidence_needs": ["checksum evidence"],
        }
        proposal["coverage"] = {"facets": ["checksum evidence"], "unresolved_gaps": []}

        plan = ci.build_composition_plan(proposal, preflight)
        verification_stage = next(
            stage
            for stage in plan["ordered_stages"]
            if stage["phase"] == "verification"
        )
        self.assertIn(gate, verification_stage["entry_conditions"])
        gate_record = next(
            item for item in composition_gate_catalog(plan) if item["name"] == gate
        )

        runtime = advance_composition_runtime(
            plan,
            {"requested_phase": "verification"},
        )
        self.assertFalse(runtime["phase_advance"]["allowed"])
        self.assertIn(
            gate_record["gate_id"], runtime["phase_advance"]["pending_gate_ids"]
        )

    def test_declared_phase_gate_requires_its_selected_origin_phase(self) -> None:
        gate = "Verification evidence authorizes the final release stage."
        seed = _node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator produces a checksum handoff.",
            phase_transitions={
                "verification": {
                    "next_phases": ["final"],
                    "activate_skills": [],
                    "verification_gates": [gate],
                }
            },
        )
        verifier = _node(
            "checksum-verifier",
            "skill_definition",
            "skills/checksum-verifier/SKILL.md",
            "Checksum verifier produces verification evidence.",
        )
        finalizer = _node(
            "release-finalizer",
            "skill_definition",
            "skills/release-finalizer/SKILL.md",
            "Release finalizer produces final release evidence.",
        )
        preflight = ci.prepare_composition(
            [seed, verifier, finalizer],
            "Prepare migration evidence, verify checksum evidence, and finalize release evidence.",
        )
        seed_role = _role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["checksum handoff"],
            exit_gates=["checksum handoff is ready"],
        )
        verifier_role = _role(
            preflight,
            "checksum-verifier",
            "checksum verifier",
            "verification",
            inputs=["checksum handoff"],
            outputs=["verification evidence"],
            exit_gates=["verification evidence is ready"],
        )
        finalizer_role = _role(
            preflight,
            "release-finalizer",
            "release finalizer",
            "final",
            inputs=["verification evidence"],
            outputs=["final release evidence"],
            exit_gates=["final release evidence is ready"],
            covers=["final release evidence"],
        )
        proposal = _proposal(
            preflight,
            [seed_role, verifier_role, finalizer_role],
            [
                _edge(preflight, "migration-seed", "checksum-verifier", "enables"),
                _edge(preflight, "checksum-verifier", "release-finalizer", "enables"),
            ],
            current_phase="implementation",
        )
        proposal["task_model"] = {
            "deliverables": ["final release evidence"],
            "success_criteria": ["final release evidence"],
            "constraints": [],
            "subgoals": ["checksum handoff", "verification evidence"],
            "evidence_needs": ["final release evidence"],
        }
        proposal["coverage"] = {
            "facets": ["final release evidence"],
            "unresolved_gaps": [],
        }

        validation = ci.validate_semantic_proposal(proposal, preflight)
        self.assertTrue(validation["valid"], validation["errors"])
        plan = ci.build_composition_plan(proposal, preflight)
        final_stage = next(
            stage for stage in plan["ordered_stages"] if stage["phase"] == "final"
        )

        self.assertNotIn(gate, final_stage["entry_conditions"])
        self.assertIn(
            "Declared phase gate for migration-seed has no selected verification stage.",
            plan["composition_diagnostics"]["phase_transition_gate_warnings"],
        )

if __name__ == "__main__":
    unittest.main()
