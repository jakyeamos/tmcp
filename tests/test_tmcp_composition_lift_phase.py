from __future__ import annotations

import unittest

from tmcp_runtime.domain.composition_lift_phase import (
    bound_phase_artifact,
    handoff_contract_text,
    phase_contract_text,
    phase_handoff_requirements,
)


class CompositionLiftPhaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stage = {
            "phase": "implementation",
            "entry_conditions": ["Complete root cause handoff."],
            "handoff_contracts": [
                {
                    "handoff_id": "handoff-" + "a" * 20,
                    "producer_node_id": "diagnosis",
                    "consumer_node_id": "fix",
                    "relationship_type": "enables",
                    "required_inputs": ["root cause handoff"],
                    "produced_outputs": ["root cause handoff"],
                    "producer_exit_gates": ["diagnosis evidence"],
                    "citations": ["slice-" + "b" * 20],
                }
            ],
        }
        self.sources = {
            "targeted-fix": """Inputs: root cause handoff.
Outputs: fix handoff.
Exit gate: narrowest change.
Output contract:
- Produce a focused change list with the root-cause link.
- Mark the narrowest-change exit gate pass/fail with targeted evidence.
"""
        }
        self.task_context = {
            "evidence": [
                {
                    "evidence_id": "diagnosis-reproduction",
                    "kind": "failure_reproduction",
                    "provenance": "fixture_supplied",
                }
            ]
        }

    def test_phase_contract_preserves_typed_source_contract(self) -> None:
        rendered = phase_contract_text(self.stage, ["targeted-fix"], self.sources)
        self.assertIn("typed inputs: root cause handoff.", rendered)
        self.assertIn("typed output: fix handoff.", rendered)
        self.assertIn("typed exit gate: narrowest change.", rendered)
        self.assertIn("root-cause link", rendered)

    def test_handoff_contract_includes_edges_and_citations(self) -> None:
        rendered = handoff_contract_text(self.stage)
        self.assertIn("enables", rendered)
        self.assertIn("root cause handoff", rendered)
        self.assertIn("slice-" + "b" * 20, rendered)

    def test_requirements_include_evidence_index_and_complete_envelope(self) -> None:
        rendered = phase_handoff_requirements(
            self.stage,
            ["targeted-fix"],
            self.sources,
            self.task_context,
        )
        self.assertIn("diagnosis-reproduction", rendered)
        self.assertIn("PHASE_RESULT; STATUS; INPUT_HANDOFF", rendered)
        self.assertIn("Complete root cause handoff.", rendered)

    def test_bounded_artifact_retains_head_and_exit_tail(self) -> None:
        artifact = "DELIVERABLES\n" + ("x" * 200) + "\nEXIT_GATE: PASS\n" + ("y" * 200)
        bounded = bound_phase_artifact(artifact, limit=220)
        self.assertLessEqual(len(bounded), 220)
        self.assertIn("DELIVERABLES", bounded)
        self.assertIn("EXIT_GATE: PASS", bounded)
        self.assertIn("elided", bounded)

    def test_bounded_phase_envelope_preserves_present_headings(self) -> None:
        headings = (
            "PHASE_RESULT",
            "STATUS",
            "INPUT_HANDOFF",
            "DELIVERABLES",
            "EVIDENCE_BOUNDARY",
            "PRODUCED_HANDOFF",
            "EXIT_GATE",
            "NEXT_ENTRY",
            "UNRESOLVED_GAPS",
        )
        artifact = "\n\n".join(
            f"{heading}\n" + (f"{heading.lower()} detail " * 80) for heading in headings
        )
        bounded = bound_phase_artifact(artifact, limit=900)
        self.assertLessEqual(len(bounded), 900)
        for heading in headings:
            self.assertEqual(bounded.count(heading), 1)


if __name__ == "__main__":
    unittest.main()
