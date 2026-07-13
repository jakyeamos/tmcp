from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from typing import Any, cast

import tmcp_runtime.services.sessions as sessions_service
from tmcp_runtime.services.sessions import RuntimeSessionService


class _Snapshot:
    def __init__(self) -> None:
        self.packet: dict[str, Any] = {
            "packet_id": "old-packet",
            "project_path": "/project",
        }

    def metadata(self) -> dict[str, Any]:
        return {"revision": 2, "packet_id": "new-packet"}


class _Store:
    project_root = Path("/project")

    def __init__(self) -> None:
        self.snapshot = _Snapshot()
        self.update_arguments: dict[str, object] = {}

    def load(self) -> _Snapshot:
        return self.snapshot

    def update(
        self,
        snapshot: _Snapshot,
        packet: dict[str, Any],
        *,
        last_recompile: dict[str, Any],
        now: str,
    ) -> _Snapshot:
        self.update_arguments = {
            "snapshot": snapshot,
            "packet": packet,
            "last_recompile": last_recompile,
            "now": now,
        }
        return self.snapshot


class RuntimeSessionServiceTests(unittest.TestCase):
    def test_full_session_flow_uses_injected_store_and_runtime_callbacks(self) -> None:
        store = _Store()
        build_arguments: dict[str, object] = {}
        recompile_arguments: dict[str, object] = {}

        def build_state(arguments: dict[str, object]) -> dict[str, object]:
            build_arguments.update(arguments)
            return {
                "objective": "Implement onboarding",
                "project_path": "/project",
                "phase": "runtime",
                "suggested_phase": "implementation",
                "task_identity": {},
                "task_identity_delta": None,
                "packet_delta": {},
                "next_verification_gate": [],
                "warnings": [],
            }

        def recompile_packet(
            arguments: dict[str, object], state: dict[str, object]
        ) -> dict[str, object]:
            recompile_arguments.update(arguments)
            return {
                "packet": {"packet_id": "new-packet"},
                "previous_packet_id": "old-packet",
                "recompile_reason": "phase_transition",
            }

        service = RuntimeSessionService(
            open_store=lambda project_path, session_id: store,
            build_state=build_state,
            recompile_packet=recompile_packet,
            now_iso=lambda: "2026-07-13T12:00:00Z",
        )

        result = service.run(
            {
                "session_id": "run-1",
                "project_path": "/project",
                "output_mode": "full",
            }
        )

        self.assertEqual(build_arguments["previous_packet_id"], "old-packet")
        self.assertEqual(build_arguments["project_path"], str(store.project_root))
        previous_packet = cast(dict[str, Any], recompile_arguments["previous_packet"])
        self.assertEqual(previous_packet["packet_id"], "old-packet")
        session = cast(dict[str, Any], result["session"])
        self.assertEqual(session, {"revision": 2, "packet_id": "new-packet"})
        self.assertEqual(store.update_arguments["now"], "2026-07-13T12:00:00Z")

    def test_session_mode_rejects_inline_previous_packet(self) -> None:
        service = RuntimeSessionService(
            open_store=lambda project_path, session_id: _Store(),
            build_state=lambda arguments: {},
            recompile_packet=lambda arguments, state: {},
            now_iso=lambda: "now",
        )

        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            service.run(
                {
                    "session_id": "run-1",
                    "project_path": "/project",
                    "output_mode": "full",
                    "previous_packet": {},
                }
            )

    def test_session_service_has_no_storage_or_transport_imports(self) -> None:
        source_path = Path(inspect.getfile(sessions_service))
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
