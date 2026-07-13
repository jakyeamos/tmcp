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
