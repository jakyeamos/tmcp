from __future__ import annotations

import copy
import unittest
from typing import Any

from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import content_digest_for
from tmcp_runtime.domain.host_composition_provenance import (
    validate_host_composition_lineage,
)
from tests.test_tmcp_composition_integration import CompositionIntegrationTests
from tests.tmcp_runtime_provenance_test_support import RuntimeProvenanceTestSupport
from tmcp_runtime.services.compose import (
    compose_packet_from_source_nodes,
    prepare_composition_from_source_nodes,
)
from tmcp_runtime.services.host_composition import (
    HOST_COMPOSITION_INTAKE_SCHEMA,
    HostCompositionIntake,
    compose_host_composition,
    prepare_host_composition,
    run_host_composition,
)


class HostCompositionTests(RuntimeProvenanceTestSupport, unittest.TestCase):
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

    def _host_packet(self) -> tuple[HostCompositionIntake, dict[str, Any]]:
        intake = prepare_host_composition(self.arguments, source_nodes=self.nodes)
        return intake, compose_host_composition(
            intake,
            self._proposal(intake.host_input()["preflight"]),
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
        lineage = packet["host_composition"]
        origin = lineage["origin"]
        self.assertEqual(lineage["schema"], "tmcp-host-composition-lineage-v0.1")
        self.assertEqual(
            origin,
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
        self.assertEqual(lineage["origin_digest"], stable_digest(origin))
        self.assertEqual(lineage["runtime_snapshot_status"], "initial_frozen_snapshot")
        self.assertEqual(lineage["current_preflight_id"], intake.preflight_id)
        self.assertFalse(lineage["inherited_origin"])
        self.assertEqual(
            packet["receipt_template"]["host_composition_provenance"],
            {
                "schema": "tmcp-host-composition-receipt-provenance-v0.1",
                "origin_digest": lineage["origin_digest"],
                "origin_preflight_id": intake.preflight_id,
                "runtime_snapshot_status": "initial_frozen_snapshot",
                "runtime_preflight_id": intake.preflight_id,
                "inherited_origin": False,
                "trust": "advisory_untrusted",
            },
        )

    def test_runner_calls_the_host_once_with_bounded_input(self) -> None:
        inputs: list[dict[str, Any]] = []

        def propose_semantics(host_input: dict[str, Any]) -> dict[str, Any]:
            inputs.append(copy.deepcopy(host_input))
            return self._proposal(host_input["preflight"])

        packet = run_host_composition(
            self.arguments,
            source_nodes=self.nodes,
            propose_semantics=propose_semantics,
        )

        self.assertTrue(packet["ok"])
        self.assertEqual(len(inputs), 1)
        self.assertNotIn("_source_nodes", inputs[0])
        self.assertNotIn(self.nodes[0]["path"], str(inputs[0]))
        self.assertEqual(
            packet["composition_plan"]["preflight_id"],
            inputs[0]["preflight_id"],
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
        self.assertEqual(
            packet["host_composition"]["origin"]["automatic_tool_execution"],
            False,
        )
        self.assertEqual(
            packet["host_composition"]["origin"]["receipt_persistence"],
            "not_performed",
        )

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

    def test_runtime_recompile_revalidates_and_retains_host_origin(self) -> None:
        _intake, initial = self._host_packet()
        service = self._runtime_service(self.nodes)
        arguments = self._runtime_arguments(self.harness, initial)

        result = service.recompile(arguments, service.build_state(arguments))

        self.assertTrue(result["ok"])
        lineage = result["packet"]["host_composition"]
        self.assertEqual(lineage["origin"], initial["host_composition"]["origin"])
        self.assertEqual(
            lineage["origin_digest"], initial["host_composition"]["origin_digest"]
        )
        self.assertEqual(
            lineage["runtime_snapshot_status"], "runtime_capsule_revalidated"
        )
        self.assertTrue(lineage["inherited_origin"])
        self.assertEqual(
            lineage["current_preflight_id"],
            result["packet"]["composition_plan"]["preflight_id"],
        )
        self.assertEqual(
            result["packet"]["receipt_template"]["host_composition_provenance"]
            ["runtime_snapshot_status"],
            "runtime_capsule_revalidated",
        )
        self.assertEqual(
            result["packet_diff"]["host_composition"]["origin"]["status"],
            "preserved",
        )

    def test_runtime_recompile_retains_host_origin_when_cited_source_changes(self) -> None:
        _intake, initial = self._host_packet()
        changed_nodes = copy.deepcopy(self.nodes)
        replacement = "Implement a changed and independently verified plan."
        for node in changed_nodes:
            if node["id"] == "implement":
                node["signal_excerpt"] = replacement
                node["content_digest"] = content_digest_for(replacement)
                break
        service = self._runtime_service(changed_nodes)
        arguments = self._runtime_arguments(self.harness, initial)

        result = service.recompile(arguments, service.build_state(arguments))

        self.assertFalse(result["ok"])
        self.assertIsNone(result["packet"]["composition_plan"])
        self.assertEqual(
            result["packet"]["composition_plan_status"], "stale_source_provenance"
        )
        lineage = result["packet"]["host_composition"]
        self.assertEqual(lineage["origin"], initial["host_composition"]["origin"])
        self.assertEqual(
            lineage["origin_digest"], initial["host_composition"]["origin_digest"]
        )
        self.assertEqual(
            lineage["runtime_snapshot_status"], "runtime_capsule_rejected"
        )
        self.assertTrue(lineage["inherited_origin"])
        self.assertEqual(
            result["packet_diff"]["host_composition"]["runtime_snapshot_status"],
            {
                "previous": "initial_frozen_snapshot",
                "current": "runtime_capsule_rejected",
            },
        )

    def test_fresh_semantic_recompile_retains_host_origin_as_history(self) -> None:
        _intake, initial = self._host_packet()
        fresh_preflight = prepare_composition_from_source_nodes(
            self.arguments,
            source_nodes=self.nodes,
        )
        service = self._runtime_service(self.nodes)
        arguments = {
            **self._runtime_arguments(self.harness, initial),
            "semantic_proposal": self._proposal(fresh_preflight),
        }

        result = service.recompile(arguments, service.build_state(arguments))

        self.assertTrue(result["ok"])
        lineage = result["packet"]["host_composition"]
        self.assertEqual(lineage["origin"], initial["host_composition"]["origin"])
        self.assertEqual(
            lineage["origin_digest"], initial["host_composition"]["origin_digest"]
        )
        self.assertEqual(
            lineage["runtime_snapshot_status"], "fresh_semantic_composition"
        )
        self.assertTrue(lineage["inherited_origin"])
        self.assertEqual(
            lineage["current_preflight_id"],
            result["packet"]["composition_plan"]["preflight_id"],
        )

    def test_changed_objective_fresh_recompile_keeps_host_history_for_next_runtime(
        self,
    ) -> None:
        _intake, initial = self._host_packet()
        changed_objective = "Research, implement, and verify a materially different product change"
        fresh_arguments = {**self.arguments, "objective": changed_objective}
        fresh_preflight = prepare_composition_from_source_nodes(
            fresh_arguments,
            source_nodes=self.nodes,
        )
        service = self._runtime_service(self.nodes)
        fresh_runtime_arguments = {
            **self._runtime_arguments(self.harness, initial),
            "objective": changed_objective,
            "semantic_proposal": self._proposal(fresh_preflight),
        }

        fresh = service.recompile(
            fresh_runtime_arguments,
            service.build_state(fresh_runtime_arguments),
        )
        self.assertTrue(fresh["ok"])
        self.assertEqual(
            fresh["packet"]["host_composition"]["runtime_snapshot_status"],
            "fresh_semantic_composition",
        )

        next_runtime_arguments = {
            **self._runtime_arguments(self.harness, fresh["packet"]),
            "objective": changed_objective,
        }
        next_result = service.recompile(
            next_runtime_arguments,
            service.build_state(next_runtime_arguments),
        )

        self.assertTrue(next_result["ok"])
        lineage = next_result["packet"]["host_composition"]
        self.assertEqual(lineage["origin"], initial["host_composition"]["origin"])
        self.assertEqual(
            lineage["runtime_snapshot_status"], "runtime_capsule_revalidated"
        )

    def test_unbound_host_origin_is_omitted_during_runtime_recompile(self) -> None:
        _intake, initial = self._host_packet()
        forged = copy.deepcopy(initial)
        origin = forged["host_composition"]["origin"]
        origin["preflight_id"] = "forged-preflight"
        forged["host_composition"]["origin_digest"] = stable_digest(origin)
        service = self._runtime_service(self.nodes)
        arguments = self._runtime_arguments(self.harness, forged)

        result = service.recompile(arguments, service.build_state(arguments))

        self.assertTrue(result["ok"])
        self.assertNotIn("host_composition", result["packet"])
        self.assertNotIn(
            "host_composition_provenance", result["packet"]["receipt_template"]
        )
        self.assertEqual(
            result["packet"]["composition_diagnostics"]["host_composition_provenance"]
            ["status"],
            "untrusted_or_unbound_origin_omitted",
        )
        self.assertEqual(
            result["packet_diff"]["host_composition"]["origin"]["status"],
            "untrusted_or_unbound_origin_omitted",
        )

    def test_revalidated_host_lineage_requires_current_plan_binding(self) -> None:
        _intake, packet = self._host_packet()
        malformed = copy.deepcopy(packet["host_composition"])
        malformed["runtime_snapshot_status"] = "runtime_capsule_revalidated"
        malformed["current_preflight_id"] = None
        malformed["inherited_origin"] = True

        with self.assertRaisesRegex(ValueError, "current_preflight_id"):
            validate_host_composition_lineage(
                malformed,
                composition_plan=packet["composition_plan"],
            )


if __name__ == "__main__":
    unittest.main()
