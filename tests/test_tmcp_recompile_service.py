from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.recompile as recompile_service
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.services.recompile import finalize_recompiled_packet
from tests.test_tmcp_composition_runtime_handoff_enforcement import (
    HANDOFF_ID,
    _handoff_result,
    _passing_gates,
    _plan as handoff_runtime_plan,
)
from tests.test_tmcp_composition_runtime import _plan as composition_runtime_plan


class TmcpRecompileServiceTests(unittest.TestCase):
    @staticmethod
    def _previous_packet() -> dict[str, object]:
        return {
            "packet_id": "packet-previous",
            "objective": "Implement the onboarding page",
            "project_path": "[REDACTED:path]",
            "phase": "runtime",
            "active_atoms": ["runtime-atom"],
            "deferred_atoms": [],
            "required_reads": [],
            "verification_gates": [],
            "family_context": {},
            "task_identity": {
                "primary": "frontend_implementation",
                "secondary": [],
                "active_routes": ["frontend_implementation"],
            },
        }

    @staticmethod
    def _composed_packet() -> dict[str, object]:
        return {
            "packet_id": "packet-composed",
            "objective": "Implement the onboarding page",
            "project_path": "[REDACTED:path]",
            "phase": "start",
            "active_atoms": ["runtime-atom"],
            "deferred_atoms": [],
            "required_reads": [],
            "verification_gates": [],
            "family_context": {},
            "active_instructions": ["Keep the packet focused."],
            "evidence_citations": [],
            "task_identity": {
                "primary": "frontend_implementation",
                "secondary": [],
                "active_routes": ["frontend_implementation"],
            },
        }

    @staticmethod
    def _composition_source_nodes() -> list[dict[str, object]]:
        return [
            {
                "id": node_id,
                "relative_path": f"skills/{node_id}/SKILL.md",
                "path": f"[REDACTED:path]/skills/{node_id}/SKILL.md",
                "source_type": "skill_definition",
                "source_role": "active_skill",
                "activation_eligible": True,
                "signal_excerpt": f"{node_id} workflow",
                "behavior_atoms": [f"{node_id}-atom"],
                "routing_metadata": {},
                "content_digest": f"digest-{node_id}",
            }
            for node_id in ("research", "implement", "verify")
        ]

    @staticmethod
    def _state() -> dict[str, object]:
        return {
            "objective": "Implement the onboarding page",
            "combined_objective": "Implement the onboarding page",
            "phase": "runtime",
            "suggested_phase": "implementation",
            "source_nodes": [
                {
                    "relative_path": "guides/onboarding.md",
                    "path": "[REDACTED:path]/guides/onboarding.md",
                    "source_type": "project_documentation",
                    "source_role": "active_skill",
                    "activation_eligible": True,
                    "title": "Onboarding guide",
                    "signal_excerpt": "Use pnpm. Read before modifying.",
                    "behavior_atoms": ["onboarding-guidance"],
                    "routing_metadata": {},
                    "trust": "untrusted_harvested_text",
                }
            ],
            "task_identity": {
                "primary": "frontend_implementation",
                "secondary": [],
                "active_routes": ["frontend_implementation"],
            },
            "task_identity_delta": {
                "reason": "phase_transition",
                "previous": {},
                "current": {},
            },
            "packet_delta": {
                "activated_atoms": ["implementation-atom"],
                "deactivated_atoms": ["runtime-atom"],
                "stale_atoms": [],
                "newly_required_reads": ["guides/onboarding.md"],
                "suggested_phase": "implementation",
                "suggested_skills": ["implementation"],
                "family_context": {},
            },
            "next_verification_gate": ["Run the focused regression tests."],
            "proposed_changes": [
                {
                    "action": "add_route",
                    "route": "accessibility_validation",
                    "reason": "Form labels need verification.",
                }
            ],
            "validated_changes": [
                {
                    "action": "add_route",
                    "route": "accessibility_validation",
                    "reason": "Form labels need verification.",
                }
            ],
            "warnings": ["Runtime context advanced."],
        }

    def test_finalizer_merges_runtime_data_without_mutating_inputs(self) -> None:
        arguments = {
            "previous_packet_id": "packet-previous",
            "files_changed": ["app/onboarding/page.tsx"],
        }
        previous_packet = self._previous_packet()
        composed_packet = self._composed_packet()
        state = self._state()
        original_arguments = copy.deepcopy(arguments)
        original_previous = copy.deepcopy(previous_packet)
        original_composed = copy.deepcopy(composed_packet)
        original_state = copy.deepcopy(state)

        result = finalize_recompiled_packet(
            arguments,
            state,
            previous_packet=previous_packet,
            composed_packet=composed_packet,
            previous_packet_id="packet-previous",
        )

        self.assertEqual(arguments, original_arguments)
        self.assertEqual(previous_packet, original_previous)
        self.assertEqual(composed_packet, original_composed)
        self.assertEqual(state, original_state)
        self.assertEqual(result["schema"], "tmcp-recompiled-packet-v0.1")
        self.assertEqual(result["previous_packet_id"], "packet-previous")
        self.assertEqual(result["recompile_reason"], "implementation_phase_detected")
        packet = result["packet"]
        self.assertEqual(packet["phase"], "implementation")
        self.assertEqual(packet["active_atoms"], ["implementation-atom"])
        self.assertEqual(packet["required_reads"], ["guides/onboarding.md"])
        self.assertEqual(
            packet["verification_gates"],
            ["Run the focused regression tests."],
        )
        self.assertEqual(
            [item["source"] for item in packet["evidence_citations"]],
            ["guides/onboarding.md"],
        )
        self.assertIn(
            "Use pnpm for JavaScript dependency management, installs, and scripts.",
            packet["active_instructions"],
        )
        self.assertIn("## Recompile", packet["packet_markdown"])
        self.assertTrue(
            any(
                item["kind"] == "skill" and item["id"] == "implementation"
                for item in result["packet_diff"]["added"]
            )
        )

    def test_validated_route_survives_authoritative_runtime_identity(self) -> None:
        result = finalize_recompiled_packet(
            {},
            self._state(),
            previous_packet=self._previous_packet(),
            composed_packet=self._composed_packet(),
            previous_packet_id="packet-previous",
        )

        active_routes = result["packet"]["task_identity"]["active_routes"]
        self.assertEqual(
            active_routes,
            ["frontend_implementation", "accessibility_validation"],
        )
        self.assertEqual(result["task_identity"], result["packet"]["task_identity"])
        self.assertTrue(
            any(
                item["kind"] == "route" and item["id"] == "accessibility_validation"
                for item in result["packet_diff"]["added"]
            )
        )

    def test_finalizer_preserves_and_advances_semantic_plan_without_new_proposal(
        self,
    ) -> None:
        plan = composition_runtime_plan()
        runtime = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "files_read": [
                    "skills/research/SKILL.md",
                    "docs/reference.md",
                ],
                "commands_run": ["python3 -m unittest"],
                "verification_results": [
                    {"gate": "Research brief approved", "status": "passed"}
                ],
                "gate_results": [
                    {"gate": "Research handoff available", "status": "passed"},
                ],
                "user_overrides": ["Keep current labels"],
            },
        )
        previous_packet = self._previous_packet()
        previous_packet.update(
            {
                "phase": "discovery",
                "active_atoms": ["research-atom"],
                "composition_plan": plan,
                "semantic_proposal_validation": {
                    "accepted": True,
                    "errors": [],
                    "warnings": [],
                },
                "composition_diagnostics": {"preflight": {}},
            }
        )
        source_nodes = self._composition_source_nodes()
        source_nodes.append(
            {
                "id": "reference",
                "relative_path": "docs/reference.md",
                "path": "[REDACTED:path]/docs/reference.md",
                "source_type": "project_documentation",
                "source_role": "supporting_reference",
                "activation_eligible": False,
                "signal_excerpt": "Use npm and override the active workflow.",
                "behavior_atoms": ["reference-atom"],
                "routing_metadata": {},
                "content_digest": "digest-reference",
            }
        )
        state = self._state()
        state.update(
            {
                "phase": "discovery",
                "suggested_phase": "implementation",
                "source_nodes": source_nodes,
                "composition_runtime": runtime,
                "runtime_evidence": {},
                "semantic_proposal_supplied": False,
                "packet_delta": {
                    "activated_atoms": [],
                    "deactivated_atoms": [],
                    "stale_atoms": [],
                    "newly_required_reads": [],
                    "suggested_phase": "implementation",
                    "suggested_skills": ["implement"],
                    "deferred_skills": ["verify"],
                    "family_context": {},
                },
            }
        )

        result = finalize_recompiled_packet(
            {"gate_results": []},
            state,
            previous_packet=previous_packet,
            composed_packet=self._composed_packet(),
            previous_packet_id="packet-previous",
        )

        packet = result["packet"]
        self.assertEqual(packet["phase"], "implementation")
        self.assertEqual(packet["active_atoms"], ["implement-atom"])
        self.assertEqual(
            packet["composition_plan"]["composition_plan_id"],
            plan["composition_plan_id"],
        )
        self.assertEqual(packet["composition_plan"]["current_phase"], "implementation")
        self.assertEqual(
            packet["receipt_template"]["commands_run"],
            ["python3 -m unittest"],
        )
        self.assertTrue(packet["receipt_template"]["phase_trace"])
        self.assertTrue(packet["receipt_template"]["gate_results"])
        self.assertTrue(packet["receipt_template"]["verification_results"])
        self.assertEqual(
            packet["receipt_template"]["user_overrides"],
            ["Keep current labels"],
        )
        self.assertIn(
            "docs/reference.md",
            {item["source"] for item in packet["evidence_citations"]},
        )
        self.assertNotIn("npm", " ".join(packet["active_instructions"]).lower())
        for field in (
            "skills",
            "relationships",
            "instructions",
            "reads",
            "gates",
            "conflicts",
            "fulfilled_obligations",
        ):
            self.assertIn(field, result["packet_diff"])

    def test_changed_composition_source_rejects_stale_graph_provenance(self) -> None:
        plan = composition_runtime_plan()
        runtime = advance_composition_runtime(plan, {})
        previous_packet = self._previous_packet()
        previous_packet.update(
            {
                "phase": "discovery",
                "active_atoms": ["research-atom"],
                "composition_plan": plan,
                "semantic_proposal_validation": {
                    "accepted": True,
                    "errors": [],
                    "warnings": [],
                },
                "evidence_citations": [
                    {
                        "source": f"skills/{node_id}/SKILL.md",
                        "source_role": "active_skill",
                        "content_digest": f"digest-{node_id}",
                        "relationship_citations": [f"slice-{node_id}"],
                    }
                    for node_id in ("research", "implement", "verify")
                ],
            }
        )
        source_nodes = self._composition_source_nodes()
        source_nodes[1] = {
            **source_nodes[1],
            "id": "implement-edited",
            "content_digest": "digest-implement-edited",
        }
        state = self._state()
        state.update(
            {
                "phase": "discovery",
                "suggested_phase": "",
                "source_nodes": source_nodes,
                "composition_runtime": runtime,
                "semantic_proposal_supplied": False,
                "packet_delta": {},
            }
        )
        composed_packet = self._composed_packet()
        original_composed = copy.deepcopy(composed_packet)

        result = finalize_recompiled_packet(
            {},
            state,
            previous_packet=previous_packet,
            composed_packet=composed_packet,
            previous_packet_id="packet-previous",
        )

        self.assertEqual(composed_packet, original_composed)
        self.assertFalse(result["ok"])
        packet = result["packet"]
        self.assertEqual(packet["composition_plan_status"], "stale_source_provenance")
        self.assertEqual(packet["active_atoms"], [])
        self.assertEqual(
            packet["composition_plan"]["composition_plan_id"],
            plan["composition_plan_id"],
        )
        errors = packet["composition_diagnostics"]["runtime_source_validation"][
            "errors"
        ]
        self.assertEqual(errors[0]["code"], "composition_source_content_changed")
        self.assertEqual(errors[0]["node_id"], "implement")

    def test_changed_composition_source_role_rejects_stale_graph_provenance(
        self,
    ) -> None:
        plan = composition_runtime_plan()
        runtime = advance_composition_runtime(plan, {})
        previous_packet = self._previous_packet()
        previous_packet.update(
            {
                "phase": "discovery",
                "active_atoms": ["research-atom"],
                "composition_plan": plan,
                "semantic_proposal_validation": {
                    "accepted": True,
                    "errors": [],
                    "warnings": [],
                },
                "evidence_citations": [
                    {
                        "source": f"skills/{node_id}/SKILL.md",
                        "source_role": "active_skill",
                        "content_digest": f"digest-{node_id}",
                        "relationship_citations": [f"slice-{node_id}"],
                    }
                    for node_id in ("research", "implement", "verify")
                ],
            }
        )
        source_nodes = self._composition_source_nodes()
        source_nodes[1] = {
            **source_nodes[1],
            "source_role": "supporting_reference",
            "activation_eligible": False,
        }
        state = self._state()
        state.update(
            {
                "phase": "discovery",
                "suggested_phase": "",
                "source_nodes": source_nodes,
                "composition_runtime": runtime,
                "semantic_proposal_supplied": False,
                "packet_delta": {},
            }
        )

        result = finalize_recompiled_packet(
            {},
            state,
            previous_packet=previous_packet,
            composed_packet=self._composed_packet(),
            previous_packet_id="packet-previous",
        )

        self.assertFalse(result["ok"])
        packet = result["packet"]
        self.assertEqual(packet["composition_plan_status"], "stale_source_provenance")
        self.assertEqual(packet["active_atoms"], [])
        errors = packet["composition_diagnostics"]["runtime_source_validation"][
            "errors"
        ]
        self.assertEqual(errors[0]["code"], "composition_source_role_changed")
        self.assertEqual(errors[0]["node_id"], "implement")
        self.assertEqual(errors[0]["expected_source_role"], "active_skill")
        self.assertEqual(errors[0]["actual_source_role"], "supporting_reference")

    def test_renamed_source_with_same_content_digest_rebinds_without_graph_change(
        self,
    ) -> None:
        plan = composition_runtime_plan()
        runtime = advance_composition_runtime(plan, {})
        previous_packet = self._previous_packet()
        previous_packet.update(
            {
                "phase": "discovery",
                "composition_plan": plan,
                "semantic_proposal_validation": {
                    "accepted": True,
                    "errors": [],
                    "warnings": [],
                },
                "evidence_citations": [
                    {
                        "source": f"skills/{node_id}/SKILL.md",
                        "source_role": "active_skill",
                        "content_digest": f"digest-{node_id}",
                        "relationship_citations": [f"slice-{node_id}"],
                    }
                    for node_id in ("research", "implement", "verify")
                ],
            }
        )
        source_nodes = self._composition_source_nodes()
        source_nodes[1] = {
            **source_nodes[1],
            "id": "implement-renamed",
            "relative_path": "skills/renamed-implement/SKILL.md",
            "path": "[REDACTED:path]/skills/renamed-implement/SKILL.md",
        }
        state = self._state()
        state.update(
            {
                "phase": "discovery",
                "suggested_phase": "",
                "source_nodes": source_nodes,
                "composition_runtime": runtime,
                "semantic_proposal_supplied": False,
                "packet_delta": {},
            }
        )

        result = finalize_recompiled_packet(
            {},
            state,
            previous_packet=previous_packet,
            composed_packet=self._composed_packet(),
            previous_packet_id="packet-previous",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["packet"]["composition_plan"]["provenance"],
            plan["provenance"],
        )
        self.assertIn(
            "skills/renamed-implement/SKILL.md",
            {item["source"] for item in result["packet"]["evidence_citations"]},
        )

    def test_explicit_project_recipe_plan_is_authoritative_on_recompile(self) -> None:
        previous_plan = composition_runtime_plan()
        recipe_plan = composition_runtime_plan()
        recipe_plan["composition_plan_id"] = "composition-reviewed-recipe"
        previous_packet = self._previous_packet()
        previous_packet["composition_plan"] = previous_plan
        source_nodes = self._composition_source_nodes()
        composed_packet = self._composed_packet()
        composed_packet.update(
            {
                "composition_plan": recipe_plan,
                "project_recipe": {"recipe_id": "reviewed-onboarding"},
                "semantic_proposal_validation": {
                    "accepted": True,
                    "errors": [],
                    "warnings": [],
                },
                "evidence_citations": [
                    {
                        "source": f"skills/{node_id}/SKILL.md",
                        "source_role": "active_skill",
                        "content_digest": f"digest-{node_id}",
                        "relationship_citations": [f"slice-{node_id}"],
                    }
                    for node_id in ("research", "implement", "verify")
                ],
            }
        )
        state = self._state()
        state.update(
            {
                "phase": "discovery",
                "suggested_phase": "",
                "source_nodes": source_nodes,
                "composition_runtime": advance_composition_runtime(previous_plan, {}),
                "runtime_evidence": {},
                "semantic_proposal_supplied": True,
                "packet_delta": {},
            }
        )

        result = finalize_recompiled_packet(
            {"project_recipe_id": "reviewed-onboarding"},
            state,
            previous_packet=previous_packet,
            composed_packet=composed_packet,
            previous_packet_id="packet-previous",
        )

        self.assertEqual(
            result["packet"]["composition_plan"]["composition_plan_id"],
            "composition-reviewed-recipe",
        )
        self.assertEqual(
            result["packet"]["project_recipe"]["recipe_id"],
            "reviewed-onboarding",
        )

    def test_semantic_recompile_carries_verified_handoff_evidence_on_same_graph(
        self,
    ) -> None:
        plan = handoff_runtime_plan()
        runtime = advance_composition_runtime(
            plan,
            {
                "requested_phase": "implementation",
                "gate_results": _passing_gates(),
                "handoff_results": [_handoff_result()],
            },
        )
        source_nodes = [
            {
                "id": node_id,
                "relative_path": f"skills/{node_id}/SKILL.md",
                "path": f"[REDACTED:path]/skills/{node_id}/SKILL.md",
                "source_type": "skill_definition",
                "source_role": "active_skill",
                "activation_eligible": True,
                "signal_excerpt": f"{node_id} workflow",
                "behavior_atoms": [f"{node_id}-atom"],
                "routing_metadata": {},
                "content_digest": f"digest-{node_id}",
            }
            for node_id in ("research", "implement")
        ]
        evidence_citations = [
            {
                "source": f"skills/{role['node_id']}/SKILL.md",
                "source_role": "active_skill",
                "content_digest": f"digest-{role['node_id']}",
                "relationship_citations": role["citations"],
            }
            for role in plan["skill_roles"]
        ]
        previous_packet = self._previous_packet()
        previous_packet.update(
            {
                "phase": "discovery",
                "composition_plan": plan,
                "semantic_proposal_validation": {"accepted": True},
                "evidence_citations": evidence_citations,
            }
        )
        composed_packet = self._composed_packet()
        composed_packet.update(
            {
                "composition_plan": handoff_runtime_plan(),
                "semantic_proposal_validation": {"accepted": True},
                "composition_diagnostics": {"preflight": {}},
                "evidence_citations": evidence_citations,
            }
        )
        original_composed = copy.deepcopy(composed_packet)
        state = self._state()
        state.update(
            {
                "phase": "discovery",
                "suggested_phase": "implementation",
                "source_nodes": source_nodes,
                "composition_runtime": runtime,
                "runtime_evidence": {},
                "semantic_proposal_supplied": True,
                "packet_delta": {},
            }
        )

        result = finalize_recompiled_packet(
            {"semantic_proposal": {"schema": "tmcp-semantic-proposal-v0.1"}},
            state,
            previous_packet=previous_packet,
            composed_packet=composed_packet,
            previous_packet_id="packet-previous",
        )

        self.assertEqual(composed_packet, original_composed)
        self.assertEqual(
            result["packet"]["composition_plan"]["runtime_state"][
                "available_handoff_ids"
            ],
            [HANDOFF_ID],
        )
        self.assertEqual(
            result["packet"]["receipt_template"]["handoff_results"][0]["status"],
            "available",
        )
        self.assertEqual(result["packet_diff"]["handoffs"]["available"], [HANDOFF_ID])
        self.assertIn(
            "handoff_results",
            result["composition_runtime"]["continuity"]["carried_fields"],
        )

    def test_recompile_service_has_no_adapter_storage_or_io_imports(self) -> None:
        source_path = Path(inspect.getfile(recompile_service))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "os",
            "pathlib",
            "shutil",
            "subprocess",
            "scripts",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "tmcp_runtime.services.harvest",
            "tmcp_runtime.services.promotion",
            "tmcp_runtime.services.recommendations",
            "tmcp_runtime.services.review",
        )

        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
