from __future__ import annotations

import copy
import unittest
from typing import Any

from tests.test_tmcp_composition_integration import CompositionIntegrationTests
from tmcp_runtime.services.compose import (
    compose_packet_from_source_nodes,
    prepare_composition_from_source_nodes,
)
from tmcp_runtime.services.host_composition import (
    HOST_COMPOSITION_INTAKE_SCHEMA,
    compose_host_composition,
    prepare_host_composition,
)


class HostCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        harness = CompositionIntegrationTests()
        harness.setUp()
        self.harness = harness
        self.arguments = copy.deepcopy(harness.arguments)
        self.nodes = copy.deepcopy(harness.nodes)

    def _proposal(self, preflight: dict[str, Any]) -> dict[str, Any]:
        self.harness.nodes = copy.deepcopy(self.nodes)
        return self.harness._proposal(preflight)

    def _direct_compose(
        self,
        arguments: dict[str, Any],
        *,
        prepared_composition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return compose_packet_from_source_nodes(
            arguments,
            source_nodes=self.nodes,
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
            prepared_composition=prepared_composition,
        )

    def test_host_intake_reuses_one_exact_snapshot_for_prepare_and_compose(self) -> None:
        intake = prepare_host_composition(self.arguments, source_nodes=self.nodes)
        host_input = intake.host_input()
        packet = compose_host_composition(
            intake,
            self._proposal(host_input["preflight"]),
        )

        self.assertTrue(packet["ok"])
        self.assertEqual(
            packet["composition_plan"]["preflight_id"], intake.preflight_id
        )
        self.assertEqual(packet["global_cache"]["cache_policy"], "none")
        self.assertEqual(
            packet["host_composition"],
            {
                "schema": HOST_COMPOSITION_INTAKE_SCHEMA,
                "preflight_id": intake.preflight_id,
                "preflight_digest": intake.preflight_digest,
                "source_snapshot_digest": intake.source_snapshot_digest,
                "request_digest": intake.request_digest,
                "task_identity_digest": intake.task_identity_digest,
                "reused_snapshot": True,
                "automatic_tool_execution": False,
                "receipt_persistence": "not_performed",
            },
        )

    def test_host_input_is_bounded_and_mutating_its_copy_cannot_change_intake(self) -> None:
        intake = prepare_host_composition(self.arguments, source_nodes=self.nodes)
        host_input = intake.host_input()
        proposal = self._proposal(host_input["preflight"])
        host_input["preflight"]["objective"] = "Tampered host copy"

        packet = compose_host_composition(intake, proposal)

        self.assertTrue(packet["ok"])
        self.assertNotIn("_source_nodes", host_input)
        self.assertNotIn(self.nodes[0]["path"], str(host_input))
        self.assertEqual(
            packet["composition_plan"]["preflight_id"], intake.preflight_id
        )

    def test_host_intake_rejects_cache_sessions_recipes_and_receipt_writes(self) -> None:
        rejected_arguments = (
            {"cache_policy": "global"},
            {"session_id": "run-1"},
            {"project_recipe_id": "reviewed-recipe"},
            {"record_receipt": True},
            {"write_artifacts": True},
        )

        for rejected in rejected_arguments:
            with self.subTest(rejected=rejected):
                with self.assertRaisesRegex(ValueError, "Host composition intake"):
                    prepare_host_composition(
                        {**self.arguments, **rejected},
                        source_nodes=self.nodes,
                    )

    def test_invalid_host_semantics_remain_inert_without_compatibility_fallback(self) -> None:
        intake = prepare_host_composition(self.arguments, source_nodes=self.nodes)
        proposal = self._proposal(intake.host_input()["preflight"])
        proposal["relationships"][0]["citations"] = ["slice-unknown"]

        packet = compose_host_composition(intake, proposal)

        self.assertFalse(packet["ok"])
        self.assertIsNone(packet["composition_plan"])
        self.assertFalse(packet["semantic_proposal_validation"]["accepted"])
        self.assertEqual(packet["active_instructions"], [])
        self.assertEqual(packet["active_atoms"], [])
        self.assertEqual(packet["host_composition"]["automatic_tool_execution"], False)
        self.assertEqual(packet["host_composition"]["receipt_persistence"], "not_performed")

    def test_tampered_private_intake_snapshot_is_rejected_before_compose(self) -> None:
        intake = prepare_host_composition(self.arguments, source_nodes=self.nodes)
        proposal = self._proposal(intake.host_input()["preflight"])
        intake._source_nodes[0]["signal_excerpt"] = "Changed after preparation."

        with self.assertRaisesRegex(ValueError, "source snapshot changed"):
            compose_host_composition(intake, proposal)

    def test_direct_compose_rejects_preflight_from_another_objective(self) -> None:
        preflight = prepare_composition_from_source_nodes(
            self.arguments,
            source_nodes=self.nodes,
        )
        proposal = self._proposal(preflight)

        with self.assertRaisesRegex(ValueError, "prepared_composition does not match"):
            self._direct_compose(
                {
                    **self.arguments,
                    "objective": "Publish an unrelated release now.",
                    "semantic_proposal": proposal,
                },
                prepared_composition=preflight,
            )

    def test_direct_compose_rejects_preflight_from_a_changed_source_snapshot(self) -> None:
        preflight = prepare_composition_from_source_nodes(
            self.arguments,
            source_nodes=self.nodes,
        )
        proposal = self._proposal(preflight)
        self.nodes[2]["relative_path"] = "skills/implementation-v2/SKILL.md"

        with self.assertRaisesRegex(ValueError, "prepared_composition does not match"):
            self._direct_compose(
                {**self.arguments, "semantic_proposal": proposal},
                prepared_composition=preflight,
            )


if __name__ == "__main__":
    unittest.main()
