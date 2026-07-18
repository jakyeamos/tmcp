from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path
from typing import Any

import tmcp_runtime.domain.composition_runtime as composition_runtime
import tmcp_runtime.domain.composition_runtime_evidence as runtime_evidence
from tmcp_runtime.domain.composition_runtime import (
    advance_composition_runtime,
    composition_gate_catalog,
    evaluate_composition_gates,
    normalize_runtime_evidence,
)


def _role(
    node_id: str,
    phase: str,
    exit_gate: str,
    activation: str,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "role": f"{node_id} specialist",
        "inputs": [f"{node_id} required state"],
        "outputs": [f"{node_id} handoff"],
        "phase_affinity": [phase],
        "entry_gates": [],
        "exit_gates": [exit_gate],
        "context_cost": 100,
        "covers": [],
        "citations": [f"slice-{node_id}"],
        "source_role": "active_skill",
        "activation": activation,
    }


def _bridge(node_id: str) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "instruction": f"Apply {node_id} and produce its handoff.",
        "citations": [f"slice-{node_id}"],
        "trust": "advisory_untrusted",
    }


def _plan() -> dict[str, Any]:
    return {
        "schema": "tmcp-composition-plan-v0.1",
        "composition_plan_id": "composition-runtime-fixture",
        "preflight_id": "preflight-runtime-fixture",
        "current_phase": "discovery",
        "task_model": {
            "deliverables": ["Working change"],
            "success_criteria": ["Focused verification passes"],
            "constraints": [],
            "subgoals": ["Research", "Implement", "Verify"],
            "evidence_needs": [],
        },
        "skill_roles": [
            _role(
                "research",
                "discovery",
                "Research brief approved",
                "active",
            ),
            _role(
                "implement",
                "implementation",
                "Focused tests pass",
                "deferred",
            ),
            _role(
                "verify",
                "verification",
                "Final review passes",
                "deferred",
            ),
        ],
        "typed_edges": [
            {
                "from": "research",
                "to": "implement",
                "type": "precedes",
                "citations": ["slice-research", "slice-implement"],
                "rationale": "Research produces the implementation brief.",
            },
            {
                "from": "implement",
                "to": "verify",
                "type": "enables",
                "citations": ["slice-implement", "slice-verify"],
                "rationale": "The implementation enables verification.",
            },
        ],
        "ordered_stages": [
            {
                "stage_id": "stage-1",
                "order": 1,
                "phase": "discovery",
                "status": "active",
                "entry_conditions": [],
                "node_ids": ["research"],
                "bridge_instructions": [_bridge("research")],
            },
            {
                "stage_id": "stage-2",
                "order": 2,
                "phase": "implementation",
                "status": "deferred",
                "entry_conditions": ["Research handoff available"],
                "node_ids": ["implement"],
                "bridge_instructions": [_bridge("implement")],
            },
            {
                "stage_id": "stage-3",
                "order": 3,
                "phase": "verification",
                "status": "deferred",
                "entry_conditions": ["Implementation available"],
                "node_ids": ["verify"],
                "bridge_instructions": [_bridge("verify")],
            },
        ],
        "coverage": {
            "facets": [],
            "covered_criteria": [],
            "uncovered_criteria": ["Focused verification passes"],
            "unresolved_gaps": ["Focused verification passes"],
        },
        "provenance": {
            "graph_digest": "abc123",
            "content_digests": ["source-a", "source-b"],
            "normalized_relationship_count": 2,
            "identity_policy": "normalized_source_content_and_typed_relationships",
        },
        "composition_diagnostics": {},
        "trust": "advisory_untrusted",
        "instruction_override_policy": "Advisory only.",
    }


def _passed(name: str) -> dict[str, str]:
    return {"gate": name, "status": "passed"}


class CompositionRuntimeEvidenceTests(unittest.TestCase):
    def test_normalization_preserves_inputs_and_records_unstructured_evidence(
        self,
    ) -> None:
        raw: dict[str, Any] = {
            "files_read": "src/app.py",
            "files_changed": ["src/app.py"],
            "commands_run": ["python -m unittest"],
            "verification_results": [
                "tests looked good",
                {"gate": "Research brief approved", "status": "passed"},
            ],
            "gate_results": {"gate": "Unknown gate", "status": "passed"},
            "browser_evidence": ["screenshot captured"],
            "user_overrides": "keep current labels",
            "latest_user_message": "Continue",
            "requested_phase": "implementation",
        }
        before = copy.deepcopy(raw)

        normalized = normalize_runtime_evidence(raw)

        self.assertEqual(raw, before)
        self.assertEqual(normalized["files_read"], ["src/app.py"])
        self.assertEqual(normalized["files_changed"], ["src/app.py"])
        self.assertEqual(len(normalized["verification_results"]), 1)
        reasons = {item["reason"] for item in normalized["unstructured_evidence"]}
        self.assertIn("Unstructured evidence cannot satisfy a named gate.", reasons)
        self.assertIn(
            "Expected an array; value was retained as one observation.", reasons
        )

    def test_gate_catalog_is_stable_and_covers_entry_and_exit_gates(self) -> None:
        first = composition_gate_catalog(_plan())
        second = composition_gate_catalog(_plan())

        self.assertEqual(first, second)
        self.assertEqual(
            [item["name"] for item in first],
            [
                "Research brief approved",
                "Research handoff available",
                "Focused tests pass",
                "Implementation available",
                "Final review passes",
            ],
        )
        self.assertEqual(
            [item["kind"] for item in first],
            ["exit", "entry", "exit", "entry", "exit"],
        )
        self.assertEqual(len({item["gate_id"] for item in first}), 5)

    def test_only_named_structured_results_pass_and_failures_win(self) -> None:
        result = evaluate_composition_gates(
            _plan(),
            {
                "gate_results": [
                    "Research brief approved",
                    _passed("Research brief approved"),
                    {"gate": "Research brief approved", "status": "failed"},
                    {"gate": "Not in the graph", "status": "passed"},
                ]
            },
        )

        research_gate = next(
            item
            for item in result["evaluated_gates"]
            if item["name"] == "Research brief approved"
        )
        self.assertEqual(research_gate["status"], "failed")
        self.assertEqual(result["passed_gate_ids"], [])
        self.assertEqual(result["unmatched_results"][0]["reason"], "unknown_gate_name")
        self.assertTrue(result["unstructured_evidence"])

    def test_ambiguous_gate_names_require_stable_gate_ids(self) -> None:
        plan = _plan()
        plan["ordered_stages"][1]["entry_conditions"] = ["Research brief approved"]

        by_name = evaluate_composition_gates(
            plan,
            {"gate_results": [_passed("Research brief approved")]},
        )
        self.assertEqual(
            by_name["unmatched_results"][0]["reason"], "ambiguous_gate_name"
        )
        self.assertEqual(by_name["passed_gate_ids"], [])

        gate_id = next(
            item["gate_id"]
            for item in composition_gate_catalog(plan)
            if item["kind"] == "exit" and item["name"] == "Research brief approved"
        )
        by_id = evaluate_composition_gates(
            plan,
            {"gate_results": [{"gate_id": gate_id, "status": "passed"}]},
        )
        self.assertEqual(by_id["passed_gate_ids"], [gate_id])


class CompositionRuntimeTransitionTests(unittest.TestCase):
    def test_governing_roles_remain_active_across_non_governing_stages(self) -> None:
        plan = _plan()
        plan["skill_roles"][0]["source_role"] = "governing_instruction"

        result = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "gate_results": [
                    _passed("Research brief approved"),
                    _passed("Research handoff available"),
                ],
            },
        )

        activations = {
            item["node_id"]: item["activation"]
            for item in result["composition_plan"]["skill_roles"]
        }
        self.assertEqual(result["active_skill_ids"], ["implement"])
        self.assertEqual(result["active_governing_node_ids"], ["research"])
        self.assertEqual(
            activations,
            {"research": "active", "implement": "active", "verify": "deferred"},
        )
        self.assertEqual(
            [item["node_id"] for item in result["deferred_skills"]],
            ["verify"],
        )

    def test_pending_gates_block_advancement_and_keep_only_current_skill_active(
        self,
    ) -> None:
        plan = _plan()
        before = copy.deepcopy(plan)

        result = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "files_read": ["docs/research.md"],
                "commands_run": ["python -m unittest"],
                "browser_evidence": ["render looked correct"],
                "verification_results": ["Research brief approved"],
            },
        )

        self.assertEqual(plan, before)
        self.assertFalse(result["phase_advance"]["allowed"])
        self.assertEqual(
            result["phase_advance"]["blocked_reason"],
            "required_gates_not_passed",
        )
        self.assertEqual(result["current_phase"], "discovery")
        self.assertEqual(result["active_skill_ids"], ["research"])
        self.assertEqual(
            [item["node_id"] for item in result["deferred_skills"]],
            ["implement", "verify"],
        )
        self.assertEqual(
            result["deferred_skills"][0]["entry_conditions"],
            ["Research handoff available"],
        )
        self.assertEqual(result["phase_trace"][-1]["status"], "blocked")
        self.assertEqual(result["graph_diff"]["reads"]["added"], ["docs/research.md"])
        self.assertTrue(result["gate_evaluation"]["unstructured_evidence"])
        self.assertIn(
            "browser_evidence",
            {item.get("kind") for item in result["runtime_observations"]},
        )

    def test_passing_exit_and_entry_gates_advances_and_emits_graph_diff(self) -> None:
        plan = _plan()

        result = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "files_read": ["docs/research.md"],
                "files_changed": ["src/app.py"],
                "commands_run": ["python -m unittest"],
                "gate_results": [
                    _passed("Research brief approved"),
                    _passed("Research handoff available"),
                ],
            },
        )

        self.assertTrue(result["phase_advance"]["allowed"])
        self.assertEqual(result["current_phase"], "implementation")
        self.assertEqual(result["current_stage_id"], "stage-2")
        self.assertEqual(result["active_skill_ids"], ["implement"])
        activations = {
            item["node_id"]: item["activation"]
            for item in result["composition_plan"]["skill_roles"]
        }
        self.assertEqual(
            activations,
            {"research": "deferred", "implement": "active", "verify": "deferred"},
        )
        self.assertEqual(
            result["composition_plan"]["composition_plan_id"],
            plan["composition_plan_id"],
        )
        self.assertEqual(result["composition_plan"]["provenance"], plan["provenance"])
        self.assertEqual(result["graph_diff"]["skills"]["added"], ["implement"])
        self.assertEqual(result["graph_diff"]["skills"]["dropped"], ["research"])
        self.assertEqual(len(result["graph_diff"]["relationships"]["added"]), 1)
        self.assertEqual(len(result["graph_diff"]["instructions"]["added"]), 1)
        self.assertEqual(len(result["graph_diff"]["instructions"]["dropped"]), 1)
        self.assertEqual(
            result["graph_diff"]["phase_change"],
            {"from": "discovery", "to": "implementation"},
        )
        self.assertEqual(len(result["fulfilled_obligations"]), 2)
        self.assertEqual(len(result["graph_diff"]["gates"]["newly_fulfilled"]), 2)

    def test_failures_block_even_when_named_gates_pass(self) -> None:
        result = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "gate_results": [
                    _passed("Research brief approved"),
                    _passed("Research handoff available"),
                ],
                "failures": ["Research fixture failed"],
            },
        )

        self.assertFalse(result["phase_advance"]["allowed"])
        self.assertEqual(
            result["phase_advance"]["blocked_reason"],
            "runtime_failures_present",
        )
        self.assertEqual(result["active_skill_ids"], ["research"])

    def test_explicit_phase_override_bypasses_but_does_not_fulfill_gates(self) -> None:
        generic = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "user_overrides": ["Keep the existing navigation labels"],
            },
        )
        self.assertFalse(generic["phase_advance"]["allowed"])

        unlinked = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "user_overrides": [
                    {
                        "action": "advance_phase",
                        "reason": "Accept the known verification risk",
                    }
                ],
            },
        )
        self.assertFalse(unlinked["phase_advance"]["allowed"])

        explicit = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "latest_user_message": "I accept the known verification risk.",
                "user_overrides": [
                    {
                        "action": "advance_phase",
                        "source": "user",
                        "message": "Accept the known verification risk",
                    }
                ],
            },
        )

        self.assertTrue(explicit["phase_advance"]["allowed"])
        self.assertTrue(explicit["phase_advance"]["override_applied"])
        self.assertEqual(explicit["current_phase"], "implementation")
        self.assertEqual(explicit["fulfilled_obligations"], [])
        self.assertEqual(
            set(explicit["graph_diff"]["gates"]["bypassed"]),
            set(explicit["phase_advance"]["required_gate_ids"]),
        )
        self.assertEqual(
            explicit["phase_trace"][-1]["status"], "advanced_with_override"
        )

    def test_same_phase_successor_requires_gates_and_remains_reachable(self) -> None:
        plan = _plan()
        plan["ordered_stages"][2]["phase"] = "implementation"
        implementation = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "gate_results": [
                    _passed("Research brief approved"),
                    _passed("Research handoff available"),
                ],
            },
        )

        blocked = advance_composition_runtime(
            implementation["composition_plan"],
            {"requested_phase": "implementation"},
        )
        self.assertFalse(blocked["phase_advance"]["allowed"])
        self.assertEqual(blocked["current_stage_id"], "stage-2")
        self.assertEqual(
            blocked["phase_advance"]["blocked_reason"],
            "required_gates_not_passed",
        )

        advanced = advance_composition_runtime(
            implementation["composition_plan"],
            {
                "requested_phase": "implementation",
                "gate_results": [
                    _passed("Focused tests pass"),
                    _passed("Implementation available"),
                ],
            },
        )
        self.assertTrue(advanced["phase_advance"]["allowed"])
        self.assertEqual(advanced["current_stage_id"], "stage-3")
        self.assertEqual(advanced["current_phase"], "implementation")
        self.assertEqual(advanced["active_skill_ids"], ["verify"])
        self.assertEqual(advanced["phase_trace"][-1]["status"], "advanced")

        overridden = advance_composition_runtime(
            implementation["composition_plan"],
            {
                "requested_phase": "implementation",
                "user_overrides": [
                    {
                        "action": "advance_phase",
                        "source": "user",
                        "message": "Accept the known verification risk",
                    }
                ],
                "latest_user_message": "I accept the known verification risk.",
            },
        )
        self.assertTrue(overridden["phase_advance"]["override_applied"])
        self.assertEqual(overridden["current_stage_id"], "stage-3")
        self.assertEqual(
            overridden["phase_trace"][-1]["status"], "advanced_with_override"
        )

    def test_override_cannot_make_an_unknown_phase_valid(self) -> None:
        result = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "deployment",
                "user_overrides": [
                    {"action": "advance_phase", "reason": "Go to deployment"}
                ],
            },
        )

        self.assertFalse(result["phase_advance"]["allowed"])
        self.assertFalse(result["phase_advance"]["override_applied"])
        self.assertEqual(
            result["phase_advance"]["blocked_reason"], "unknown_requested_phase"
        )
        self.assertTrue(result["warnings"])

    def test_runtime_state_carries_fulfilled_gates_and_accumulates_trace(self) -> None:
        implementation = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "gate_results": [
                    _passed("Research brief approved"),
                    _passed("Research handoff available"),
                ],
                "files_read": ["docs/research.md"],
            },
        )
        verification = advance_composition_runtime(
            implementation["composition_plan"],
            {
                "requested_phase": "verification",
                "verification_results": [
                    _passed("Focused tests pass"),
                    _passed("Implementation available"),
                ],
                "files_read": ["src/app.py"],
            },
        )

        self.assertTrue(verification["phase_advance"]["allowed"])
        self.assertEqual(verification["current_phase"], "verification")
        self.assertEqual(verification["active_skill_ids"], ["verify"])
        self.assertEqual(len(verification["phase_trace"]), 2)
        self.assertEqual(len(verification["fulfilled_obligations"]), 4)
        self.assertEqual(
            verification["graph_diff"]["reads"]["all"],
            ["docs/research.md", "src/app.py"],
        )
        carried = [
            item
            for item in verification["gate_evaluation"]["evaluated_gates"]
            if item["carried"]
        ]
        self.assertEqual(len(carried), 2)

    def test_backward_phase_request_reactivates_only_the_prior_stage(self) -> None:
        implementation = advance_composition_runtime(
            _plan(),
            {
                "requested_phase": "implementation",
                "gate_results": [
                    _passed("Research brief approved"),
                    _passed("Research handoff available"),
                ],
            },
        )

        reverted = advance_composition_runtime(
            implementation["composition_plan"],
            {"requested_phase": "discovery"},
        )

        self.assertTrue(reverted["phase_advance"]["allowed"])
        self.assertEqual(reverted["current_phase"], "discovery")
        self.assertEqual(reverted["active_skill_ids"], ["research"])
        self.assertEqual(reverted["phase_trace"][-1]["status"], "reverted")

    def test_invalid_plan_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "tmcp-composition-plan-v0.1"):
            advance_composition_runtime({"schema": "wrong"}, {})


class CompositionRuntimePurityTests(unittest.TestCase):
    def test_runtime_modules_have_no_io_or_service_imports_and_stay_bounded(
        self,
    ) -> None:
        forbidden_prefixes = (
            "os",
            "pathlib",
            "subprocess",
            "scripts",
            "tmcp_runtime.safety",
            "tmcp_runtime.services",
            "tmcp_runtime.storage",
        )
        for module in (composition_runtime, runtime_evidence):
            with self.subTest(module=module.__name__):
                source_path = Path(inspect.getfile(module))
                source = source_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                imported = {
                    node.module or ""
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                }
                imported.update(
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                )
                self.assertTrue(
                    all(
                        not name.startswith(prefix)
                        for name in imported
                        for prefix in forbidden_prefixes
                    )
                )
                nonblank = sum(bool(line.strip()) for line in source.splitlines())
                self.assertLessEqual(nonblank, 600)


if __name__ == "__main__":
    unittest.main()
