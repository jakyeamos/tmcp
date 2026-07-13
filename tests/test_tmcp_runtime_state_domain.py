from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.domain.runtime_state as runtime_state
from tmcp_runtime.domain.routes import derive_task_identity
from tmcp_runtime.domain.runtime_state import derive_runtime_state


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

    def test_context_only_state_is_data_only_and_does_not_use_cache_warnings(self) -> None:
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

    def test_redirect_cache_and_proposal_warnings_keep_their_contract_order(self) -> None:
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

    def test_previous_packet_identity_is_used_when_no_explicit_identity_is_given(self) -> None:
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
