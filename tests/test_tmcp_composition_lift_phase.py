from __future__ import annotations

import unittest

from tmcp_runtime.domain.composition_lift_phase import (
    DEFAULT_COMPOSITION_HANDOFF_LIMIT,
    bound_phase_artifact,
    bridge_obligation_text,
    handoff_contract_text,
    phase_exit_gate_status,
    phase_deliverable_index,
    phase_contract_text,
    phase_handoff_requirements,
    render_composition_handoff,
)
from tmcp_runtime.safety.redaction import redact_sensitive_text


class CompositionLiftPhaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stage = {
            "phase": "implementation",
            "entry_conditions": ["Complete root cause handoff."],
            "bridge_instructions": [
                {
                    "role": "targeted-fix specialist",
                    "required_inputs": ["root cause handoff"],
                    "produced_outputs": ["fix handoff"],
                    "covered_criteria": ["narrowest change"],
                    "exit_gates": ["narrowest change"],
                    "citations": ["slice-" + "c" * 20],
                }
            ],
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

    def test_bridge_obligations_preserve_typed_handoff_fields(self) -> None:
        rendered = bridge_obligation_text(self.stage)
        self.assertIn("required input=root cause handoff", rendered)
        self.assertIn("produced handoff=fix handoff", rendered)
        self.assertIn("cover criterion=narrowest change", rendered)
        self.assertIn("exit gate=narrowest change", rendered)
        self.assertIn("slice-" + "c" * 20, rendered)

    def test_requirements_include_evidence_index_and_complete_envelope(self) -> None:
        rendered = phase_handoff_requirements(
            self.stage,
            ["targeted-fix"],
            self.sources,
            self.task_context,
        )
        self.assertIn("diagnosis-reproduction", rendered)
        self.assertIn("Current bridge obligations", rendered)
        self.assertIn("cover criterion=narrowest change", rendered)
        self.assertIn("Enumerate every material state, path, claim, or gate", rendered)
        self.assertIn("concise means no repeated incoming context", rendered)
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

    def test_bounded_phase_envelope_preserves_gate_suffixes(self) -> None:
        artifact = "\n\n".join(
            [
                "STATUS: COMPLETE\n" + ("status detail " * 80),
                "DELIVERABLES\n" + ("deliverable detail " * 80),
                "EXIT_GATE: PASS\n" + ("gate detail " * 80),
            ]
        )
        bounded = bound_phase_artifact(artifact, limit=900)
        self.assertLessEqual(len(bounded), 900)
        self.assertIn("STATUS: COMPLETE", bounded)
        self.assertIn("EXIT_GATE: PASS", bounded)

    def test_phase_exit_gate_status_is_deterministic(self) -> None:
        self.assertEqual(
            phase_exit_gate_status("EXIT_GATE: PASS\nEvidence is complete."),
            "pass",
        )
        self.assertEqual(
            phase_exit_gate_status("EXIT_GATE\nreadiness risks: FAIL."),
            "fail",
        )
        self.assertEqual(
            phase_exit_gate_status("EXIT_GATE: BLOCKED\nMissing handoff."),
            "blocked",
        )
        self.assertEqual(phase_exit_gate_status("STATUS: PASS"), "unknown")

    def test_deliverable_index_quotes_phase_outputs_without_execution_claims(self) -> None:
        artifacts = [
            (
                {"phase": "discovery", "status": "active"},
                "DELIVERABLES\nRoot cause record.\nPRODUCED_HANDOFF\nROOT_CAUSE_HANDOFF\nEXIT_GATE: PASS",
            ),
            (
                {"phase": "verification", "status": "deferred"},
                "DELIVERABLES\nRegression matrix.\nPRODUCED_HANDOFF\nBEHAVIOR_HANDOFF\nEXIT_GATE: BLOCKED",
            ),
        ]
        index = phase_deliverable_index(artifacts)
        self.assertIn("phase 1 discovery | gate=PASS", index)
        self.assertIn("Root cause record", index)
        self.assertIn("BEHAVIOR_HANDOFF", index)
        self.assertIn("handoff: BEHAVIOR_HANDOFF", index)
        self.assertNotIn("host execution", index.casefold())
        rendered = render_composition_handoff(artifacts, limit=2_000)
        self.assertIn("# Composition deliverable index", rendered)
        self.assertIn("## Phase 2: verification (deferred)", rendered)

    def test_index_labels_do_not_trigger_opaque_assignment_redaction(self) -> None:
        artifacts = [
            (
                {"phase": "implementation", "status": "deferred"},
                "DELIVERABLES\nNo change.\nPRODUCED_HANDOFF\n"
                "component-handoff-ui-architecture\nEXIT_GATE: BLOCKED",
            )
        ]
        rendered = render_composition_handoff(artifacts)
        _safe, redactions = redact_sensitive_text(rendered, enabled=True)
        self.assertNotIn("long_high_entropy", redactions)

    def test_default_composition_handoff_stays_inside_lift_artifact_ceiling(self) -> None:
        artifacts = [
            (
                {"phase": f"phase-{index}", "status": "active"},
                "DELIVERABLES\n"
                + ("deliverable " * 900)
                + "\nPRODUCED_HANDOFF\n"
                + ("handoff " * 900)
                + "\nEXIT_GATE: PASS",
            )
            for index in range(5)
        ]
        rendered = render_composition_handoff(artifacts)
        self.assertLessEqual(len(rendered), DEFAULT_COMPOSITION_HANDOFF_LIMIT)
        self.assertLess(len(rendered), 16_000)

    def test_render_compacts_prior_phases_but_keeps_current_envelope(self) -> None:
        headings = (
            "PHASE_RESULT",
            "STATUS: PASS",
            "DELIVERABLES",
            "EVIDENCE_BOUNDARY",
            "PRODUCED_HANDOFF",
            "EXIT_GATE: PASS",
            "NEXT_ENTRY",
            "UNRESOLVED_GAPS",
        )
        artifacts = [
            (
                {"phase": f"phase-{index}", "status": "active"},
                "\n\n".join(f"{heading}\n" + ("detail " * 160) for heading in headings),
            )
            for index in range(1, 4)
        ]
        rendered = render_composition_handoff(artifacts)
        self.assertLess(len(rendered), 11_000)
        self.assertEqual(rendered.count("## Phase "), 3)
        self.assertEqual(rendered.count("EXIT_GATE"), 3)
        self.assertIn("phase 1 phase-1", rendered)
        self.assertIn("phase 3 phase-3", rendered)
        self.assertIn("UNRESOLVED_GAPS", rendered)


if __name__ == "__main__":
    unittest.main()
