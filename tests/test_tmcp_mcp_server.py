from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast


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

    def test_packet_substance_check_flags_process_only_packets(self) -> None:
        packet = self.server._compile_standalone_packet(
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

    def test_harvest_is_portable_and_prunes_dependency_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / ".github").mkdir()
            (root / ".cursor" / "rules").mkdir(parents=True)
            (root / "node_modules" / "ignored").mkdir(parents=True)
            (root / ".aios" / "audit").mkdir(parents=True)
            (root / ".tmcp" / "harvest").mkdir(parents=True)
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
            (root / ".aios" / "audit" / "gate-summary.md").write_text(
                "# Generated gate output\n",
                encoding="utf-8",
            )
            (root / ".tmcp" / "harvest" / "packet.md").write_text(
                "# Generated TMCP output\n",
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
        self.assertNotIn(".aios/audit/gate-summary.md", rel_paths)
        self.assertNotIn(".tmcp/harvest/packet.md", rel_paths)
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
            high_entropy = "A9b8C7d6E5f4G3h2I1j0K9l8M7n6O5p4Q3r2S1t0"
            (root / "AGENTS.md").write_text(
                "\n".join(
                    [
                        "# Agent Contract",
                        "Keep docs/security-privacy-harvest-audit.md readable.",
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

            result = self.server._harvest_skills(
                {"source_path": str(root), "limit": 10}
            )

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
        self.assertIn("docs/security-privacy-harvest-audit.md", serialized)
        self.assertGreater(sum(result["redaction_summary"].values()), 0)

    def test_recommend_workflows_uses_harvested_priority_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: frontend-ui-review",
                        "---",
                        "# UI Review",
                        "Use screenshots, responsive layout checks, design-system fit, visual polish, and component state evidence.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text(
                "# Agent Rules\n\nVerify UI states with evidence before implementation.\n",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {"source_path": str(root), "limit": 10},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-workflow-recommendation-v1")
        self.assertIn("ui_quality", result["priority_profile"]["primary_signals"])
        self.assertEqual(
            result["recommended_workflows"][0]["id"], "expert_ui_rubric_workflow"
        )
        self.assertTrue(result["recommended_workflows"][0]["evidence"])
        self.assertIn("starter_prompt", result["recommended_workflows"][0])

    def test_recommend_workflows_filters_candidates_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "recommendations"
            (root / "SECURITY.md").write_text(
                "# Security\n\nRedact secrets, review permissions, audit auth tokens, and inspect data flow privacy.\n",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["security_privacy_review_workflow"],
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                },
            )

            self.assertEqual(
                [item["id"] for item in result["recommended_workflows"]],
                ["security_privacy_review_workflow"],
            )
            self.assertEqual(result["not_recommended"], [])
            paths = result["artifact_paths"]
            self.assertTrue(Path(paths["recommendation_json"]).exists())
            self.assertTrue(Path(paths["recommendation_markdown"]).exists())

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
            self.assertTrue(result["artifact_paths"])
            self.assertTrue(
                any(
                    "profile-coverage" in item["id"]
                    for item in result["remediation_slices"]
                )
            )
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

    def test_visual_review_requires_product_quality_coverage(self) -> None:
        result = self.server._standalone_review_plan(
            {
                "objective": "Use the TMCP expert UI rubric on this product",
                "project_path": "/tmp/product",
                "write_artifacts": False,
                "evidence_json": json.dumps(
                    [
                        {
                            "dimension_id": "interaction_architecture",
                            "severity": "blocker",
                            "summary": "Feed remains in loading state after the route is opened.",
                            "evidence": [
                                "Browser route stayed on skeleton cards for 12 seconds."
                            ],
                            "recommended_fix": "Bound computation and show error or empty state.",
                        },
                        {
                            "dimension_id": "data_realism",
                            "severity": "warning",
                            "summary": "Dashboard data resolves but the feed does not.",
                            "evidence": [
                                "Dashboard count renders; feed stays unresolved."
                            ],
                            "recommended_fix": "Make each feed resolve to data, empty, or failure state.",
                        },
                    ]
                ),
            }
        )

        validations = {item["validation_key"]: item for item in result["validations"]}
        self.assertIn("profile_evidence_coverage", validations)
        coverage_validation = validations["profile_evidence_coverage"]
        self.assertFalse(coverage_validation["passed"])
        self.assertTrue(
            any(
                "visual" in issue.lower() and "coverage" in issue.lower()
                for issue in coverage_validation["issues"]
            )
        )
        self.assertTrue(result["audit_report"]["coverage_gaps"])
        self.assertTrue(
            any(
                "profile-coverage" in item["id"]
                for item in result["remediation_slices"]
            )
        )
        gap_slice = next(
            item
            for item in result["remediation_slices"]
            if "profile-coverage" in item["id"]
        )
        self.assertIn("typography", " ".join(gap_slice["scope"]).lower())
        self.assertIn("spacing", " ".join(gap_slice["scope"]).lower())

    def test_profile_coverage_is_enforced_for_non_visual_reviews(self) -> None:
        result = self.server._standalone_review_plan(
            {
                "objective": "Use TMCP to audit security and privacy risks in this project",
                "project_path": "/tmp/product",
                "write_artifacts": False,
                "evidence_json": json.dumps(
                    [
                        {
                            "dimension_id": "secret_exposure",
                            "severity": "observation",
                            "summary": "The reviewed page renders without errors.",
                            "evidence": ["Browser route loaded successfully."],
                            "recommended_fix": "Keep the route rendering.",
                        },
                        {
                            "dimension_id": "permission_boundary",
                            "severity": "observation",
                            "summary": "The reviewed page renders without errors.",
                            "evidence": ["Browser route loaded successfully."],
                            "recommended_fix": "Keep the route rendering.",
                        },
                        {
                            "dimension_id": "data_flow_privacy",
                            "severity": "observation",
                            "summary": "The reviewed page renders without errors.",
                            "evidence": ["Browser route loaded successfully."],
                            "recommended_fix": "Keep the route rendering.",
                        },
                        {
                            "dimension_id": "supply_chain",
                            "severity": "observation",
                            "summary": "The reviewed page renders without errors.",
                            "evidence": ["Browser route loaded successfully."],
                            "recommended_fix": "Keep the route rendering.",
                        },
                    ]
                ),
            }
        )

        validations = {item["validation_key"]: item for item in result["validations"]}
        coverage_validation = validations["profile_evidence_coverage"]
        self.assertFalse(coverage_validation["passed"])
        self.assertTrue(
            any(
                "security" in issue.lower() and "privacy" in issue.lower()
                for issue in coverage_validation["issues"]
            )
        )
        self.assertTrue(
            any(
                "profile-coverage" in item["id"]
                for item in result["remediation_slices"]
            )
        )

    def test_review_plan_harvests_project_sources_for_public_sector_substance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            (docs / "government-readiness.md").write_text(
                "\n".join(
                    [
                        "# Government Readiness Audit",
                        "A government readiness audit must inspect security controls, tenant isolation,",
                        "audit logs, source provenance, legal calculation safety, release blockers,",
                        "deployment rollback, UAT evidence, accessibility, and risk register gates.",
                        "Score blocker, warning, and observation findings with cited evidence.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._standalone_review_plan(
                {
                    "objective": "Use TMCP to audit government readiness for CrimClock",
                    "project_path": str(root),
                    "write_artifacts": False,
                    "evidence_json": json.dumps(
                        [
                            {
                                "dimension_id": "governance_policy_fit",
                                "severity": "warning",
                                "summary": "Readiness gate needs owner evidence.",
                                "evidence": ["docs/government-readiness.md"],
                                "recommended_fix": "Attach owner and acceptance evidence to the gate.",
                            }
                        ]
                    ),
                }
            )

        self.assertEqual(result["rubric"]["profile"], "public_sector_readiness")
        substance = result["expertise_packet"]["substance_check"]
        self.assertEqual(substance["level"], "source_backed_playbook")
        self.assertTrue(substance["has_domain_playbook"])
        self.assertGreaterEqual(substance["substantive_source_count"], 1)
        self.assertIn("government", substance["matched_domain_terms"])
        self.assertEqual(result["artifact_paths"], {})
        self.assertTrue(
            any(
                node["relative_path"] == "docs/government-readiness.md"
                for node in result["expertise_packet"]["source_skill_nodes"]
            )
        )

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
                "tmcp_doctor",
                "tmcp_explain",
                "tmcp_harvest_skills",
                "tmcp_recommend_workflows",
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

    def test_launcher_cli_status_calls_tool_directly(self) -> None:
        completed = subprocess.run(
            ["node", str(LAUNCHER_PATH), "status"],
            cwd=PLUGIN_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["standalone"]["available"])
        self.assertIn("workflow_recommendation", payload["standalone"]["capabilities"])

    def test_launcher_cli_explain_accepts_positional_objective(self) -> None:
        completed = subprocess.run(
            [
                "node",
                str(LAUNCHER_PATH),
                "explain",
                "Use the TMCP expert UI rubric on Hoopscout",
                "--project-path",
                "/tmp/hoopscout",
                "--adapter",
                "standalone",
            ],
            cwd=PLUGIN_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["adapter"], "standalone")
        self.assertEqual(payload["packet"]["task_id"], "audit")

    def test_cli_parser_repeated_flags_become_lists(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "harvest",
                ".",
                "--include-globs",
                "**/SKILL.md",
                "--include-globs",
                "**/AGENTS.md",
                "--write-artifacts",
                "--no-redact-sensitive",
                "--compact",
            ]
        )

        self.assertEqual(tool_name, "tmcp_harvest_skills")
        self.assertTrue(compact)
        self.assertEqual(arguments["source_path"], ".")
        self.assertEqual(arguments["include_globs"], ["**/SKILL.md", "**/AGENTS.md"])
        self.assertTrue(arguments["write_artifacts"])
        self.assertFalse(arguments["redact_sensitive"])

    def test_cli_parser_schema_array_flags_accept_single_value(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            ["recommend", ".", "--candidate-workflows", "ui_quality"]
        )

        self.assertEqual(tool_name, "tmcp_recommend_workflows")
        self.assertFalse(compact)
        self.assertEqual(arguments["candidate_workflows"], ["ui_quality"])

    def test_cli_expert_ui_rubric_alias_defaults_to_tmcp_workflow(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "expert-ui-rubric",
                "--project-path",
                "/tmp/fantasy",
                "--evidence-json",
                "[]",
            ]
        )

        self.assertEqual(tool_name, "expert_rubric_review_plan")
        self.assertFalse(compact)
        self.assertEqual(
            arguments["objective"], "Use the TMCP expert UI rubric on this project."
        )
        self.assertEqual(arguments["adapter"], "standalone")
        self.assertEqual(arguments["project_path"], "/tmp/fantasy")

    def test_cli_expert_ui_rubric_alias_accepts_objective_override(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "tmcp-expert-ui-rubric",
                "Use the TMCP expert UI rubric workflow on Fantasy",
            ]
        )

        self.assertEqual(tool_name, "expert_rubric_review_plan")
        self.assertFalse(compact)
        self.assertEqual(
            arguments["objective"], "Use the TMCP expert UI rubric workflow on Fantasy"
        )
        self.assertEqual(arguments["adapter"], "standalone")

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
        self.assertIn(
            "Collect missing evidence", result["remediation_slices"][0]["title"]
        )

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

    def test_aios_adapter_present_uses_aios_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_aios = Path(tmp)
            (fake_aios / "bin").mkdir()
            (fake_aios / "bin" / "aios.py").write_text(
                "import json\n"
                "print(json.dumps({'ok': True, 'adapter': 'fake-aios', 'task_id': 'audit'}))\n",
                encoding="utf-8",
            )
            original_root = getattr(self.server, "AIOS_ROOT")
            setattr(self.server, "AIOS_ROOT", fake_aios)
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
                setattr(self.server, "AIOS_ROOT", original_root)

        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "fake-aios")
        self.assertEqual(result["task_id"], "audit")


if __name__ == "__main__":
    unittest.main()
