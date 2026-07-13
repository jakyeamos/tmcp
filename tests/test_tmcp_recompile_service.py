from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.recompile as recompile_service
from tmcp_runtime.services.recompile import finalize_recompiled_packet


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
                item["kind"] == "route"
                and item["id"] == "accessibility_validation"
                for item in result["packet_diff"]["added"]
            )
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
