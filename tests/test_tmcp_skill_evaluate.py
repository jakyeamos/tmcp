from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = PLUGIN_ROOT / "scripts" / "tmcp_mcp_server.py"
EVALUATE_PATH = PLUGIN_ROOT / "scripts" / "tmcp_skill_evaluate.py"
LAUNCHER_PATH = PLUGIN_ROOT / "scripts" / "tmcp_launcher.mjs"
FIXTURE_SKILL = (
    PLUGIN_ROOT / "tests" / "fixtures" / "skills" / "approval-before-edit" / "SKILL.md"
)
PLAN_SCHEMA_PATH = (
    PLUGIN_ROOT / "schemas" / "tmcp-skill-evaluation-plan-v0.1.schema.json"
)
REPORT_SCHEMA_PATH = (
    PLUGIN_ROOT / "schemas" / "tmcp-skill-evaluation-report-v0.1.schema.json"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_mcp_requests(requests: list[dict]) -> list[dict]:
    framing = load_module(PLUGIN_ROOT / "scripts" / "tmcp_mcp_framing.py", "framing")
    raw = b"".join(framing.encode_message(request) for request in requests)
    completed = subprocess.run(
        ["node", str(LAUNCHER_PATH)],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PLUGIN_ROOT),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode())
    responses: list[dict] = []
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
        body_start = header_end + 4
        body = stream[body_start : body_start + length]
        responses.append(json.loads(body.decode()))
        position = body_start + length
    return responses


class SkillEvaluateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = load_module(SERVER_PATH, "tmcp_mcp_server_skill_eval")
        cls.evaluate = load_module(EVALUATE_PATH, "tmcp_skill_evaluate")

    def _plan_arguments(self) -> dict:
        return {
            "skill_paths": [str(FIXTURE_SKILL)],
            "task_fixtures": [
                {
                    "id": "approval-before-edit",
                    "prompt": "Fix the bug in this file.",
                    "expected_observables": [
                        "agent asks for approval before editing",
                        "agent names target file before mutation",
                    ],
                }
            ],
            "variants": ["baseline", "original", "negative_control"],
        }

    def test_tool_appears_in_tools_list(self) -> None:
        responses = run_mcp_requests(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}]
        )
        tools = responses[0]["result"]["tools"]
        tool_names = {tool["name"] for tool in tools}
        self.assertIn("tmcp_evaluate_skills", tool_names)

    def test_plan_decomposes_fixture_skill(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        self.assertEqual(plan["schema"], "tmcp-skill-evaluation-plan-v0.1")
        self.assertEqual(len(plan["evaluated_skills"]), 1)
        skill = plan["evaluated_skills"][0]
        self.assertTrue(str(skill["skill_path"]).endswith("SKILL.md"))
        self.assertIn("behavior-verification", skill["behavior_atoms"])

    def test_plan_generates_requested_variants(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        variant_ids = {row["variant_id"] for row in plan["task_matrix"]}
        self.assertEqual(variant_ids, {"baseline", "original", "negative_control"})

    def test_score_rejects_evidence_without_observable_trace(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        with self.assertRaises(ValueError) as ctx:
            self.evaluate.score_evidence(
                {
                    "evaluation_plan": plan,
                    "run_evidence_json": [
                        {
                            "task_id": "approval-before-edit",
                            "variant_id": "original",
                            "trace": [],
                        }
                    ],
                }
            )
        self.assertIn("observable observations", str(ctx.exception))

    def test_score_separates_activation_from_adherence(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        report = self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "run_evidence_json": [
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "original",
                        "observations": [
                            {
                                "kind": "file_read",
                                "value": "skills/approval-before-edit/SKILL.md",
                            },
                            {"kind": "file_write", "value": "src/app.tsx"},
                            {"kind": "command_run", "value": "npm test"},
                        ],
                        "human_labels": [
                            {
                                "observable_id": "asked_approval_before_edit",
                                "passed": False,
                            }
                        ],
                        "outcome": "partial",
                    }
                ],
            }
        )
        activation = report["activation_scores"][0]
        adherence = report["adherence_scores"][0]
        self.assertTrue(activation["signals"]["skill_selected"])
        self.assertFalse(adherence["signals"]["asked_for_approval_before_edit"])
        self.assertNotEqual(activation["score"], adherence["score"])

    def test_static_review_flags_vague_verification_noop(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        findings = plan["evaluated_skills"][0]["static_findings"]
        pattern_ids = {item["pattern_id"] for item in findings}
        self.assertIn("verification.vague-quality-language", pattern_ids)
        vague = next(
            item
            for item in findings
            if item["pattern_id"] == "verification.vague-quality-language"
        )
        self.assertIn("SKILL.md", vague["message"])
        self.assertIn("behavior-verification", vague["internal_atoms"])

    def test_score_produces_guidebook_entries_with_evidence_levels(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        report = self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "run_evidence_json": [
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "original",
                        "observations": [
                            {"kind": "assistant_message", "value": "Running npm test"},
                            {"kind": "command_run", "value": "npm test"},
                        ],
                        "outcome": "passed",
                    }
                ],
            }
        )
        self.assertTrue(report["guidebook_entries"])
        for entry in report["guidebook_entries"]:
            self.assertIn(entry["evidence_level"], self.evaluate.EVIDENCE_LEVELS)

    def test_score_does_not_auto_promote(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        report = self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "run_evidence_json": [
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "original",
                        "observations": [
                            {"kind": "command_run", "value": "npm test"},
                        ],
                        "outcome": "passed",
                    }
                ],
            }
        )
        self.assertFalse(report["promotion_policy"]["auto_promote"])
        self.assertEqual(report["promotion_policy"]["applied_changes"], [])
        for item in report["skill_harvest_feedback"]:
            self.assertTrue(item["safe_to_auto_warn"])
            self.assertFalse(item["safe_to_auto_rewrite"])

    def test_plan_schema_required_fields_present(self) -> None:
        schema = json.loads(PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        missing = [field for field in schema["required"] if field not in plan]
        self.assertEqual(missing, [])

    def test_report_schema_required_fields_present(self) -> None:
        schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        report = self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "run_evidence_json": [
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "original",
                        "observations": [
                            {"kind": "command_run", "value": "npm test"},
                        ],
                        "outcome": "passed",
                    }
                ],
            }
        )
        missing = [field for field in schema["required"] if field not in report]
        self.assertEqual(missing, [])

    def test_write_artifacts_emits_plan_and_report_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "eval"
            plan = self.evaluate.evaluate_skills(
                {
                    **self._plan_arguments(),
                    "mode": "plan",
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                }
            )
            self.assertIn("artifact_paths", plan)
            report = self.evaluate.evaluate_skills(
                {
                    "mode": "score",
                    "evaluation_plan": plan,
                    "run_evidence_json": [
                        {
                            "task_id": "approval-before-edit",
                            "variant_id": "original",
                            "observations": [
                                {"kind": "command_run", "value": "npm test"},
                            ],
                            "outcome": "passed",
                        }
                    ],
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                }
            )
            self.assertTrue((output_dir / "tmcp-skill-evaluation-plan.json").exists())
            self.assertTrue(
                (output_dir / "tmcp-skill-evaluation-report.json").exists()
            )
            self.assertTrue((output_dir / "skill-writing-guidebook.md").exists())
            self.assertTrue((output_dir / "skill-pattern-catalog.json").exists())
            self.assertIn("artifact_paths", report)

    def test_mcp_tool_call_plan_mode(self) -> None:
        result = self.server._call_tool(
            "tmcp_evaluate_skills",
            {
                **self._plan_arguments(),
                "mode": "plan",
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "plan")
        self.assertEqual(result["schema"], "tmcp-skill-evaluation-plan-v0.1")

    def test_harvest_emits_skill_eval_warnings_for_fixture_skill(self) -> None:
        result = self.server._harvest_skills(
            {
                "source_path": str(FIXTURE_SKILL.parent),
                "include_globs": ["**/SKILL.md"],
                "limit": 5,
            }
        )
        self.assertTrue(result["ok"])
        warning_text = "\n".join(result["warnings"])
        self.assertIn("verification no-op", warning_text.lower())
        summary = result["skill_eval_advisory_summary"]
        self.assertGreater(summary["warning_count"], 0)
        self.assertIn("verification.vague-quality-language", summary["patterns_detected"])
        self.assertEqual(summary["policy"], "advisory_only_no_auto_rewrite")
        node = next(
            item
            for item in result["source_nodes"]
            if str(item.get("path", "")).endswith("SKILL.md")
        )
        self.assertTrue(node.get("skill_eval_advisories"))

    def test_plan_includes_packet_inclusion_contracts(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        self.assertTrue(plan.get("packet_inclusion_contracts"))
        contract = plan["packet_inclusion_contracts"][0]
        self.assertIn("required_reads", contract["expected"])
        self.assertIn("behavior_atoms", contract["expected"])

    def test_packet_inclusion_diff_uses_compose_packet(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        row = next(
            item
            for item in plan["task_matrix"]
            if item["variant_id"] == "original"
        )
        composed = self.evaluate.compose_packet_for_eval_row(
            row,
            self.server._compose_packet,
            project_path=str(PLUGIN_ROOT),
        )
        contract = plan["packet_inclusion_contracts"][0]["expected"]
        diff = self.evaluate.diff_packet_inclusion(
            contract,
            composed,
            skill_path=str(row["skill_path"]),
            variant_id="original",
        )
        self.assertEqual(diff["confidence"], "high")
        self.assertTrue(diff["signals"]["skill_selected_in_packet"])
        self.assertIn("packet_id", composed)

    def test_score_packet_inclusion_reports_compose_diff(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        report = self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "project_path": str(PLUGIN_ROOT),
                "run_evidence_json": [
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "original",
                        "observations": [
                            {"kind": "command_run", "value": "npm test"},
                        ],
                        "outcome": "passed",
                    }
                ],
            }
        )
        packet_score = report["packet_inclusion_scores"][0]
        self.assertEqual(packet_score["confidence"], "high")
        self.assertIn("packet_inclusion_diff", packet_score)
        self.assertTrue(report["packet_inclusion_diffs"])
        self.assertIn(
            "tmcp_compose_packet",
            packet_score.get("notes", "").lower(),
        )

    def test_baseline_variant_expects_skill_not_selected(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        row = next(
            item
            for item in plan["task_matrix"]
            if item["variant_id"] == "baseline"
        )
        composed = self.evaluate.compose_packet_for_eval_row(
            row,
            self.server._compose_packet,
            project_path=str(PLUGIN_ROOT),
        )
        contract = plan["packet_inclusion_contracts"][0]["expected"]
        diff = self.evaluate.diff_packet_inclusion(
            contract,
            composed,
            skill_path=str(row["skill_path"]),
            variant_id="baseline",
        )
        self.assertFalse(diff["signals"]["skill_should_be_selected"])

    def test_multi_agent_traces_raise_evidence_level(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        report = self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "run_evidence_json": [
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "original",
                        "agent": {"name": "codex", "model": "gpt-5"},
                        "observations": [{"kind": "command_run", "value": "npm test"}],
                        "outcome": "passed",
                    },
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "rewritten",
                        "agent": {"name": "cursor", "model": "claude"},
                        "observations": [{"kind": "command_run", "value": "npm test"}],
                        "outcome": "passed",
                    },
                ],
            }
        )
        levels = {entry["evidence_level"] for entry in report["guidebook_entries"]}
        self.assertIn("controlled_multi_agent_eval", levels)


if __name__ == "__main__":
    unittest.main()
