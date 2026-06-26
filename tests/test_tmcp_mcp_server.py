from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tmcp_mcp_server.py"
PLUGIN_ROOT = SERVER_PATH.parents[1]
LAUNCHER_PATH = PLUGIN_ROOT / "scripts" / "tmcp_launcher.mjs"
GOLDEN_PACKETS_PATH = PLUGIN_ROOT / "tests" / "fixtures" / "golden_packets.json"
PACKET_SCHEMA_PATH = PLUGIN_ROOT / "schemas" / "tmcp-skill-packet-v0.2.schema.json"


def load_server_module():
    spec = importlib.util.spec_from_file_location("tmcp_mcp_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load tmcp_mcp_server module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_framing_module():
    path = PLUGIN_ROOT / "scripts" / "tmcp_mcp_framing.py"
    spec = importlib.util.spec_from_file_location("tmcp_mcp_framing", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load tmcp_mcp_framing module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_mcp_requests(requests: list[dict[str, object]]) -> list[dict[str, object]]:
    raw = b""
    framing = load_framing_module()
    for request in requests:
        raw += framing.encode_message(request)
    env = os.environ.copy()
    env["AIOS_ROOT"] = "/tmp/tmcp-aios-missing"
    completed = subprocess.run(
        ["node", str(LAUNCHER_PATH)],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(SERVER_PATH.parents[1]),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode())
    responses: list[dict[str, object]] = []
    stream = completed.stdout
    position = 0
    while position < len(stream):
        header_end = stream.index(b"\r\n\r\n", position)
        headers = stream[position:header_end].decode().split("\r\n")
        length = int(
            [
                header.split(":", 1)[1].strip()
                for header in headers
                if header.lower().startswith("content-length:")
            ][0]
        )
        start = header_end + 4
        responses.append(json.loads(stream[start : start + length]))
        position = start + length
    return responses


class TmcpMcpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = load_server_module()

    def test_expert_ui_rubric_routes_to_audit_packet(self) -> None:
        packet = self.server._compile_standalone_packet(
            objective="Use the TMCP expert UI rubric on Hoopscout",
            project_path="/tmp/hoopscout",
        )

        self.assertEqual(packet["task_id"], "audit")
        self.assertIn("@task:audit", packet["selected_nodes"])
        rubric = self.server._synthesize_rubric(packet, "run-test", packet["objective"])
        self.assertEqual(rubric["profile"], "visual_polish")

    def test_harvest_is_portable_and_prunes_dependency_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / ".github").mkdir()
            (root / ".cursor" / "rules").mkdir(parents=True)
            (root / "node_modules" / "ignored").mkdir(parents=True)
            (root / "AGENTS.md").write_text(
                "# Agent Contract\n\nRead before modifying. Verify with tests.\n",
                encoding="utf-8",
            )
            (root / "docs" / "workflow.md").write_text(
                "# Release Workflow\n\nUse evidence and artifacts.\n",
                encoding="utf-8",
            )
            (root / ".github" / "pull_request_template.md").write_text(
                "# PR\n\nRun quality checks.\n",
                encoding="utf-8",
            )
            (root / ".cursor" / "rules" / "ui.md").write_text(
                "---\ndescription: UI rule\n---\nUse screenshots as evidence.\n",
                encoding="utf-8",
            )
            (root / "node_modules" / "ignored" / "README.md").write_text(
                "# Ignore me\n",
                encoding="utf-8",
            )

            result = self.server._harvest_skills(
                {
                    "source_paths": [str(root), str(root / "missing")],
                    "objective": "Harvest portable project skill behavior",
                    "limit": 20,
                }
            )

        self.assertEqual(result["source_count"], 4)
        rel_paths = {node["relative_path"] for node in result["source_nodes"]}
        self.assertIn("AGENTS.md", rel_paths)
        self.assertIn(".cursor/rules/ui.md", rel_paths)
        self.assertNotIn("node_modules/ignored/README.md", rel_paths)
        source_types = {node["source_type"] for node in result["source_nodes"]}
        self.assertIn("agent_operating_contract", source_types)
        self.assertIn("cursor_rule", source_types)
        self.assertTrue(any("missing" in warning for warning in result["warnings"]))

    def test_harvest_redacts_sensitive_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = "sk-" + "A" * 40
            github_token = "ghp_" + "b" * 36
            aws_key = "AKIA" + "C" * 16
            high_entropy = "D" * 48
            (root / "AGENTS.md").write_text(
                "\n".join(
                    [
                        "# Agent Contract",
                        f"OPENAI_API_KEY={secret}",
                        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
                        f"GITHUB_TOKEN={github_token}",
                        f"AWS_ACCESS_KEY_ID={aws_key}",
                        "CLIENT_SECRET=supersecretvalue",
                        f"opaque={high_entropy}",
                        "-----BEGIN PRIVATE KEY-----",
                        "abcdef0123456789abcdef0123456789abcdef0123456789",
                        "-----END PRIVATE KEY-----",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._harvest_skills({"source_path": str(root), "limit": 10})

        serialized = json.dumps(result)
        for sensitive_value in (
            secret,
            github_token,
            aws_key,
            high_entropy,
            "supersecretvalue",
            "abcdef0123456789abcdef0123456789abcdef0123456789",
            "abcdefghijklmnopqrstuvwxyz123456",
        ):
            self.assertNotIn(sensitive_value, serialized)
        self.assertIn("[REDACTED:", serialized)
        self.assertGreater(sum(result["redaction_summary"].values()), 0)

    def test_review_plan_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "review"
            result = self.server._standalone_review_plan(
                {
                    "objective": "Use the TMCP expert UI rubric on Hoopscout",
                    "project_path": tmp,
                    "output_dir": str(output_dir),
                    "evidence_json": json.dumps(
                        [
                            {
                                "dimension_id": "surface_hierarchy",
                                "severity": "warning",
                                "summary": "Cards compete with the primary workflow.",
                                "evidence": ["src/app/page.tsx"],
                                "recommended_fix": "Rework hierarchy around the primary task.",
                            }
                        ]
                    ),
                }
            )

            self.assertEqual(result["rubric"]["profile"], "visual_polish")
            self.assertEqual(len(result["remediation_slices"]), 1)
            expected = {
                "expertise-packet.json",
                "rubric.json",
                "rubric.md",
                "audit-report.json",
                "audit-report.md",
                "remediation-plan.json",
                "remediation-plan.md",
                "implementation-handoff.json",
            }
            self.assertEqual({path.name for path in output_dir.iterdir()}, expected)

    def test_mcp_protocol_lists_and_calls_tools(self) -> None:
        responses = run_mcp_requests(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "tmcp_status", "arguments": {}},
                },
            ]
        )

        tools_result = responses[0]["result"]
        self.assertIsInstance(tools_result, dict)
        tool_names = {
            tool["name"]
            for tool in tools_result["tools"]  # type: ignore[index]
        }
        self.assertEqual(
            tool_names,
            {
                "expert_rubric_review_plan",
                "tmcp_doctor",
                "tmcp_explain",
                "tmcp_harvest_skills",
                "tmcp_status",
            },
        )
        status_result = responses[1]["result"]
        self.assertIsInstance(status_result, dict)
        structured = status_result["structuredContent"]  # type: ignore[index]
        self.assertTrue(structured["standalone"]["available"])  # type: ignore[index]

    def test_doctor_reports_first_run_readiness(self) -> None:
        result = self.server._call_tool("tmcp_doctor", {"client": "plain_mcp"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-doctor-v0.1")
        check_ids = {check["id"] for check in result["checks"]}
        self.assertIn("node_launcher", check_ids)
        self.assertIn("node_runtime", check_ids)
        self.assertIn("python_server", check_ids)
        self.assertEqual(result["smoke_test"]["tool"], "tmcp_status")

    def test_packet_schema_required_fields_match_compiled_packet(self) -> None:
        schema = json.loads(PACKET_SCHEMA_PATH.read_text(encoding="utf-8"))
        packet = self.server._compile_standalone_packet(
            objective="Plan a release readiness roadmap for the plugin",
            project_path="/tmp/project",
        )

        self.assertEqual(schema["properties"]["schema"]["const"], packet["schema"])
        missing = [field for field in schema["required"] if field not in packet]
        self.assertEqual(missing, [])

    def test_clean_copy_install_check_passes_without_aios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "tmcp"
            shutil.copytree(
                PLUGIN_ROOT,
                copied,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            completed = subprocess.run(
                ["python3", "scripts/check_install.py", "."],
                cwd=copied,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["manifest"], "pass")
        self.assertEqual(payload["mcp_launch"], "pass")

    def test_launcher_prefers_windows_python_launcher_on_windows(self) -> None:
        completed = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                (
                    "import { pythonCandidates } from './scripts/tmcp_launcher.mjs';"
                    "console.log(JSON.stringify(pythonCandidates({}, 'win32')));"
                ),
            ],
            cwd=PLUGIN_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        candidates = json.loads(completed.stdout)
        self.assertEqual(candidates[0]["command"], "py")
        self.assertEqual(candidates[0]["args"], ["-3"])

    def test_launcher_respects_explicit_python_env(self) -> None:
        completed = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                (
                    "import { pythonCandidates } from './scripts/tmcp_launcher.mjs';"
                    "console.log(JSON.stringify(pythonCandidates({ TMCP_PYTHON: '/opt/Python 3/python.exe' }, 'win32')));"
                ),
            ],
            cwd=PLUGIN_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        candidates = json.loads(completed.stdout)
        self.assertEqual(candidates[0]["command"], "/opt/Python 3/python.exe")
        self.assertEqual(candidates[0]["source"], "TMCP_PYTHON")

    def test_mcp_protocol_rejects_invalid_arguments(self) -> None:
        responses = run_mcp_requests(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "tmcp_status", "arguments": []},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "missing_tool", "arguments": {}},
                },
            ]
        )

        self.assertEqual(responses[0]["error"]["code"], -32602)  # type: ignore[index]
        self.assertEqual(responses[1]["error"]["code"], -32000)  # type: ignore[index]

    def test_golden_packet_routes_and_profiles(self) -> None:
        cases = json.loads(GOLDEN_PACKETS_PATH.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(objective=case["objective"]):
                packet = self.server._compile_standalone_packet(
                    objective=case["objective"],
                    project_path="/tmp/project",
                )
                rubric = self.server._synthesize_rubric(
                    packet,
                    "run-golden",
                    case["objective"],
                )
                self.assertEqual(packet["task_id"], case["task_id"])
                self.assertEqual(rubric["profile"], case["profile"])
                for node in case["required_nodes"]:
                    self.assertIn(node, packet["selected_nodes"])

    def test_review_plan_no_evidence_creates_gap_slice(self) -> None:
        result = self.server._standalone_review_plan(
            {
                "objective": "Review developer onboarding commands and CLI docs",
                "project_path": "/tmp/project",
                "write_artifacts": False,
                "evidence_json": "[]",
            }
        )

        self.assertEqual(result["rubric"]["profile"], "developer_experience")
        self.assertTrue(result["audit_report"]["deferred_scope"])
        self.assertEqual(result["remediation_slices"][0]["id"], "slice-1")
        self.assertIn("Collect missing evidence", result["remediation_slices"][0]["title"])

    def test_aios_adapter_explicit_missing_returns_clear_error(self) -> None:
        original_root = self.server.AIOS_ROOT
        self.server.AIOS_ROOT = Path("/tmp/tmcp-aios-definitely-missing")
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
            self.server.AIOS_ROOT = original_root

        self.assertFalse(result["ok"])
        self.assertEqual(result["adapter"], "aios")
        self.assertIn("AIOS_ROOT", result["error"])

    def test_aios_auto_missing_falls_back_to_standalone(self) -> None:
        original_root = self.server.AIOS_ROOT
        self.server.AIOS_ROOT = Path("/tmp/tmcp-aios-definitely-missing")
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
            self.server.AIOS_ROOT = original_root

        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "standalone")
        self.assertEqual(result["packet"]["schema"], "tmcp-skill-packet-v0.2")

    def test_aios_adapter_present_uses_aios_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_aios = Path(tmp)
            (fake_aios / "bin").mkdir()
            (fake_aios / "bin" / "aios.py").write_text(
                "import json\n"
                "print(json.dumps({'ok': True, 'adapter': 'fake-aios', 'task_id': 'audit'}))\n",
                encoding="utf-8",
            )
            original_root = self.server.AIOS_ROOT
            self.server.AIOS_ROOT = fake_aios
            try:
                result = self.server._call_tool(
                    "tmcp_explain",
                    {
                        "objective": "Use the TMCP expert UI rubric on Hoopscout",
                        "project_path": "/tmp/project",
                        "adapter": "aios",
                    },
                )
            finally:
                self.server.AIOS_ROOT = original_root

        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "fake-aios")
        self.assertEqual(result["task_id"], "audit")


if __name__ == "__main__":
    unittest.main()
