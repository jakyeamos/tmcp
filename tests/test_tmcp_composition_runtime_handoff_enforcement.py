from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import Any

from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.api.composition_tool_schemas import COMPOSITION_TOOLS
from tmcp_runtime.domain.composition_handoffs import relationship_id_for
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.domain.receipts import build_receipt_template, build_run_receipt


HANDOFF_ID = "handoff-" + "a" * 20
RESEARCH_SLICE = "slice-" + "c" * 20
IMPLEMENT_SLICE = "slice-" + "d" * 20
ROOT = Path(__file__).resolve().parents[1]


def _role(
    node_id: str,
    phase: str,
    inputs: list[str],
    outputs: list[str],
    exit_gate: str,
    activation: str,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "role": f"{node_id} specialist",
        "inputs": inputs,
        "outputs": outputs,
        "phase_affinity": [phase],
        "entry_gates": [],
        "exit_gates": [exit_gate],
        "context_cost": 100,
        "covers": [],
        "citations": [RESEARCH_SLICE if node_id == "research" else IMPLEMENT_SLICE],
        "source_role": "active_skill",
        "activation": activation,
    }


def _plan() -> dict[str, Any]:
    edge = {
        "from": "research",
        "to": "implement",
        "type": "produces",
        "citations": [RESEARCH_SLICE, IMPLEMENT_SLICE],
    }
    contract = {
        "handoff_id": HANDOFF_ID,
        "relationship_id": relationship_id_for(edge),
        "producer_node_id": "research",
        "consumer_node_id": "implement",
        "relationship_type": "produces",
        "required_inputs": ["research brief"],
        "produced_outputs": ["research brief"],
        "producer_exit_gates": ["Research complete"],
        "citations": [RESEARCH_SLICE, IMPLEMENT_SLICE],
        "trust": "advisory_untrusted",
    }
    return {
        "schema": "tmcp-composition-plan-v0.1",
        "composition_plan_id": "composition-runtime-handoff",
        "preflight_id": "preflight-runtime-handoff",
        "current_phase": "discovery",
        "task_model": {
            "deliverables": ["Working change"],
            "success_criteria": ["Focused verification passes"],
            "constraints": [],
            "subgoals": ["Research", "Implement"],
            "evidence_needs": [],
        },
        "skill_roles": [
            _role(
                "research",
                "discovery",
                ["task objective"],
                ["research brief"],
                "Research complete",
                "active",
            ),
            _role(
                "implement",
                "implementation",
                ["research brief"],
                ["working change"],
                "Implementation complete",
                "deferred",
            ),
        ],
        "typed_edges": [edge],
        "handoff_contracts": [contract],
        "ordered_stages": [
            {
                "stage_id": "stage-1",
                "order": 1,
                "phase": "discovery",
                "status": "active",
                "entry_conditions": [],
                "node_ids": ["research"],
                "bridge_instructions": [],
            },
            {
                "stage_id": "stage-2",
                "order": 2,
                "phase": "implementation",
                "status": "deferred",
                "entry_conditions": ["Research handoff ready"],
                "node_ids": ["implement"],
                "bridge_instructions": [],
                "handoff_contracts": [copy.deepcopy(contract)],
            },
        ],
        "coverage": {
            "facets": [],
            "covered_criteria": [],
            "uncovered_criteria": [],
            "unresolved_gaps": [],
        },
        "provenance": {
            "graph_digest": "e" * 32,
            "recipe_digest": "f" * 32,
            "content_digests": ["a" * 64, "b" * 64],
            "normalized_relationship_count": 1,
            "normalized_scoped_seed_relationship_count": 0,
            "identity_policy": "normalized_source_content_and_typed_relationships",
        },
        "composition_diagnostics": {},
        "trust": "advisory_untrusted",
        "instruction_override_policy": "Advisory only.",
    }


def _passing_gates() -> list[dict[str, str]]:
    return [
        {"gate": "Research complete", "status": "passed"},
        {"gate": "Research handoff ready", "status": "passed"},
    ]


def _handoff_result(**changes: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "handoff_id": HANDOFF_ID,
        "producer_node_id": "research",
        "consumer_node_id": "implement",
        "status": "available",
        "consumed_inputs": ["research brief"],
        "produced_outputs": ["research brief"],
        "evidence_refs": ["docs/research-brief.md"],
    }
    result.update(changes)
    return result


class CompositionRuntimeHandoffEnforcementTests(unittest.TestCase):
    def test_named_gates_are_not_sufficient_without_typed_handoff_evidence(
        self,
    ) -> None:
        result = advance_composition_runtime(
            _plan(),
            {"requested_phase": "implementation", "gate_results": _passing_gates()},
        )

        self.assertFalse(result["phase_advance"]["allowed"])
        self.assertEqual(
            result["phase_advance"]["blocked_reason"],
            "required_handoffs_not_available",
        )
        self.assertEqual(result["phase_advance"]["pending_handoff_ids"], [HANDOFF_ID])
        self.assertEqual(result["graph_diff"]["handoffs"]["pending"], [HANDOFF_ID])

    def test_only_exact_typed_contract_evidence_unblocks_the_consumer(self) -> None:
        invalid_results = {
            "wrong id": _handoff_result(handoff_id="handoff-" + "f" * 20),
            "wrong producer": _handoff_result(producer_node_id="other"),
            "wrong consumer": _handoff_result(consumer_node_id="other"),
            "wrong output": _handoff_result(produced_outputs=["implementation plan"]),
            "missing artifact": _handoff_result(evidence_refs=[]),
        }
        for label, handoff in invalid_results.items():
            with self.subTest(label=label):
                result = advance_composition_runtime(
                    _plan(),
                    {
                        "requested_phase": "implementation",
                        "gate_results": _passing_gates(),
                        "handoff_results": [handoff],
                    },
                )
                self.assertFalse(result["phase_advance"]["allowed"])
                self.assertEqual(
                    result["phase_advance"]["blocked_reason"],
                    "required_handoffs_not_available",
                )

        advanced = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "gate_results": _passing_gates(),
                "handoff_results": [_handoff_result()],
            },
        )
        self.assertTrue(advanced["phase_advance"]["allowed"])
        self.assertEqual(advanced["current_phase"], "implementation")
        self.assertEqual(
            advanced["graph_diff"]["handoffs"]["newly_available"], [HANDOFF_ID]
        )
        self.assertEqual(
            advanced["composition_plan"]["runtime_state"]["available_handoff_ids"],
            [HANDOFF_ID],
        )

        carried = advance_composition_runtime(advanced["composition_plan"], {})
        self.assertEqual(
            carried["handoff_evaluation"]["available_handoff_ids"], [HANDOFF_ID]
        )
        self.assertEqual(carried["graph_diff"]["handoffs"]["newly_available"], [])

    def test_reporting_continuation_does_not_bypass_typed_handoff(self) -> None:
        plan = _plan()
        plan["phase_gate_policy"] = "entry_gates_and_handoffs"
        failed_exit = {"gate": "Research complete", "status": "failed"}
        entry_gate = {"gate": "Research handoff ready", "status": "passed"}

        blocked = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "gate_results": [failed_exit, entry_gate],
            },
        )
        self.assertFalse(blocked["phase_advance"]["allowed"])
        self.assertEqual(
            blocked["phase_advance"]["blocked_reason"],
            "required_handoffs_not_available",
        )
        self.assertTrue(blocked["phase_advance"]["nonblocking_failed_gate_ids"])

        advanced = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "gate_results": [failed_exit, entry_gate],
                "handoff_results": [_handoff_result()],
            },
        )
        self.assertTrue(advanced["phase_advance"]["allowed"])
        self.assertTrue(advanced["phase_advance"]["nonblocking_failed_gate_ids"])

    def test_explicit_phase_override_lists_bypassed_handoffs_without_fulfilling_them(
        self,
    ) -> None:
        result = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "gate_results": _passing_gates(),
                "latest_user_message": "I accept the known risk.",
                "user_overrides": [
                    {
                        "action": "advance_phase",
                        "source": "user",
                        "message": "Accept the known risk",
                    }
                ],
            },
        )

        self.assertTrue(result["phase_advance"]["override_applied"])
        self.assertEqual(result["graph_diff"]["handoffs"]["bypassed"], [HANDOFF_ID])
        self.assertEqual(result["handoff_evaluation"]["available_handoff_ids"], [])

    def test_carried_handoff_evidence_is_revalidated_before_reuse(self) -> None:
        advanced = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "gate_results": _passing_gates(),
                "handoff_results": [_handoff_result()],
            },
        )
        tampered = copy.deepcopy(advanced["composition_plan"])
        tampered["runtime_state"]["handoff_results"][0]["consumed_inputs"] = [
            "forged input"
        ]

        result = advance_composition_runtime(tampered, {})

        self.assertEqual(result["handoff_evaluation"]["available_handoff_ids"], [])
        self.assertEqual(
            result["handoff_evaluation"]["pending_handoff_ids"], [HANDOFF_ID]
        )

    def test_tampered_contracts_cannot_unlock_a_consumer_stage(self) -> None:
        tampered_cases = {
            "unknown producer": ("handoff_contracts", "producer_node_id", "ghost"),
            "wrong relationship": (
                "handoff_contracts",
                "relationship_id",
                "relationship-" + "f" * 16,
            ),
        }
        for label, (section, field, value) in tampered_cases.items():
            with self.subTest(label=label):
                plan = _plan()
                plan[section][0][field] = value
                plan["ordered_stages"][1]["handoff_contracts"][0][field] = value
                result = advance_composition_runtime(
                    plan,
                    {
                        "requested_phase": "implementation",
                        "gate_results": _passing_gates(),
                        "handoff_results": [
                            _handoff_result(
                                producer_node_id=(
                                    value if field == "producer_node_id" else "research"
                                )
                            )
                        ],
                    },
                )
                self.assertFalse(result["phase_advance"]["allowed"])
                self.assertEqual(
                    result["phase_advance"]["blocked_reason"],
                    "invalid_handoff_contracts",
                )

        stage_mismatch = _plan()
        stage_mismatch["ordered_stages"][1]["handoff_contracts"][0][
            "produced_outputs"
        ] = ["forged output"]
        result = advance_composition_runtime(
            stage_mismatch,
            {
                "requested_phase": "implementation",
                "gate_results": _passing_gates(),
                "handoff_results": [_handoff_result()],
            },
        )
        self.assertFalse(result["phase_advance"]["allowed"])
        self.assertEqual(
            result["phase_advance"]["blocked_reason"], "invalid_handoff_contracts"
        )

    def test_runtime_and_receipt_contracts_expose_typed_handoff_fields(self) -> None:
        runtime_properties = COMPOSITION_TOOLS["tmcp_runtime_next"]["inputSchema"][
            "properties"
        ]
        self.assertIn("requested_phase", runtime_properties)
        self.assertIn("handoff_results", runtime_properties)
        self.assertIn("user_redirect", runtime_properties)
        self.assertIn("oneOf", runtime_properties["browser_evidence"]["items"])

        handoff = _handoff_result()
        template = build_receipt_template(
            packet_id="packet-handoff",
            activated_atoms=[],
            composition_fields={"handoff_results": [handoff]},
        )
        receipt = build_run_receipt(
            {"packet_id": "packet-handoff", "handoff_results": [handoff]},
            created_at="2026-07-17T00:00:00Z",
        )
        self.assertEqual(template["handoff_results"], [handoff])
        self.assertEqual(receipt["handoff_results"], [handoff])
        assert_matches_schema(
            receipt,
            ROOT / "schemas" / "tmcp-run-receipt-v0.1.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
