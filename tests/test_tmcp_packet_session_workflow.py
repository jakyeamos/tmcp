from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tests.tmcp_test_client import TestWorkspace
from tmcp_runtime.storage import PacketSessionError, PacketSessionStore, artifact_persistence_available


class PacketSessionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_compose_and_recompile_stay_inside_the_explicit_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            source = root / "source"
            project.mkdir()
            source.mkdir()
            (source / "AGENTS.md").write_text(
                "Use pnpm and verify the release package.\n", encoding="utf-8"
            )
            session_id = "release-run-private"
            compose = self.server._compose_packet(
                {
                    "objective": "Improve release readiness",
                    "project_path": str(project),
                    "source_path": str(source),
                    "phase": "start",
                    "cache_policy": "none",
                    "session_id": session_id,
                }
            )
            store = PacketSessionStore.open(project, session_id)
            stored_after_compose = store.load()
            recompiled = self.server._runtime_next(
                {
                    "objective": "Improve release readiness",
                    "project_path": str(project),
                    "source_path": str(source),
                    "current_phase": "verification",
                    "files_changed": ["scripts/check_release_package.py"],
                    "output_mode": "full",
                    "cache_policy": "none",
                    "session_id": session_id,
                }
            )
            stored_after_recompile = store.load()
            serialized = store.path.read_text(encoding="utf-8")
            session_path_exists = store.path.exists()
            source_has_session_directory = (source / ".tmcp").exists()

        self.assertEqual(compose["session"]["record_schema"], "tmcp-run-session-v0.1")
        self.assertEqual(compose["session"]["revision"], 1)
        self.assertEqual(stored_after_compose.packet["packet_id"], compose["packet_id"])
        self.assertEqual(recompiled["schema"], "tmcp-recompiled-packet-v0.1")
        self.assertEqual(recompiled["previous_packet_id"], compose["packet_id"])
        self.assertEqual(recompiled["session"]["revision"], 2)
        self.assertEqual(stored_after_recompile.revision, 2)
        self.assertEqual(
            stored_after_recompile.record["last_recompile"]["updated_at"],
            stored_after_recompile.record["updated_at"],
        )
        self.assertTrue(session_path_exists)
        self.assertFalse(source_has_session_directory)
        self.assertNotIn(session_id, serialized)

    def test_sessions_are_opt_in_and_require_a_project_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            self.server._compose_packet(
                {
                    "objective": "Improve release readiness",
                    "project_path": str(project),
                    "source_path": str(project),
                    "cache_policy": "none",
                }
            )
            self.assertFalse((project / ".tmcp" / "runs").exists())

            with self.assertRaises(ValueError):
                self.server._compose_packet(
                    {
                        "objective": "Improve release readiness",
                        "source_path": str(project),
                        "cache_policy": "none",
                        "session_id": "run-1",
                    }
                )
            with self.assertRaises(ValueError):
                self.server._compose_packet(
                    {
                        "objective": "Improve release readiness",
                        "project_path": ".",
                        "source_path": str(project),
                        "cache_policy": "none",
                        "session_id": "run-1",
                    }
                )
            with self.assertRaises(ValueError):
                self.server._runtime_next(
                    {
                        "objective": "Improve release readiness",
                        "project_path": str(project),
                        "session_id": "run-1",
                        "output_mode": "delta",
                        "cache_policy": "none",
                    }
                )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_session_recompile_rejects_an_inline_previous_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            composed = self.server._compose_packet(
                {
                    "objective": "Improve release readiness",
                    "project_path": str(project),
                    "source_path": str(project),
                    "cache_policy": "none",
                    "session_id": "run-1",
                }
            )

            with self.assertRaises(ValueError):
                self.server._runtime_next(
                    {
                        "objective": "Improve release readiness",
                        "project_path": str(project),
                        "output_mode": "full",
                        "cache_policy": "none",
                        "session_id": "run-1",
                        "previous_packet": composed,
                    }
                )

            store = PacketSessionStore.open(project, "run-1")
            self.assertEqual(store.load().revision, 1)
            with self.assertRaises(ValueError):
                self.server._runtime_next(
                    {
                        "objective": "Improve release readiness",
                        "project_path": str(project),
                        "output_mode": "full",
                        "cache_policy": "none",
                        "session_id": "run-1",
                        "previous_packet_id": "forged-packet-id",
                    }
                )
            self.assertEqual(store.load().revision, 1)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_mcp_transport_recompiles_a_project_local_session(self) -> None:
        with TestWorkspace() as workspace:
            if workspace.project is None:
                self.fail("Test workspace did not create a project.")
            project = str(workspace.project)
            responses = workspace.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "tmcp_compose_packet",
                            "arguments": {
                                "objective": "Improve release readiness",
                                "project_path": project,
                                "source_path": project,
                                "cache_policy": "none",
                                "session_id": "opaque-session-id-39",
                            },
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "tmcp_runtime_next",
                            "arguments": {
                                "objective": "Improve release readiness",
                                "project_path": project,
                                "source_path": project,
                                "current_phase": "verification",
                                "output_mode": "full",
                                "cache_policy": "none",
                                "session_id": "opaque-session-id-39",
                            },
                        },
                    },
                ]
            )

            compose = responses[0]["result"]["structuredContent"]
            recompiled = responses[1]["result"]["structuredContent"]
            store = PacketSessionStore.open(project, "opaque-session-id-39")
            stored = store.load()

        self.assertEqual(compose["session"]["revision"], 1)
        self.assertEqual(recompiled["session"]["revision"], 2)
        self.assertEqual(stored.revision, 2)
        self.assertNotIn("opaque-session-id-39", json.dumps(stored.record))

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_cli_sessions_require_an_absolute_target_path(self) -> None:
        with TestWorkspace() as workspace:
            if workspace.project is None or workspace.source is None:
                self.fail("Test workspace did not create source and project directories.")
            launcher = str(helpers.PLUGIN_ROOT / "scripts" / "tmcp_launcher.mjs")
            environment = workspace.environment()
            relative = subprocess.run(
                [
                    "node",
                    launcher,
                    "compose-packet",
                    "Improve release readiness",
                    "--project-path",
                    ".",
                    "--source-path",
                    str(workspace.project),
                    "--cache-policy",
                    "none",
                    "--session-id",
                    "relative-run",
                    "--compact",
                ],
                cwd=workspace.source,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            absolute = subprocess.run(
                [
                    "node",
                    launcher,
                    "compose-packet",
                    "Improve release readiness",
                    "--project-path",
                    str(workspace.project),
                    "--source-path",
                    str(workspace.project),
                    "--cache-policy",
                    "none",
                    "--session-id",
                    "absolute-run",
                    "--compact",
                ],
                cwd=workspace.source,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            store = PacketSessionStore.open(workspace.project, "absolute-run")
            absolute_payload = json.loads(absolute.stdout)
            session_path_exists = store.path.exists()

        self.assertNotEqual(relative.returncode, 0)
        self.assertIn("absolute project_path", relative.stdout + relative.stderr)
        self.assertEqual(absolute.returncode, 0, absolute.stderr)
        self.assertEqual(absolute_payload["session"]["revision"], 1)
        self.assertTrue(session_path_exists)

    def test_missing_session_fails_without_creating_a_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            with self.assertRaises(PacketSessionError):
                self.server._runtime_next(
                    {
                        "objective": "Improve release readiness",
                        "project_path": str(project),
                        "output_mode": "full",
                        "cache_policy": "none",
                        "session_id": "missing-run",
                    }
                )

            self.assertFalse((project / ".tmcp" / "runs").exists())


if __name__ == "__main__":
    unittest.main()
