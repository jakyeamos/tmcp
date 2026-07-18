"""Shared unittest harness for provenance-guard tests, with no test cases."""

from __future__ import annotations

import copy
from typing import Any

from tmcp_runtime.services.compose import (
    compose_packet_from_source_nodes,
    prepare_composition_from_source_nodes,
)
from tmcp_runtime.services.runtime import RuntimeService, RuntimeServiceContext
from tests import test_tmcp_composition_integration as composition_integration


class RuntimeProvenanceTestSupport:
    @staticmethod
    def _runtime_service(nodes: list[dict[str, Any]]) -> RuntimeService:
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

        composition_callbacks = {
            "compose_packet_from_source_nodes": compose,
            "prepare_composition_from_source_nodes": (
                lambda arguments, source_nodes: prepare_composition_from_source_nodes(
                    arguments,
                    source_nodes=source_nodes,
                )
            ),
        }
        return RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: True,
                load_source_nodes=lambda arguments: copy.deepcopy(nodes),
                load_cache_warnings=lambda cache_policy: [],
                **composition_callbacks,
            )
        )

    @staticmethod
    def _semantic_packet(
        *, phase: str = "implementation"
    ) -> tuple[
        composition_integration.CompositionIntegrationTests,
        list[dict[str, Any]],
        dict[str, Any],
    ]:
        harness = composition_integration.CompositionIntegrationTests()
        harness.setUp()
        nodes = copy.deepcopy(harness.nodes)
        arguments = {**harness.arguments, "phase": phase}
        preflight = prepare_composition_from_source_nodes(
            arguments,
            source_nodes=nodes,
        )
        harness.nodes = nodes
        proposal = harness._proposal(preflight)
        proposal["current_phase"] = phase
        packet = harness._compose(
            {
                **arguments,
                "semantic_proposal": proposal,
            }
        )
        return harness, nodes, packet

    @staticmethod
    def _runtime_arguments(
        harness: composition_integration.CompositionIntegrationTests,
        previous_packet: dict[str, Any],
        *,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        root = project_path or harness.arguments["project_path"]
        return {
            "objective": harness.arguments["objective"],
            "project_path": root,
            "source_path": root,
            "current_phase": "implementation",
            "previous_packet": previous_packet,
        }

    @staticmethod
    def _verification_transition_evidence(plan: dict[str, Any]) -> dict[str, Any]:
        from tmcp_runtime.domain.composition_runtime import composition_gate_catalog

        contract = next(
            item
            for item in plan["handoff_contracts"]
            if item["consumer_node_id"] == "verify"
        )
        implementation_stage = next(
            item["stage_id"]
            for item in plan["ordered_stages"]
            if item["phase"] == "implementation"
        )
        verification_stage = next(
            item["stage_id"]
            for item in plan["ordered_stages"]
            if item["phase"] == "verification"
        )
        return {
            "requested_phase": "verification",
            "gate_results": [
                {"gate": item["name"], "status": "passed"}
                for item in composition_gate_catalog(plan)
                if (
                    item["kind"] == "exit"
                    and item["owner_stage_id"] == implementation_stage
                )
                or (
                    item["kind"] == "entry"
                    and item["owner_stage_id"] == verification_stage
                )
            ],
            "handoff_results": [
                {
                    "handoff_id": contract["handoff_id"],
                    "producer_node_id": contract["producer_node_id"],
                    "consumer_node_id": contract["consumer_node_id"],
                    "status": "available",
                    "consumed_inputs": contract["required_inputs"],
                    "produced_outputs": contract["produced_outputs"],
                    "evidence_refs": ["docs/implementation.md"],
                }
            ],
        }
