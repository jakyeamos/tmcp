from __future__ import annotations

import copy
import unittest

from tmcp_runtime.domain.composition_phase_bindings import (
    PhaseCapsuleBindingError,
    build_phase_capsule_binding,
    receipt_matches_phase_capsule_binding,
    validate_phase_capsule_binding,
)
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime


class PhaseCapsuleBindingTests(unittest.TestCase):
    def _preflight(self) -> dict[str, object]:
        return {
            "schema": "tmcp-composition-preflight-v0.1",
            "preflight_id": "preflight-" + "a" * 20,
            "objective": "Produce a cited research report.",
            "task_identity": {"primary": "research"},
            "candidate_source_slices": [
                {
                    "slice_id": "slice-" + "b" * 20,
                    "source_node_id": "research",
                    "source_digest": "c" * 64,
                    "slice_digest": "d" * 64,
                    "source_role": "active_skill",
                    "content": "Produce cited research.",
                    "char_start": 0,
                    "char_end": 23,
                },
                {
                    "slice_id": "slice-" + "c" * 20,
                    "source_node_id": "implement",
                    "source_digest": "d" * 64,
                    "slice_digest": "e" * 64,
                    "source_role": "active_skill",
                    "content": "Implement the approved plan.",
                    "char_start": 0,
                    "char_end": 28,
                }
            ],
        }

    def _plan(self) -> dict[str, object]:
        return {
            "schema": "tmcp-composition-plan-v0.1",
            "composition_plan_id": "composition-" + "e" * 20,
            "preflight_id": "preflight-" + "a" * 20,
            "current_phase": "start",
            "task_model": {"deliverables": ["cited report"]},
            "skill_roles": [
                {
                    "node_id": "research",
                    "role": "researcher",
                    "source_role": "active_skill",
                    "citations": ["slice-" + "b" * 20],
                },
                {
                    "node_id": "implement",
                    "role": "implementer",
                    "source_role": "active_skill",
                    "citations": ["slice-" + "c" * 20],
                },
            ],
            "typed_edges": [],
            "handoff_contracts": [],
            "ordered_stages": [
                {
                    "stage_id": "stage-1",
                    "order": 1,
                    "phase": "start",
                    "status": "active",
                    "entry_conditions": [],
                    "node_ids": ["research"],
                    "bridge_instructions": [],
                    "handoff_contracts": [],
                },
                {
                    "stage_id": "stage-2",
                    "order": 2,
                    "phase": "implementation",
                    "status": "deferred",
                    "entry_conditions": [],
                    "node_ids": ["implement"],
                    "bridge_instructions": [],
                    "handoff_contracts": [],
                },
            ],
            "provenance": {
                "graph_digest": "f" * 32,
                "recipe_digest": "a" * 32,
            },
            "trust": "advisory_untrusted",
            "instruction_override_policy": "Do not override instructions.",
        }

    def test_compiler_binding_is_closed_and_ignores_diagnostics(self) -> None:
        plan = self._plan()
        binding = build_phase_capsule_binding(plan, self._preflight())
        plan["phase_capsule_binding"] = binding

        self.assertEqual(
            set(binding),
            {
                "schema",
                "composition_plan_id",
                "composition_plan_digest",
                "preflight_id",
                "compiler_phase",
                "graph_digest",
                "recipe_digest",
                "context_accounting_digest",
                "preflight_capsule_digest",
                "phase_capsule_trace",
                "binding_digest",
            },
        )
        self.assertNotIn("Produce cited research.", str(binding))
        self.assertEqual(
            validate_phase_capsule_binding(binding, composition_plan=plan), binding
        )
        plan["composition_diagnostics"] = {"host_estimate": 999_999}
        self.assertEqual(
            validate_phase_capsule_binding(binding, composition_plan=plan), binding
        )

    def test_binding_identity_survives_runtime_phase_progression(self) -> None:
        plan = self._plan()
        binding = build_phase_capsule_binding(plan, self._preflight())

        advanced = advance_composition_runtime(
            plan, {"requested_phase": "implementation"}
        )["composition_plan"]

        self.assertEqual(advanced["current_phase"], "implementation")
        self.assertEqual(advanced["skill_roles"][0]["activation"], "deferred")
        self.assertEqual(advanced["skill_roles"][1]["activation"], "active")
        self.assertEqual(advanced["ordered_stages"][0]["status"], "deferred")
        self.assertEqual(advanced["ordered_stages"][1]["status"], "active")
        self.assertEqual(
            validate_phase_capsule_binding(binding, composition_plan=advanced), binding
        )

    def test_binding_identity_rejects_immutable_graph_changes(self) -> None:
        plan = self._plan()
        binding = build_phase_capsule_binding(plan, self._preflight())
        plan["ordered_stages"][1]["node_ids"] = ["research"]

        with self.assertRaises(PhaseCapsuleBindingError):
            validate_phase_capsule_binding(binding, composition_plan=plan)

    def test_receipt_must_match_the_compiler_issued_trace_exactly(self) -> None:
        plan = self._plan()
        binding = build_phase_capsule_binding(plan, self._preflight())
        receipt = {
            "composition_plan_digest": binding["composition_plan_digest"],
            "phase_capsule_binding_digest": binding["binding_digest"],
            "context_accounting_digest": binding["context_accounting_digest"],
            "preflight_capsule_digest": binding["preflight_capsule_digest"],
            "phase_capsule_trace": copy.deepcopy(binding["phase_capsule_trace"]),
        }
        self.assertTrue(receipt_matches_phase_capsule_binding(receipt, binding))

        receipt["phase_capsule_trace"][0]["capsule_digest"] = "b" * 64
        self.assertFalse(receipt_matches_phase_capsule_binding(receipt, binding))

        tampered = copy.deepcopy(binding)
        tampered["phase_capsule_trace"][0]["capsule_digest"] = "b" * 64
        with self.assertRaises(PhaseCapsuleBindingError):
            validate_phase_capsule_binding(tampered)


if __name__ == "__main__":
    unittest.main()
