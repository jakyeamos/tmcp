from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from tests import test_tmcp_mcp_server as helpers
from tests.tmcp_test_client import run_mcp_requests as run_hermetic_mcp_requests
from tmcp_runtime.services.evaluation_cost_rejudge import trace_source_digest
from tmcp_runtime.storage import artifact_persistence_available


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
EVALUATE_PATH = PLUGIN_ROOT / "scripts" / "tmcp_skill_evaluate.py"
HARVEST_ADVISORIES_PATH = (
    PLUGIN_ROOT / "tmcp_runtime" / "services" / "harvest_advisories.py"
)
FIXTURE_SKILL = (
    PLUGIN_ROOT / "tests" / "fixtures" / "skills" / "approval-before-edit" / "SKILL.md"
)
PLAN_SCHEMA_PATH = (
    PLUGIN_ROOT / "schemas" / "tmcp-skill-evaluation-plan-v0.2.schema.json"
)
REPORT_SCHEMA_PATH = (
    PLUGIN_ROOT / "schemas" / "tmcp-skill-evaluation-report-v0.2.schema.json"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_mcp_requests(requests: list[dict[str, object]]) -> list[dict[str, object]]:
    return run_hermetic_mcp_requests(requests, PLUGIN_ROOT)


class SkillEvaluateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()
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

    def _pattern_plan(self) -> dict:
        arguments = self._plan_arguments()
        arguments["variants"] = ["original", "ablated"]
        arguments["task_fixtures"][0].update(
            {
                "pattern_id": "structure.explicit-verification-section",
                "tested_atom": "verification_section",
                "intervention_variant": "ablated",
                "control_variant": "original",
                "intervention_target": "verification",
                "expected_effect_direction": "negative",
            }
        )
        return self.evaluate.build_evaluation_plan(arguments)

    def _score_probe(self, plan: dict, row: dict) -> dict:
        return self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "compose_packet": False,
                "run_evidence_json": [
                    {
                        "task_id": row["task_id"],
                        "variant_id": row["variant_id"],
                        "matrix_row_id": row.get("matrix_row_id"),
                        "ablation_section": row.get("ablation_section"),
                        "observations": [
                            {"kind": "assistant_message", "value": "artifact"}
                        ],
                    }
                ],
            }
        )

    def test_tool_appears_in_tools_list(self) -> None:
        responses = run_mcp_requests(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}]
        )
        result = cast(dict[str, object], responses[0]["result"])
        tools = cast(list[dict[str, object]], result["tools"])
        tool_names = {tool["name"] for tool in tools}
        self.assertIn("tmcp_evaluate_skills", tool_names)

    def test_evaluator_does_not_depend_on_private_server_helpers(self) -> None:
        source = EVALUATE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("scripts.tmcp_mcp_server", source)
        self.assertNotIn("__globals__", source)
        self.assertNotIn("tmcp_runtime.storage", source)
        self.assertNotIn("AtomicArtifactStore", source)

    def test_harvest_advisories_service_does_not_import_adapter(self) -> None:
        source = HARVEST_ADVISORIES_PATH.read_text(encoding="utf-8")

        self.assertNotIn("scripts.tmcp_mcp_server", source)
        self.assertNotIn("scripts.tmcp_skill_evaluate", source)

    def test_plan_decomposes_fixture_skill(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        self.assertEqual(plan["schema"], "tmcp-skill-evaluation-plan-v0.2")
        self.assertEqual(len(plan["evaluated_skills"]), 1)
        skill = plan["evaluated_skills"][0]
        self.assertTrue(str(skill["skill_path"]).endswith("SKILL.md"))
        self.assertIn("behavior-verification", skill["behavior_atoms"])

    def test_plan_generates_requested_variants(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        variant_ids = {row["variant_id"] for row in plan["task_matrix"]}
        self.assertEqual(variant_ids, {"baseline", "original", "negative_control"})

    def test_plan_preserves_nonsecret_content_digests(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())

        skill_digest = plan["evaluated_skills"][0]["skill_digest"]
        fixture_digest = plan["task_matrix"][0]["fixture_digest"]
        self.assertTrue(skill_digest.startswith("sha256:"))
        self.assertTrue(fixture_digest.startswith("sha256:"))
        self.assertNotIn("REDACTED", skill_digest)
        self.assertNotIn("REDACTED", fixture_digest)

    def test_plan_rejects_oversized_variant_input(self) -> None:
        arguments = self._plan_arguments()
        arguments["variants"] = ["variant"] * (
            self.evaluate.MAX_EVALUATION_VARIANTS + 1
        )

        with self.assertRaisesRegex(ValueError, "variant count"):
            self.evaluate.build_evaluation_plan(arguments)

    def test_plan_rejects_oversized_serialized_fixture_input(self) -> None:
        with patch.object(self.evaluate, "MAX_EVALUATION_INPUT_BYTES", 16):
            with self.assertRaisesRegex(ValueError, "serialized size"):
                self.evaluate.build_evaluation_plan(self._plan_arguments())

    def test_plan_rejects_matrix_before_cartesian_expansion(self) -> None:
        with patch.object(self.evaluate, "MAX_EVALUATION_MATRIX_ROWS", 1):
            with self.assertRaisesRegex(ValueError, "matrix"):
                self.evaluate.build_evaluation_plan(self._plan_arguments())

    def test_score_rejects_oversized_evidence_input(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        trace = {
            "task_id": "approval-before-edit",
            "variant_id": "original",
            "observations": [{"kind": "command_run", "value": "pnpm test"}],
        }

        with self.assertRaisesRegex(ValueError, "trace count"):
            self.evaluate.score_evidence(
                {
                    "evaluation_plan": plan,
                    "run_evidence_json": [trace]
                    * (self.evaluate.MAX_EVALUATION_TRACES + 1),
                }
            )

    def test_score_rejects_malformed_nested_plan_before_scoring(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        plan["evaluated_skills"][0]["static_findings"] = "bad"

        with self.assertRaisesRegex(ValueError, "static_findings"):
            self.evaluate.score_evidence(
                {
                    "evaluation_plan": plan,
                    "run_evidence_json": [
                        {
                            "task_id": "approval-before-edit",
                            "variant_id": "original",
                            "observations": [
                                {"kind": "command_run", "value": "pnpm test"}
                            ],
                        }
                    ],
                }
            )

    def test_score_rejects_oversized_inline_plan_input(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        with patch.object(self.evaluate, "MAX_EVALUATION_INPUT_BYTES", 16):
            with self.assertRaisesRegex(ValueError, "evaluation_plan"):
                self.evaluate.score_evidence(
                    {
                        "evaluation_plan": plan,
                        "run_evidence_json": [
                            {
                                "task_id": "approval-before-edit",
                                "variant_id": "original",
                                "observations": [
                                    {"kind": "command_run", "value": "pnpm test"}
                                ],
                            }
                        ],
                    }
                )

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

    def test_score_binds_cost_rejudgments_before_trace_redaction(self) -> None:
        plan = self._pattern_plan()
        row = next(
            item for item in plan["task_matrix"] if item["variant_id"] == "original"
        )
        trace = {
            "schema": "tmcp-skill-eval-trace-v0.1",
            "trace_id": "trace-1",
            "experiment_id": plan["experiment"]["experiment_id"],
            "matrix_row_id": row["matrix_row_id"],
            "task_id": row["task_id"],
            "variant_id": row["variant_id"],
            "skill_path": row["skill_path"],
            "ablation_section": row["ablation_section"],
            "agent": {"name": "test", "model": "test"},
            "campaign": {
                "runner_artifact_sha256": "sha256:" + "0123456789abcdef" * 4,
            },
            "observations": [{"kind": "assistant_message", "value": "artifact"}],
            "case_verdict": {"passed": True, "cost_regression": True},
        }
        sidecar = {
            "schema": "tmcp-skill-eval-cost-rejudgment-v0.1",
            "rejudgments": [
                {
                    "trace_id": trace["trace_id"],
                    "source_trace_digest": trace_source_digest(trace),
                    "cost_regression": False,
                    "evidence": [
                        {
                            "criterion": (
                                "C1: The artifact does not require materially "
                                "unnecessary execution work."
                            ),
                            "status": "necessary",
                            "citation": "artifact line 1",
                        }
                    ],
                    "rationale": "The required control is necessary.",
                    "provenance": {
                        "judge_blinded": True,
                        "isolated_session": True,
                        "fresh_session": True,
                        "condition_hidden": True,
                        "source_artifact_only": True,
                    },
                }
            ],
        }
        redactions: dict[str, int] = {}
        redacted_trace = self.evaluate._safe_bounded_json_value(
            [trace], label="run_evidence_json", redactions=redactions
        )[0]

        self.assertNotEqual(
            trace_source_digest(trace), trace_source_digest(redacted_trace)
        )
        report = self.evaluate.score_evidence(
            {
                "evaluation_plan": plan,
                "compose_packet": False,
                "run_evidence_json": [trace],
                "cost_rejudgments_json": sidecar,
            }
        )

        self.assertEqual(report["schema"], "tmcp-skill-evaluation-report-v0.2")

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
                            {"kind": "command_run", "value": "pnpm test"},
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
                            {"kind": "assistant_message", "value": "Running pnpm test"},
                            {"kind": "command_run", "value": "pnpm test"},
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
                            {"kind": "command_run", "value": "pnpm test"},
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
                            {"kind": "command_run", "value": "pnpm test"},
                        ],
                        "outcome": "passed",
                    }
                ],
            }
        )
        missing = [field for field in schema["required"] if field not in report]
        self.assertEqual(missing, [])

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_write_artifacts_emits_plan_and_report_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "eval"
            plan = self.server._call_tool(
                "tmcp_evaluate_skills",
                {
                    **self._plan_arguments(),
                    "mode": "plan",
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                },
            )
            self.assertIn("artifact_paths", plan)
            report = self.server._call_tool(
                "tmcp_evaluate_skills",
                {
                    "mode": "score",
                    "evaluation_plan": plan,
                    "run_evidence_json": [
                        {
                            "task_id": "approval-before-edit",
                            "variant_id": "original",
                            "observations": [
                                {"kind": "command_run", "value": "pnpm test"},
                            ],
                            "outcome": "passed",
                        }
                    ],
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                },
            )
            self.assertTrue((output_dir / "tmcp-skill-evaluation-plan.json").exists())
            self.assertTrue((output_dir / "tmcp-skill-evaluation-report.json").exists())
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
        self.assertEqual(result["schema"], "tmcp-skill-evaluation-plan-v0.2")

    def test_mcp_tool_call_score_mode_injects_composition_service(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())

        result = self.server._call_tool(
            "tmcp_evaluate_skills",
            {
                "mode": "score",
                "evaluation_plan": plan,
                "project_path": str(PLUGIN_ROOT),
                "run_evidence_json": [
                    {
                        "task_id": "approval-before-edit",
                        "variant_id": "original",
                        "observations": [
                            {"kind": "command_run", "value": "pnpm test"},
                        ],
                        "outcome": "passed",
                    }
                ],
            },
        )

        self.assertEqual(result["mode"], "score")
        self.assertEqual(
            result["packet_inclusion_scores"][0]["confidence"],
            "high",
        )

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
        self.assertIn(
            "verification.vague-quality-language", summary["patterns_detected"]
        )
        self.assertEqual(summary["policy"], "advisory_only_no_auto_rewrite")
        node = next(
            item
            for item in result["source_nodes"]
            if str(item.get("path", "")).endswith("SKILL.md")
        )
        self.assertTrue(node.get("skill_eval_advisories"))

    def test_pattern_lookup_falls_back_for_malformed_catalog_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            with patch.object(self.evaluate, "PATTERN_CATALOG_PATH", catalog_path):
                for payload in ("[]", '{"patterns": null}', "not json"):
                    catalog_path.write_text(payload, encoding="utf-8")
                    patterns = self.evaluate._pattern_lookup()
                    self.assertIn("verification.vague-quality-language", patterns)

    def test_plan_includes_packet_inclusion_contracts(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        self.assertTrue(plan.get("packet_inclusion_contracts"))
        contract = plan["packet_inclusion_contracts"][0]
        self.assertIn("required_reads", contract["expected"])
        self.assertIn("behavior_atoms", contract["expected"])

    def test_packet_inclusion_diff_uses_compose_packet(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        row = next(
            item for item in plan["task_matrix"] if item["variant_id"] == "original"
        )
        composed = self.evaluate.compose_packet_for_eval_row(
            row,
            self.server._compose_evaluation_row,
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
        self.assertTrue(diff["signals"]["included_output_contract"])
        self.assertIn("Return a helpful summary", " ".join(composed["output_contract"]))
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
                            {"kind": "command_run", "value": "pnpm test"},
                        ],
                        "outcome": "passed",
                    }
                ],
            },
            compose_evaluation_row=self.server._compose_evaluation_row,
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
            item for item in plan["task_matrix"] if item["variant_id"] == "baseline"
        )
        composed = self.evaluate.compose_packet_for_eval_row(
            row,
            self.server._compose_evaluation_row,
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

    def test_unmatched_trace_cannot_raise_evidence_level(self) -> None:
        plan = self.evaluate.build_evaluation_plan(self._plan_arguments())
        with self.assertRaisesRegex(ValueError, "does not match the task matrix"):
            self.evaluate.score_evidence(
                {
                    "evaluation_plan": plan,
                    "run_evidence_json": [
                        {
                            "task_id": "approval-before-edit",
                            "variant_id": "rewritten",
                            "agent": {"name": "cursor", "model": "claude"},
                            "observations": [
                                {"kind": "command_run", "value": "pnpm test"}
                            ],
                            "outcome": "passed",
                        }
                    ],
                },
                compose_evaluation_row=self.server._compose_evaluation_row,
            )

    def test_tampered_pattern_contract_is_rejected_during_score_load(self) -> None:
        plan = self._pattern_plan()
        plan["task_matrix"][0]["pattern_intervention_contract"]["allowed_kinds"] = [
            "routing_projection"
        ]
        row = plan["task_matrix"][0]

        with self.assertRaisesRegex(ValueError, "pattern contract is not canonical"):
            self._score_probe(plan, row)

    def test_tampered_pattern_direction_is_rejected_during_score_load(self) -> None:
        plan = self._pattern_plan()
        row = next(item for item in plan["task_matrix"] if item.get("pattern_id"))
        row["expected_effect_direction"] = "positive"

        with self.assertRaisesRegex(ValueError, "direction is not canonical"):
            self._score_probe(plan, row)

    def test_v02_pattern_row_needs_matrix_id(self) -> None:
        plan = self._pattern_plan()
        row = next(item for item in plan["task_matrix"] if item.get("pattern_id"))
        row.pop("matrix_row_id")

        with self.assertRaisesRegex(ValueError, "requires matrix_row_id"):
            self._score_probe(plan, row)

    def test_tampered_ablation_attachment_is_rejected(self) -> None:
        plan = self._pattern_plan()
        row = next(
            item
            for item in plan["task_matrix"]
            if item.get("pattern_id") and item["variant_id"] == "ablated"
        )
        row["skill_attachment"] += "\nTampered intervention.\n"

        with self.assertRaisesRegex(ValueError, "canonical one-section ablation"):
            self._score_probe(plan, row)

    def test_tampered_original_attachment_is_rejected(self) -> None:
        plan = self._pattern_plan()
        row = next(
            item
            for item in plan["task_matrix"]
            if item.get("pattern_id") and item["variant_id"] == "original"
        )
        row["skill_attachment"] += "\nTampered control.\n"

        with self.assertRaisesRegex(ValueError, "does not match skill_digest"):
            self._score_probe(plan, row)

    def test_legacy_rows_stay_hypothesis(self) -> None:
        plan = self._pattern_plan()
        plan["schema"] = "tmcp-skill-evaluation-plan-v0.1"
        pattern_rows = [row for row in plan["task_matrix"] if row.get("pattern_id")]
        for row in pattern_rows:
            row.pop("matrix_row_id")
            row.pop("tested_atom")
            row.pop("pattern_intervention_contract")
        original = next(row for row in pattern_rows if row["variant_id"] == "original")

        report = self._score_probe(plan, original)

        claim = report["pattern_claims"][0]
        self.assertEqual(claim["evidence_level"], "hypothesis")
        self.assertFalse(claim["plan_contract_trusted"])
        self.assertFalse(claim["promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
