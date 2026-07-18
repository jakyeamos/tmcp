from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.domain.runtime_state as runtime_state
from tmcp_runtime.domain.routes import derive_task_identity
from tmcp_runtime.domain.runtime_state import derive_runtime_state
from tests.test_tmcp_composition_runtime import _plan as composition_runtime_plan


class TmcpRuntimeStateDomainTests(unittest.TestCase):
    @staticmethod
    def _family_nodes() -> list[dict[str, object]]:
        return [
            {
                "source_type": "scoped_packet_seed",
                "seed_id": "runtime_seed",
                "title": "Runtime seed",
                "route_affinity": ["frontend_implementation"],
                "source_references": ["skills/runtime/SKILL.md"],
                "objective_patterns": ["onboarding"],
                "chains_after": ["implementation"],
                "chains_before": [],
                "do_not_activate_with": [],
                "phase_transitions": {
                    "runtime": {
                        "next_phases": ["implementation"],
                        "activate_skills": ["implementation"],
                        "verification_gates": ["Inspect the current implementation."],
                    }
                },
            },
            {
                "source_type": "skill_definition",
                "relative_path": "skills/implementation/SKILL.md",
                "routing_metadata": {},
                "signal_excerpt": "Use existing components before implementation.",
            },
        ]

    @staticmethod
    def _runtime_plan() -> dict[str, object]:
        plan = composition_runtime_plan()
        plan["current_phase"] = "runtime"
        plan["ordered_stages"][0]["phase"] = "runtime"
        return plan

    def test_context_only_state_is_data_only_and_does_not_use_cache_warnings(
        self,
    ) -> None:
        arguments = {
            "objective": "Debug the failing onboarding page",
            "project_path": "/project",
            "current_phase": "runtime",
            "files_changed": ["app/page.tsx"],
            "failures": ["test failed"],
            "cache_policy": "none",
        }
        original_arguments = copy.deepcopy(arguments)
        source_nodes: list[dict[str, object]] = []

        state = derive_runtime_state(
            arguments,
            source_nodes=source_nodes,
            cache_warnings=["must not appear without cache opt-in"],
        )

        self.assertEqual(arguments, original_arguments)
        self.assertEqual(source_nodes, [])
        self.assertEqual(state["project_path"], "/project")
        self.assertEqual(state["cache_policy"], "none")
        self.assertIn("debugging-regression", state["packet_delta"]["activated_atoms"])
        self.assertNotIn("must not appear", " ".join(state["warnings"]))

    def test_injected_family_nodes_drive_the_runtime_transition(self) -> None:
        state = derive_runtime_state(
            {
                "objective": "Use runtime to implement onboarding",
                "current_phase": "runtime",
                "cache_policy": "none",
            },
            source_nodes=self._family_nodes(),
            cache_warnings=[],
        )

        packet_delta = state["packet_delta"]
        self.assertEqual(state["suggested_phase"], "implementation")
        self.assertEqual(packet_delta["suggested_skills"], ["implementation"])
        self.assertIn("skill:implementation", packet_delta["activated_atoms"])
        self.assertIn(
            "skills/implementation/SKILL.md",
            packet_delta["newly_required_reads"],
        )

    def test_redirect_cache_and_proposal_warnings_keep_their_contract_order(
        self,
    ) -> None:
        state = derive_runtime_state(
            {
                "objective": "Implement onboarding",
                "latest_user_message": "Actually, redesign the landing page instead.",
                "cache_policy": "global",
                "proposed_changes": [
                    {"action": "add_route", "route": "not-a-real-route"}
                ],
            },
            source_nodes=[],
            cache_warnings=["cache warning"],
        )

        self.assertEqual(
            state["warnings"],
            [
                "Latest user message may redirect the objective; stale atoms should be rechecked before use.",
                "cache warning",
                "Rejected proposed change: unknown route `not-a-real-route`.",
            ],
        )
        self.assertIn(
            "previous-objective-specific-atoms",
            state["packet_delta"]["stale_atoms"],
        )
        self.assertEqual(state["validated_changes"], [])

    def test_explicit_user_redirect_is_preserved_and_drives_identity_reason(
        self,
    ) -> None:
        previous_identity = derive_task_identity("Research onboarding requirements")
        redirect = {"reason": "Switch to the billing migration."}

        state = derive_runtime_state(
            {
                "objective": "Implement the billing migration",
                "previous_packet": {"task_identity": previous_identity},
                "user_redirect": redirect,
                "cache_policy": "none",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        self.assertEqual(state["runtime_evidence"]["user_redirect"], redirect)
        self.assertIn(
            "previous-objective-specific-atoms", state["packet_delta"]["stale_atoms"]
        )
        self.assertEqual(state["task_identity_delta"]["reason"], "user_redirect")

    def test_capsule_bound_explicit_redirect_requires_fresh_composition(
        self,
    ) -> None:
        plan = self._runtime_plan()
        plan["phase_capsule_binding"] = {
            "schema": "tmcp-phase-capsule-binding-v0.1"
        }
        plan["runtime_capsule"] = {
            "schema": "tmcp-composition-runtime-capsule-v0.1"
        }

        state = derive_runtime_state(
            {
                "objective": "Debug the failing login test",
                "previous_packet": {
                    "composition_plan": plan,
                    "task_identity": derive_task_identity(
                        "Debug the failing login test"
                    ),
                },
                "user_redirect": {"reason": "Switch to the billing migration."},
                "cache_policy": "none",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        policy = state["composition_recompile_policy"]
        self.assertTrue(policy["protected_plan"])
        self.assertTrue(policy["runtime_capsule_present"])
        self.assertTrue(policy["requires_fresh_composition"])
        self.assertEqual(policy["reason"], "user_redirect")

    def test_bare_different_message_does_not_force_fresh_composition(self) -> None:
        plan = self._runtime_plan()
        plan["phase_capsule_binding"] = {
            "schema": "tmcp-phase-capsule-binding-v0.1"
        }
        plan["runtime_capsule"] = {
            "schema": "tmcp-composition-runtime-capsule-v0.1"
        }

        state = derive_runtime_state(
            {
                "objective": "Debug the failing login test",
                "latest_user_message": (
                    "Please run different tests for the login failure."
                ),
                "previous_packet": {
                    "composition_plan": plan,
                    "task_identity": derive_task_identity(
                        "Debug the failing login test"
                    ),
                },
                "cache_policy": "none",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        policy = state["composition_recompile_policy"]
        self.assertTrue(policy["protected_plan"])
        self.assertFalse(policy["requires_fresh_composition"])
        self.assertEqual(policy["reason"], "")

    def test_unknown_cache_policy_discards_cache_warnings(self) -> None:
        state = derive_runtime_state(
            {
                "objective": "Implement onboarding",
                "cache_policy": "globla",
            },
            source_nodes=[],
            cache_warnings=["untrusted global cache warning"],
        )

        self.assertEqual(state["cache_policy"], "none")
        self.assertNotIn("untrusted global cache warning", state["warnings"])

    def test_previous_packet_identity_is_used_when_no_explicit_identity_is_given(
        self,
    ) -> None:
        previous_identity = derive_task_identity("Debug the failing login test")
        state = derive_runtime_state(
            {
                "objective": "Redesign the login page",
                "previous_packet": {"task_identity": previous_identity},
                "cache_policy": "none",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        delta = state["task_identity_delta"]
        self.assertIsNotNone(delta)
        assert isinstance(delta, dict)
        self.assertEqual(delta["previous"], previous_identity)
        self.assertEqual(delta["reason"], "runtime_context_changed")

    def test_legacy_unbound_plan_stays_inert_despite_runtime_evidence(self) -> None:
        state = derive_runtime_state(
            {
                "objective": "Use runtime to implement onboarding",
                "current_phase": "runtime",
                "previous_packet": {"composition_plan": self._runtime_plan()},
                "files_read": ["docs/research.md"],
                "files_changed": ["app/page.tsx"],
                "commands_run": ["python3 -m unittest"],
                "verification_results": ["looks good"],
                "failures": ["visual check still pending"],
                "browser_evidence": ["screenshot captured"],
                "latest_user_message": "Continue with the implementation.",
                "user_overrides": ["Keep the current labels"],
                "cache_policy": "none",
            },
            source_nodes=self._family_nodes(),
            cache_warnings=[],
        )

        self.assertIsNone(state["composition_runtime"])
        self.assertTrue(
            state["composition_recompile_policy"]
            ["legacy_unbound_graph_requires_fresh_composition"]
        )
        self.assertIn(
            "An unbound legacy composition graph requires a fresh semantic proposal.",
            state["warnings"],
        )
        # Family routing can still recommend a bounded next skill, but it must
        # not replay the unbound semantic graph or accept its runtime evidence.
        self.assertEqual(state["suggested_phase"], "implementation")
        self.assertEqual(state["packet_delta"]["suggested_skills"], ["implementation"])
        self.assertEqual(
            state["runtime_evidence"]["files_read"], ["docs/research.md"]
        )

    def test_legacy_unbound_plan_cannot_advance_from_structured_gate_results(
        self,
    ) -> None:
        state = derive_runtime_state(
            {
                "objective": "Use runtime to implement onboarding",
                "current_phase": "runtime",
                "previous_packet": {"composition_plan": self._runtime_plan()},
                "verification_results": [
                    {"gate": "Research brief approved", "status": "passed"}
                ],
                "gate_results": [
                    {"gate": "Research handoff available", "status": "passed"}
                ],
                "cache_policy": "none",
            },
            source_nodes=self._family_nodes(),
            cache_warnings=[],
        )

        self.assertIsNone(state["composition_runtime"])
        self.assertEqual(state["phase"], "runtime")
        self.assertTrue(
            state["composition_recompile_policy"]
            ["legacy_unbound_graph_requires_fresh_composition"]
        )
        self.assertEqual(state["suggested_phase"], "implementation")
        self.assertEqual(state["packet_delta"]["suggested_skills"], ["implementation"])

    def test_legacy_unbound_plan_does_not_rewrite_reported_phase(self) -> None:
        state = derive_runtime_state(
            {
                "objective": "Implement onboarding",
                "current_phase": "implementation",
                "previous_packet": {"composition_plan": self._runtime_plan()},
                "gate_results": [
                    {"gate": "Research brief approved", "status": "passed"},
                    {"gate": "Research handoff available", "status": "passed"},
                ],
                "cache_policy": "none",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        self.assertEqual(state["phase"], "implementation")
        self.assertEqual(state["runtime_evidence"]["requested_phase"], "")
        self.assertIsNone(state["composition_runtime"])
        self.assertTrue(
            state["composition_recompile_policy"]
            ["legacy_unbound_graph_requires_fresh_composition"]
        )

    def test_fresh_composition_does_not_inherit_legacy_plan_gates(self) -> None:
        state = derive_runtime_state(
            {
                "objective": "Verify onboarding",
                "current_phase": "runtime",
                "previous_packet": {"composition_plan": self._runtime_plan()},
                "semantic_proposal": {
                    "schema": "tmcp-semantic-proposal-v0.1",
                    "current_phase": "verification",
                },
                "cache_policy": "none",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        self.assertTrue(state["semantic_proposal_supplied"])
        self.assertIsNone(state["composition_runtime"])
        self.assertFalse(
            state["composition_recompile_policy"]
            ["legacy_unbound_graph_requires_fresh_composition"]
        )
        self.assertEqual(state["runtime_evidence"]["requested_phase"], "verification")

    def test_explicit_project_recipe_does_not_replay_legacy_plan(self) -> None:
        state = derive_runtime_state(
            {
                "objective": "Implement onboarding",
                "previous_packet": {"composition_plan": self._runtime_plan()},
                "project_recipe_id": "reviewed-onboarding",
                "cache_policy": "project",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        self.assertTrue(state["semantic_proposal_supplied"])
        self.assertIsNone(state["composition_runtime"])
        self.assertFalse(
            state["composition_recompile_policy"]
            ["legacy_unbound_graph_requires_fresh_composition"]
        )

    def test_runtime_state_domain_has_no_adapter_or_io_imports(self) -> None:
        source_path = Path(inspect.getfile(runtime_state))
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
            "os",
            "pathlib",
            "subprocess",
            "scripts",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "tmcp_runtime.services",
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
