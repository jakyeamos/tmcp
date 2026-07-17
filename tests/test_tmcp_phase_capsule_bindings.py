from __future__ import annotations

import copy
import unittest

from tmcp_runtime.domain.composition_phase_bindings import (
    PhaseCapsuleBindingError,
    build_phase_capsule_binding,
    receipt_matches_phase_capsule_binding,
    validate_phase_capsule_binding,
)


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
                }
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
                }
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
