from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from tests.tmcp_test_client import (
    TestWorkspace,
    run_mcp_requests as run_hermetic_mcp_requests,
)
from tmcp_runtime.domain import review_evidence, standalone_packets


SERVER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tmcp_mcp_server.py"
PLUGIN_ROOT = SERVER_PATH.parents[1]
GOLDEN_PACKETS_PATH = PLUGIN_ROOT / "tests" / "fixtures" / "golden_packets.json"
PACKET_SCHEMA_PATH = PLUGIN_ROOT / "schemas" / "tmcp-skill-packet-v0.2.schema.json"


def load_server_module():
    from tests.test_tmcp_mcp_server import load_server_module as load

    return load()


def run_mcp_requests(requests: list[dict[str, object]]) -> list[dict[str, object]]:
    return run_hermetic_mcp_requests(requests, PLUGIN_ROOT)


class TmcpMcpProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = load_server_module()

    def test_server_dispatch_registry_covers_every_public_tool(self) -> None:
        from tmcp_runtime.api.registry import PUBLIC_TOOL_NAMES

        self.assertEqual(set(self.server._TOOL_HANDLERS), PUBLIC_TOOL_NAMES)
        self.assertEqual(self.server._TOOL_DISPATCHER.tool_names, PUBLIC_TOOL_NAMES)

    def test_expert_ui_rubric_routes_to_audit_packet(self) -> None:
        packet = standalone_packets.compile_standalone_packet(
            objective="Use the TMCP expert UI rubric on Hoopscout",
            project_path="/tmp/hoopscout",
        )

        self.assertEqual(packet["task_id"], "audit")
        self.assertIn("@task:audit", packet["selected_nodes"])
        rubric = review_evidence.synthesize_rubric(
            packet, "run-test", packet["objective"]
        )
        self.assertEqual(rubric["profile"], "visual_polish")

    def test_packet_substance_check_flags_process_only_packets(self) -> None:
        packet = standalone_packets.compile_standalone_packet(
            objective="Use TMCP to audit government readiness for CrimClock",
            project_path="/tmp/crimclock",
        )

        substance = packet["substance_check"]
        self.assertEqual(substance["level"], "process_only")
        self.assertFalse(substance["has_domain_playbook"])
        self.assertIn(
            "derive rubric substance from target repo docs",
            substance["fallback_policy"],
        )
        self.assertTrue(substance["issues"])

    def test_profile_coverage_accepts_tuple_terms(self) -> None:
        requirements = list(
            review_evidence.PROFILE_COVERAGE_REQUIREMENTS["visual_polish"]
        )
        self.assertTrue(all(isinstance(item["terms"], tuple) for item in requirements))
        coverage_text = " ".join(
            str(term)
            for requirement in requirements
            for term in cast(tuple[object, ...], requirement["terms"])
        )

        report = review_evidence.build_audit_report(
            {
                "profile": "visual_polish",
                "coverage_requirements": requirements,
                "dimensions": [
                    {"id": "visual_product_quality", "name": "Visual product quality"}
                ],
            },
            [
                {
                    "dimension_id": "visual_product_quality",
                    "severity": "observation",
                    "summary": coverage_text,
                    "evidence": [coverage_text],
                    "recommended_fix": "No fix required.",
                }
            ],
            "tuple-coverage",
        )

        self.assertEqual(report["coverage_gaps"], [])

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
        tools_result_map = cast(Mapping[str, object], tools_result)
        tools = cast(list[Mapping[str, object]], tools_result_map["tools"])
        tool_names = {tool["name"] for tool in tools}
        self.assertEqual(
            tool_names,
            {
                "expert_rubric_review_plan",
                "tmcp_compose_packet",
                "tmcp_doctor",
                "tmcp_evaluate_skills",
                "tmcp_explain",
                "tmcp_harvest_skills",
                "tmcp_promote_harvest",
                "tmcp_record_receipt",
                "tmcp_recommend_workflows",
                "tmcp_runtime_next",
                "tmcp_status",
            },
        )
        status_result = responses[1]["result"]
        self.assertIsInstance(status_result, dict)
        status_result_map = cast(Mapping[str, object], status_result)
        structured = cast(
            Mapping[str, Mapping[str, object]], status_result_map["structuredContent"]
        )
        self.assertTrue(structured["standalone"]["available"])

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
        packet = standalone_packets.compile_standalone_packet(
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
            with TestWorkspace(copied) as workspace:
                completed = subprocess.run(
                    ["python3", "scripts/check_install.py", "."],
                    cwd=copied,
                    env=workspace.environment(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["manifest"], "pass")
        self.assertEqual(payload["mcp_launch"], "pass")

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

        first_error = cast(Mapping[str, object], responses[0]["error"])
        second_error = cast(Mapping[str, object], responses[1]["error"])
        self.assertEqual(first_error["code"], -32602)
        self.assertEqual(second_error["code"], -32000)

    def test_golden_packet_routes_and_profiles(self) -> None:
        cases = json.loads(GOLDEN_PACKETS_PATH.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(objective=case["objective"]):
                packet = standalone_packets.compile_standalone_packet(
                    objective=case["objective"],
                    project_path="/tmp/project",
                )
                rubric = review_evidence.synthesize_rubric(
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

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "needs_evidence")
        self.assertEqual(result["rubric"]["profile"], "developer_experience")
        self.assertEqual(result["audit_report"]["findings"], [])
        self.assertTrue(result["audit_report"]["deferred_scope"])
        self.assertEqual(result["remediation_slices"][0]["id"], "slice-1")
        self.assertIn(
            "Populate dimension-mapped evidence",
            result["remediation_slices"][0]["title"],
        )
        self.assertEqual(
            result["evidence_remediation_contract"]["status"], "missing_evidence"
        )
        self.assertEqual(
            [
                item["dimension_id"]
                for item in result["evidence_contract"]["starter_template"]
            ],
            result["evidence_contract"]["dimension_ids"],
        )


if __name__ == "__main__":
    unittest.main()
