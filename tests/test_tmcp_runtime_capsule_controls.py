from __future__ import annotations

import copy
import unittest
from typing import Any

from tmcp_runtime.services.compose import (
    compose_packet_from_source_nodes,
    prepare_composition_from_source_nodes,
)
from tmcp_runtime.services.runtime import RuntimeService, RuntimeServiceContext
from tests import test_tmcp_composition_integration as composition_integration


class RuntimeCapsuleControlTests(unittest.TestCase):
    def setUp(self) -> None:
        harness = composition_integration.CompositionIntegrationTests()
        harness.setUp()
        self.harness = harness
        self.controls = {
            "candidate_limit": 6,
            "max_excerpt_chars": 800,
            "max_total_chars": 6000,
            "max_total_tokens": 1500,
            "include_all_active_source_slices": True,
            "explicitly_scoped_paths": [],
        }
        self.arguments = {**harness.arguments, **self.controls}
        self.nodes = copy.deepcopy(harness.nodes)
        preflight = prepare_composition_from_source_nodes(
            self.arguments,
            source_nodes=self.nodes,
        )
        harness.nodes = self.nodes
        self.packet = harness._compose(
            {
                **self.arguments,
                "semantic_proposal": harness._proposal(preflight),
            }
        )
        self.plan = copy.deepcopy(self.packet["composition_plan"])

    def _service(self, prepared: list[dict[str, Any]]) -> RuntimeService:
        def prepare(
            arguments: dict[str, Any], source_nodes: list[dict[str, Any]]
        ) -> dict[str, Any]:
            prepared.append(dict(arguments))
            return prepare_composition_from_source_nodes(
                arguments,
                source_nodes=source_nodes,
            )

        def compose(
            arguments: dict[str, Any],
            source_nodes: list[dict[str, Any]],
            prepared_composition: dict[str, Any] | None,
        ) -> dict[str, Any]:
            return compose_packet_from_source_nodes(
                arguments,
                source_nodes=source_nodes,
                global_graphs=[],
                receipts=[],
                cache_warnings=[],
                cache_home="[REDACTED:path]",
                prepared_composition=prepared_composition,
            )

        return RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: True,
                load_source_nodes=lambda arguments: copy.deepcopy(self.nodes),
                load_cache_warnings=lambda cache_policy: [],
                compose_packet_from_source_nodes=compose,
                prepare_composition_from_source_nodes=prepare,
            )
        )

    def _runtime_arguments(self, **overrides: object) -> dict[str, Any]:
        return {
            "objective": self.arguments["objective"],
            "project_path": self.arguments["project_path"],
            "source_path": self.arguments["project_path"],
            "current_phase": "implementation",
            "previous_packet": copy.deepcopy(self.packet),
            **overrides,
        }

    def test_omitted_controls_rehydrate_from_closed_capsule(self) -> None:
        prepared: list[dict[str, Any]] = []
        service = self._service(prepared)
        runtime_arguments = self._runtime_arguments()
        state = service.build_state(runtime_arguments)

        result = service.recompile(runtime_arguments, state)

        self.assertEqual(len(prepared), 1)
        for field, value in self.controls.items():
            self.assertEqual(prepared[0][field], value)
        packet = result["packet"]
        self.assertEqual(
            packet["composition_plan"]["composition_plan_id"],
            self.plan["composition_plan_id"],
        )
        self.assertTrue(packet["composition_diagnostics"]["runtime_capsule_validation"]["accepted"])

    def test_explicit_control_change_does_not_silently_reuse_the_old_plan(self) -> None:
        prepared: list[dict[str, Any]] = []
        service = self._service(prepared)
        runtime_arguments = self._runtime_arguments(candidate_limit=7)
        state = service.build_state(runtime_arguments)

        result = service.recompile(runtime_arguments, state)

        self.assertEqual(prepared[0]["candidate_limit"], 7)
        packet = result["packet"]
        self.assertIsNone(packet["composition_plan"])
        self.assertEqual(packet["composition_plan_status"], "runtime_capsule_invalid")
        self.assertEqual(
            packet["composition_diagnostics"]["runtime_capsule_validation"]
            ["required_action"],
            "Prepare current sources and submit a fresh semantic proposal.",
        )


if __name__ == "__main__":
    unittest.main()
