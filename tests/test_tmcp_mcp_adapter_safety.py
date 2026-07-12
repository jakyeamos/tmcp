from __future__ import annotations

import json
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
