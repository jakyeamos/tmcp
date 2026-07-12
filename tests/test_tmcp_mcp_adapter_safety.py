from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.storage import ArtifactStorageError


class TmcpMcpAdapterSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_aios_adapter_explicit_missing_returns_clear_error(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp/tmcp-aios-definitely-missing"))
        try:
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["adapter"], "aios")
        self.assertIn("AIOS_ROOT", result["error"])
        self.assertIn("--adapter standalone", result["remediation"])

    def test_status_reports_aios_unconfigured_as_optional(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", None)
        try:
            result = self.server._call_tool("tmcp_status", {})
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertTrue(result["standalone"]["available"])
        self.assertFalse(result["aios_adapter"]["available"])
        self.assertFalse(result["aios_adapter"]["configured"])
        self.assertIsNone(result["aios_adapter"]["aios_root"])

    def test_aios_auto_missing_falls_back_to_standalone(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp/tmcp-aios-definitely-missing"))
        try:
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "auto",
                },
            )
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "standalone")
        self.assertEqual(result["packet"]["schema"], "tmcp-skill-packet-v0.2")

    def test_explain_aios_payloads_are_redacted_before_returning(self) -> None:
        secret = "sk-" + "B" * 40
        output_dir = f"/tmp/{secret}/aios-output"
        project_path = f"/tmp/{secret}/project"
        with patch.object(self.server, "_aios_available", return_value=True), patch.object(
            self.server,
            "_run_aios",
            return_value={
                "ok": True,
                "adapter": "aios",
                "detail": secret,
                "output_dir": output_dir,
                "artifact_paths": {"packet": output_dir},
            },
        ):
            success = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": project_path,
                    "adapter": "aios",
                    "compose": True,
                },
            )
        with patch.object(self.server, "_aios_available", return_value=True), patch.object(
            self.server,
            "_run_aios",
            return_value={
                "ok": False,
                "adapter": "aios",
                "command": ["aios", secret],
                "stdout": secret,
                "stderr": output_dir,
            },
        ):
            failure = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )

        self.assertTrue(success["ok"])
        self.assertFalse(failure["ok"])
        self.assertNotIn(secret, json.dumps({"success": success, "failure": failure}))
        self.assertNotIn(output_dir, json.dumps({"success": success, "failure": failure}))
        self.assertIn("redaction_summary", success)
        self.assertIn("redaction_summary", failure)

    def test_status_and_doctor_redact_sensitive_configured_paths(self) -> None:
        secret = "sk-" + "C" * 40
        original_aios_root = getattr(self.server, "AIOS_ROOT")
        original_plugin_root = getattr(self.server, "PLUGIN_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp") / secret / "aios")
        setattr(self.server, "PLUGIN_ROOT", Path("/tmp") / secret / "plugin")
        try:
            status = self.server._call_tool("tmcp_status", {})
            doctor = self.server._call_tool("tmcp_doctor", {"client": "codex"})
        finally:
            setattr(self.server, "AIOS_ROOT", original_aios_root)
            setattr(self.server, "PLUGIN_ROOT", original_plugin_root)

        rendered = json.dumps({"status": status, "doctor": doctor})
        self.assertNotIn(secret, rendered)
        self.assertIn("[REDACTED:", rendered)

    def test_explain_aios_timeout_returns_a_redacted_structured_error(self) -> None:
        secret = "sk-" + "D" * 40
        with patch.object(self.server, "_aios_available", return_value=True), patch.object(
            self.server.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["aios", secret], 120),
        ):
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "TimeoutExpired")
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("redaction_summary", result)

    def test_runtime_next_redacts_project_paths_after_internal_work(self) -> None:
        secret = "sk-" + "E" * 40
        project_path = f"/tmp/{secret}/project"
        delta = self.server._runtime_next(
            {
                "objective": "Implement a reliable project packet",
                "project_path": project_path,
                "source_path": project_path,
                "cache_policy": "none",
            }
        )
        full = self.server._runtime_next(
            {
                "objective": "Implement a reliable project packet",
                "project_path": project_path,
                "source_path": project_path,
                "cache_policy": "none",
                "output_mode": "full",
                "previous_packet": {
                    "packet_id": "prior-packet",
                    "project_path": project_path,
                },
            }
        )

        self.assertNotIn(secret, json.dumps({"delta": delta, "full": full}))
        self.assertIn("redaction_summary", delta)
        self.assertIn("redaction_summary", full)

    def test_runtime_next_requires_a_real_path_after_redacted_packet_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit source_path or project_path"):
            self.server._runtime_next(
                {
                    "objective": "Implement a reliable project packet",
                    "cache_policy": "none",
                    "output_mode": "full",
                    "previous_packet": {
                        "packet_id": "prior-packet",
                        "project_path": "/tmp/[REDACTED:opaque_token]/project",
                    },
                }
            )

    def test_review_auto_never_uses_the_aios_adapter(self) -> None:
        with patch.object(self.server, "_aios_available", return_value=True), patch.object(
            self.server,
            "_run_aios",
        ) as run_aios, patch.object(
            self.server,
            "artifact_persistence_available",
            return_value=False,
        ):
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": "Review release safety",
                    "project_path": "/tmp/project",
                    "harvest_sources": False,
                    "write_artifacts": False,
                },
            )

        run_aios.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "standalone")

    def test_review_explicit_aios_write_is_denied_before_external_execution(self) -> None:
        with patch.object(self.server, "_aios_available", return_value=True), patch.object(
            self.server,
            "_run_aios",
        ) as run_aios:
            with self.assertRaisesRegex(ArtifactStorageError, "write_artifacts=false"):
                self.server._call_tool(
                    "expert_rubric_review_plan",
                    {
                        "objective": "Review release safety",
                        "project_path": "/tmp/project",
                        "adapter": "aios",
                    },
                )

        run_aios.assert_not_called()

    def test_review_explicit_aios_missing_keeps_adapter_remediation(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp/tmcp-aios-definitely-missing"))
        try:
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": "Review release safety",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["adapter"], "aios")
        self.assertIn("--adapter standalone", result["remediation"])

    def test_review_explicit_aios_preview_redacts_and_omits_output_directory(self) -> None:
        secret = "sk-" + "A" * 40
        output_dir = f"/tmp/{secret}/review"
        with patch.object(self.server, "_aios_available", return_value=True), patch.object(
            self.server,
            "_run_aios",
            return_value={
                "ok": True,
                "adapter": "aios",
                "detail": secret,
                "output_dir": output_dir,
                "artifact_paths": {"report": output_dir},
            },
        ) as run_aios:
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": f"Review {secret}",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                    "write_artifacts": False,
                    "output_dir": output_dir,
                },
            )

        command = run_aios.call_args.args[0]
        self.assertIn("--no-write-artifacts", command)
        self.assertNotIn("--output-dir", command)
        self.assertNotIn(output_dir, command)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("output_dir", result)
        self.assertEqual(result["artifact_paths"], {})

    def test_status_omits_artifact_write_when_secure_persistence_is_unavailable(
        self,
    ) -> None:
        with patch.object(
            self.server,
            "artifact_persistence_available",
            return_value=False,
        ):
            result = self.server._call_tool("tmcp_status", {})

        standalone = result["standalone"]
        self.assertFalse(standalone["artifact_persistence"]["available"])
        self.assertNotIn("artifact_write", standalone["capabilities"])


if __name__ == "__main__":
    unittest.main()
