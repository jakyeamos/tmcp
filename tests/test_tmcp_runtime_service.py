from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.runtime as runtime_service
from tmcp_runtime.services.runtime import RuntimeService, RuntimeServiceContext


class RuntimeServiceTests(unittest.TestCase):
    def test_state_acquisition_is_supplied_by_context_callbacks(self) -> None:
        calls: list[str] = []

        def source_exists(path: str) -> bool:
            calls.append(f"exists:{path}")
            return True

        def load_source_nodes(arguments: dict[str, object]) -> list[dict[str, object]]:
            calls.append(f"harvest:{arguments['objective']}")
            return []

        def load_cache_warnings(cache_policy: str) -> list[str]:
            calls.append(f"cache:{cache_policy}")
            return ["cache warning"]

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=source_exists,
                load_source_nodes=load_source_nodes,
                load_cache_warnings=load_cache_warnings,
                compose_packet=lambda arguments: dict(arguments),
            )
        )

        state = service.build_state(
            {
                "objective": "Implement onboarding",
                "project_path": "/project",
                "cache_policy": "global",
            }
        )

        self.assertEqual(
            calls,
            ["exists:/project", "harvest:Implement onboarding", "cache:global"],
        )
        self.assertEqual(state["cache_policy"], "global")
        self.assertIn("cache warning", state["warnings"])

    def test_state_acquisition_falls_back_to_previous_packet_project_path(self) -> None:
        loaded_arguments: dict[str, object] = {}

        def load_source_nodes(arguments: dict[str, object]) -> list[dict[str, object]]:
            loaded_arguments.update(arguments)
            return []

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: path == "/previous-project",
                load_source_nodes=load_source_nodes,
                load_cache_warnings=lambda cache_policy: [],
                compose_packet=lambda arguments: dict(arguments),
            )
        )

        state = service.build_state(
            {
                "objective": "Implement onboarding",
                "previous_packet": {"project_path": "/previous-project"},
                "cache_policy": "none",
            }
        )

        self.assertEqual(loaded_arguments["source_path"], "/previous-project")
        self.assertEqual(loaded_arguments["project_path"], "/previous-project")
        self.assertEqual(state["project_path"], "/previous-project")

    def test_state_acquisition_loads_explicit_multi_root_source_paths(self) -> None:
        calls: list[str] = []
        loaded_arguments: dict[str, object] = {}

        def source_exists(path: str) -> bool:
            calls.append(path)
            return path == "/project-b"

        def load_source_nodes(arguments: dict[str, object]) -> list[dict[str, object]]:
            loaded_arguments.update(arguments)
            return []

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=source_exists,
                load_source_nodes=load_source_nodes,
                load_cache_warnings=lambda cache_policy: [],
                compose_packet=lambda arguments: dict(arguments),
            )
        )

        service.build_state(
            {
                "objective": "Compose across project and shared skills",
                "source_paths": ["/project-a", "/project-b"],
                "previous_packet": {"project_path": "[REDACTED:path]"},
            }
        )

        self.assertEqual(calls, ["/project-a", "/project-b"])
        self.assertEqual(loaded_arguments["source_paths"], ["/project-a", "/project-b"])

    def test_recompile_composition_is_supplied_by_context(self) -> None:
        composed_arguments: dict[str, object] = {}

        def compose_packet(arguments: dict[str, object]) -> dict[str, object]:
            composed_arguments.update(arguments)
            return {
                "packet_id": "new-packet",
                "objective": arguments["objective"],
                "project_path": arguments["project_path"],
                "phase": arguments["phase"],
                "active_atoms": [],
                "deferred_atoms": [],
                "required_reads": [],
                "verification_gates": [],
                "family_context": {},
                "active_instructions": [],
                "evidence_citations": [],
                "task_identity": {},
            }

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: True,
                load_source_nodes=lambda arguments: [],
                load_cache_warnings=lambda cache_policy: [],
                compose_packet=compose_packet,
            )
        )
        state = {
            "objective": "Implement onboarding",
            "combined_objective": "Implement onboarding",
            "project_path": "/project",
            "phase": "runtime",
            "suggested_phase": "implementation",
            "cache_policy": "none",
            "context": {"files_changed": ["app/page.tsx"]},
            "latest_user_message": "",
            "source_nodes": [],
            "packet_delta": {},
            "next_verification_gate": [],
            "task_identity": {},
            "task_identity_delta": None,
            "proposed_changes": [],
            "validated_changes": [],
            "warnings": [],
        }

        result = service.recompile(
            {
                "project_path": "/project",
                "files_changed": ["app/page.tsx"],
                "previous_packet": {
                    "packet_id": "old-packet",
                    "project_path": "/project",
                    "phase": "runtime",
                    "active_atoms": [],
                    "task_identity": {},
                },
            },
            state,
        )

        self.assertEqual(composed_arguments["phase"], "implementation")
        self.assertEqual(
            composed_arguments["runtime_context"],
            {"files_changed": ["app/page.tsx"]},
        )
        self.assertEqual(result["previous_packet_id"], "old-packet")

    def test_recompile_uses_gate_resolved_graph_phase(self) -> None:
        composed_arguments: dict[str, object] = {}

        def compose_packet(arguments: dict[str, object]) -> dict[str, object]:
            composed_arguments.update(arguments)
            return {
                "packet_id": "new-packet",
                "phase": arguments["phase"],
                "active_atoms": [],
                "deferred_atoms": [],
                "required_reads": [],
                "verification_gates": [],
                "family_context": {},
                "task_identity": {},
            }

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: True,
                load_source_nodes=lambda arguments: [],
                load_cache_warnings=lambda cache_policy: [],
                compose_packet=compose_packet,
            )
        )
        state = {
            "objective": "Implement onboarding",
            "combined_objective": "Implement onboarding",
            "project_path": "/project",
            "phase": "runtime",
            "suggested_phase": "implementation",
            "composition_runtime": {"current_phase": "runtime"},
            "semantic_proposal_supplied": True,
            "cache_policy": "none",
            "context": {},
            "packet_delta": {},
        }

        proposal = {
            "schema": "tmcp-semantic-proposal-v0.1",
            "current_phase": "verification",
        }
        service.recompile(
            {
                "project_path": "/project",
                "previous_packet": {
                    "packet_id": "old-packet",
                    "project_path": "/project",
                    "phase": "runtime",
                },
                "semantic_proposal": proposal,
                "max_total_tokens": 2400,
            },
            state,
        )

        self.assertEqual(composed_arguments["phase"], "runtime")
        self.assertEqual(composed_arguments["semantic_proposal"], proposal)
        self.assertEqual(composed_arguments["max_total_tokens"], 2400)

    def test_explicit_semantic_proposal_is_forwarded_for_fresh_recomposition(
        self,
    ) -> None:
        composed_arguments: dict[str, object] = {}

        def compose_packet(arguments: dict[str, object]) -> dict[str, object]:
            composed_arguments.update(arguments)
            return {
                "ok": False,
                "packet_id": "rejected-packet",
                "phase": arguments["phase"],
                "active_atoms": [],
                "deferred_atoms": [],
                "required_reads": [],
                "verification_gates": [],
                "family_context": {},
                "task_identity": {},
                "composition_plan": None,
                "semantic_proposal_validation": {"accepted": False},
            }

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: True,
                load_source_nodes=lambda arguments: [],
                load_cache_warnings=lambda cache_policy: [],
                compose_packet=compose_packet,
            )
        )
        proposal = {
            "schema": "tmcp-semantic-proposal-v0.1",
            "current_phase": "verification",
        }
        state = {
            "objective": "Verify onboarding",
            "combined_objective": "Verify onboarding",
            "project_path": "/project",
            "phase": "runtime",
            "suggested_phase": "implementation",
            "semantic_proposal_supplied": True,
            "runtime_evidence": {},
            "cache_policy": "none",
            "context": {},
            "packet_delta": {},
        }

        result = service.recompile(
            {
                "project_path": "/project",
                "previous_packet": {
                    "packet_id": "old-packet",
                    "project_path": "/project",
                    "phase": "runtime",
                },
                "semantic_proposal": proposal,
            },
            state,
        )

        self.assertEqual(composed_arguments["phase"], "verification")
        self.assertEqual(composed_arguments["semantic_proposal"], proposal)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["packet"]["composition_plan"])

    def test_explicit_project_recipe_id_is_forwarded_for_recomposition(self) -> None:
        composed_arguments: dict[str, object] = {}

        def compose_packet(arguments: dict[str, object]) -> dict[str, object]:
            composed_arguments.update(arguments)
            return {
                "packet_id": "recipe-packet",
                "phase": arguments["phase"],
                "active_atoms": [],
                "deferred_atoms": [],
                "required_reads": [],
                "verification_gates": [],
                "family_context": {},
                "task_identity": {},
                "composition_plan": None,
            }

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: True,
                load_source_nodes=lambda arguments: [],
                load_cache_warnings=lambda cache_policy: [],
                compose_packet=compose_packet,
            )
        )
        state = {
            "objective": "Implement onboarding",
            "combined_objective": "Implement onboarding",
            "project_path": "/project",
            "phase": "runtime",
            "semantic_proposal_supplied": True,
            "runtime_evidence": {},
            "cache_policy": "project",
            "context": {},
            "packet_delta": {},
        }

        service.recompile(
            {
                "project_path": "/project",
                "previous_packet": {
                    "packet_id": "old-packet",
                    "project_path": "/project",
                    "phase": "runtime",
                },
                "project_recipe_id": "reviewed-onboarding",
            },
            state,
        )

        self.assertEqual(composed_arguments["project_recipe_id"], "reviewed-onboarding")

    def test_recompile_accepts_multi_root_paths_with_redacted_previous_path(
        self,
    ) -> None:
        composed_arguments: dict[str, object] = {}

        def compose_packet(arguments: dict[str, object]) -> dict[str, object]:
            composed_arguments.update(arguments)
            return {
                "packet_id": "multi-root-packet",
                "project_path": arguments["project_path"],
                "phase": arguments["phase"],
                "active_atoms": [],
                "deferred_atoms": [],
                "required_reads": [],
                "verification_gates": [],
                "family_context": {},
                "task_identity": {},
            }

        service = RuntimeService(
            RuntimeServiceContext(
                source_exists=lambda path: True,
                load_source_nodes=lambda arguments: [],
                load_cache_warnings=lambda cache_policy: [],
                compose_packet=compose_packet,
            )
        )
        state = {
            "objective": "Compose across project and shared skills",
            "combined_objective": "Compose across project and shared skills",
            "project_path": ".",
            "phase": "runtime",
            "cache_policy": "none",
            "context": {},
            "packet_delta": {},
        }

        result = service.recompile(
            {
                "source_paths": ["/project", "/shared-skills"],
                "previous_packet": {
                    "packet_id": "old-packet",
                    "project_path": "[REDACTED:path]",
                    "phase": "runtime",
                },
            },
            state,
        )

        self.assertEqual(
            composed_arguments["source_paths"], ["/project", "/shared-skills"]
        )
        self.assertEqual(result["previous_packet_id"], "old-packet")

    def test_runtime_service_has_no_filesystem_or_transport_authority(self) -> None:
        source_path = Path(inspect.getfile(runtime_service))
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
