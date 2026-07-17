from __future__ import annotations

import unittest

from tests import test_tmcp_mcp_server as helpers


class TmcpDoctorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_doctor_reports_codex_tool_discovery_fallback(self) -> None:
        result = self.server._call_tool("tmcp_doctor", {"client": "codex"})

        self.assertTrue(result["ok"])
        discovery = result["codex_tool_discovery"]
        self.assertIn("tool_search", discovery["symptom"])
        self.assertIn(
            "tmcp list-tools",
            discovery["verify_launcher"],
        )
        config = discovery["codex_mcp_config"]["mcp_servers"]["tmcp"]
        self.assertEqual(config["command"], "node")
        self.assertEqual(config["args"], ["scripts/tmcp_launcher.mjs"])
        self.assertEqual(config["cwd"], result["plugin_root"])
        check_ids = {check["id"] for check in result["checks"]}
        self.assertIn("secure_artifact_persistence", check_ids)


if __name__ == "__main__":
    unittest.main()
