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

    def test_composition_runtime_blocks_family_phase_until_named_gates_pass(
        self,
    ) -> None:
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

        runtime = state["composition_runtime"]
        self.assertIsInstance(runtime, dict)
        assert isinstance(runtime, dict)
        self.assertEqual(runtime["current_phase"], "runtime")
        self.assertEqual(
            runtime["phase_advance"]["blocked_reason"],
            "runtime_failures_present",
        )
        self.assertEqual(state["suggested_phase"], "")
        self.assertEqual(state["packet_delta"]["suggested_skills"], [])
        observation_kinds = {
            item["kind"] for item in runtime["runtime_observations"] if "kind" in item
        }
        self.assertTrue(
            {
                "files_read",
                "files_changed",
                "commands_run",
                "failures",
                "browser_evidence",
                "user_overrides",
                "latest_user_message",
            }.issubset(observation_kinds)
        )

    def test_composition_runtime_advances_after_structured_gate_results(self) -> None:
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

        runtime = state["composition_runtime"]
        self.assertIsInstance(runtime, dict)
        assert isinstance(runtime, dict)
        self.assertTrue(runtime["phase_advance"]["allowed"])
        self.assertEqual(runtime["current_phase"], "implementation")
        self.assertEqual(state["suggested_phase"], "implementation")
        self.assertEqual(state["packet_delta"]["suggested_skills"], ["implement"])

    def test_reported_current_phase_is_a_gated_request_when_plan_is_behind(
        self,
    ) -> None:
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

        self.assertEqual(state["phase"], "runtime")
        self.assertEqual(state["runtime_evidence"]["requested_phase"], "implementation")
        self.assertEqual(
            state["composition_runtime"]["current_phase"], "implementation"
        )

    def test_fresh_composition_cannot_bypass_the_previous_plan_gates(self) -> None:
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

        runtime = state["composition_runtime"]
        self.assertTrue(state["semantic_proposal_supplied"])
        self.assertEqual(runtime["current_phase"], "runtime")
        self.assertFalse(runtime["phase_advance"]["allowed"])
        self.assertEqual(
            runtime["phase_advance"]["blocked_reason"],
            "required_gates_not_passed",
        )

    def test_explicit_project_recipe_is_treated_as_fresh_composition(self) -> None:
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
        self.assertIsInstance(state["composition_runtime"], dict)

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
