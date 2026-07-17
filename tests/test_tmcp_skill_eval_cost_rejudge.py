"""Focused contracts for the independent blind cost-rejudge harness."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import scripts.tmcp_skill_eval_cost_rejudge as cost_rejudge
import scripts.tmcp_skill_eval_cost_rejudge_runtime as cost_rejudge_runtime
from scripts.tmcp_skill_eval_campaign_protocol import (
    CAMPAIGN_PROTOCOL,
    COST_REJUDGE_CRITERION,
    _audit_event_stream,
    _sha256_file,
    cost_rejudge_output_schema,
    cost_rejudge_prompt,
    judge_prompt,
    validate_cost_rejudgment,
)


class CostRejudgeProtocolTests(unittest.TestCase):
    def test_judge_and_cost_rejudge_prompts_are_separate_and_blind(self) -> None:
        row = {
            "prompt": "TASK_ONLY",
            "variant_id": "original",
            "skill_attachment": "ATTACHMENT_SECRET",
            "expected_observables": ["OBSERVABLE"],
            "failure_smells": ["SMELL"],
        }

        original_prompt = judge_prompt(row, "ARTIFACT", first_principles="PRINCIPLES")
        rejudge_prompt = cost_rejudge_prompt(
            "TASK_ONLY",
            "ARTIFACT",
            cost_bar="CHECKOUT_SWEEP_REQUIRED",
        )

        self.assertIn("PRINCIPLES", original_prompt)
        self.assertIn("OBSERVABLE", original_prompt)
        self.assertIn("SMELL", original_prompt)
        self.assertIn("TASK_ONLY", rejudge_prompt)
        self.assertIn("ARTIFACT", rejudge_prompt)
        self.assertIn("CHECKOUT_SWEEP_REQUIRED", rejudge_prompt)
        self.assertIn(COST_REJUDGE_CRITERION, rejudge_prompt)
        for forbidden in ("ATTACHMENT_SECRET", "original", "ablated"):
            self.assertNotIn(forbidden, rejudge_prompt)

    def test_cost_rejudge_schema_and_validator_require_one_consistent_citation(
        self,
    ) -> None:
        payload = {
            "cost_regression": False,
            "evidence": [
                {
                    "criterion": COST_REJUDGE_CRITERION,
                    "status": "necessary",
                    "citation": "The artifact requires a checkout sweep.",
                }
            ],
            "rationale": "The specified integrity control is required.",
        }

        self.assertEqual(validate_cost_rejudgment(payload), payload)
        schema = cost_rejudge_output_schema()
        self.assertEqual(
            schema["required"], ["cost_regression", "evidence", "rationale"]
        )
        evidence_properties = schema["properties"]["evidence"]["items"]["properties"]
        self.assertEqual(evidence_properties["criterion"]["type"], "string")
        self.assertEqual(evidence_properties["status"]["type"], "string")
        inconsistent = {
            **payload,
            "cost_regression": True,
        }
        with self.assertRaisesRegex(ValueError, "disagrees"):
            validate_cost_rejudgment(inconsistent)
        missing_citation = {
            **payload,
            "evidence": [{**payload["evidence"][0], "citation": ""}],
        }
        with self.assertRaisesRegex(ValueError, "citation"):
            validate_cost_rejudgment(missing_citation)


class CostRejudgeArgumentTests(unittest.TestCase):
    def test_baseline_trace_count_is_allowed_but_zero_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cost_bar = root / "cost-bar.md"
            cost_bar.write_text("faithful bar", encoding="utf-8")
            args = Namespace(
                concurrency=1,
                timeout_seconds=10,
                max_transient_retries=0,
                retry_backoff_seconds=0.0,
                expected_trace_count=36,
                max_cells=None,
                source_runs=root / "source-runs",
                output_dir=root / "output",
                cleanroom=root / "cleanroom",
                cost_bar_file=cost_bar,
            )

            cost_rejudge._validate_args(args)
            args.expected_trace_count = 0
            with self.assertRaisesRegex(ValueError, "expected-trace-count"):
                cost_rejudge._validate_args(args)

    def test_preregistered_policy_binds_every_rejudge_execution_setting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cost_bar = root / "cost-evaluation-bar.md"
            cost_bar.write_text("faithful bar\n", encoding="utf-8")
            args = Namespace(
                expected_trace_count=1,
                model="gpt-5.6-sol",
                judge_effort="high",
                seed=7,
                cost_bar_file=cost_bar,
            )
            plan = {
                "experiment": {
                    "cost_rejudge_policy": {
                        "schema": "tmcp-composition-cost-rejudge-policy-v0.1",
                        "expected_trace_count": 1,
                        "model": "gpt-5.6-sol",
                        "judge_effort": "high",
                        "seed": 7,
                        "cost_bar_file": cost_bar.name,
                        "cost_bar_sha256": _sha256_file(cost_bar),
                        "raw_labels_preserved": True,
                        "complete_before_promotion": True,
                        "process_independence": {
                            "fresh_judge": True,
                            "fresh_session": True,
                            "judge_blinded": True,
                            "condition_hidden": True,
                            "source_artifact_only": True,
                            "isolated_session": True,
                            "model_identity_independence_claimed": False,
                        },
                        "claim_boundary": "cost-only blind adjudication",
                    }
                }
            }

            binding = cost_rejudge.preregistered_cost_rejudge_binding_for_args(
                plan, args
            )

            self.assertEqual(binding["cost_bar_sha256"], _sha256_file(cost_bar))
            args.seed = 8
            with self.assertRaisesRegex(ValueError, "seed"):
                cost_rejudge.preregistered_cost_rejudge_binding_for_args(plan, args)


class CostRejudgeSourceTests(unittest.TestCase):
    def _write_stage(
        self,
        cell_dir: Path,
        *,
        stage: str,
        output_name: str,
        output: str,
        thread_id: str,
    ) -> dict:
        output_path = cell_dir / output_name
        output_path.write_text(output, encoding="utf-8")
        events = "\n".join(
            json.dumps(event)
            for event in (
                {"type": "thread.started", "thread_id": thread_id},
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message"}},
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )
        )
        events_path = cell_dir / f"{stage}-events.jsonl"
        stderr_path = cell_dir / f"{stage}-stderr.log"
        usage_path = cell_dir / f"{stage}-usage.json"
        events_path.write_text(events, encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        usage = {"input_tokens": 1, "output_tokens": 1}
        usage_path.write_text(json.dumps(usage), encoding="utf-8")
        marker = {
            "schema": "tmcp-campaign-stage-v0.1",
            "stage": stage,
            "output_sha256": _sha256_file(output_path),
            "events_sha256": _sha256_file(events_path),
            "stderr_sha256": _sha256_file(stderr_path),
            "event_audit": _audit_event_stream(events),
            "usage": usage,
        }
        (cell_dir / f"{stage}-complete.json").write_text(
            json.dumps(marker), encoding="utf-8"
        )
        return marker

    def _write_one_source_campaign(self, root: Path) -> tuple[Path, Path, dict]:
        plan_path = root / "plan.json"
        runs = root / "runs"
        cell_id = "campaign-cell-1"
        cell_dir = runs / "cells" / cell_id
        cell_dir.mkdir(parents=True)
        plan = {
            "task_matrix": [
                {"matrix_row_id": "row-1", "task_id": "task-1", "prompt": "TASK_ONLY"}
            ]
        }
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        runner = self._write_stage(
            cell_dir,
            stage="runner",
            output_name="runner.txt",
            output="ARTIFACT_ONLY",
            thread_id="source-runner",
        )
        judge = self._write_stage(
            cell_dir,
            stage="judge",
            output_name="judge.json",
            output="{}",
            thread_id="source-judge",
        )
        trace = {
            "schema": "tmcp-skill-eval-trace-v0.1",
            "trace_id": "trace-1",
            "experiment_id": "experiment-1",
            "matrix_row_id": "row-1",
            "task_id": "task-1",
            "campaign": {
                "cell_id": cell_id,
                "runner_artifact": f"cells/{cell_id}/runner.txt",
                "runner_artifact_sha256": runner["output_sha256"],
                "judge_artifact": f"cells/{cell_id}/judge.json",
                "judge_artifact_sha256": judge["output_sha256"],
            },
            "provenance": {
                "runner_blinded": True,
                "judge_blinded": True,
                "isolated_session": True,
                "runner_event_audit": runner["event_audit"],
                "judge_event_audit": judge["event_audit"],
            },
            "case_verdict": {"cost_regression": True},
        }
        (cell_dir / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
        (runs / "traces.json").write_text(json.dumps([trace]), encoding="utf-8")
        manifest = {
            "schema": CAMPAIGN_PROTOCOL,
            "experiment_id": "experiment-1",
            "plan_sha256": _sha256_file(plan_path),
            "cells": [{"cell_id": cell_id, "matrix_row_id": "row-1"}],
        }
        (runs / "campaign-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return plan_path, runs, trace

    def test_source_loader_is_read_only_and_binds_runner_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, runs, trace = self._write_one_source_campaign(root)
            before = {
                path.relative_to(runs): _sha256_file(path)
                for path in runs.rglob("*")
                if path.is_file()
            }

            _, _, sources, threads = cost_rejudge._load_source_traces(
                source_plan=plan_path,
                source_runs=runs,
                expected_trace_count=1,
            )

            self.assertEqual(len(sources), 1)
            self.assertEqual(
                sources[0].source_trace_digest,
                cost_rejudge._canonical_json_digest(trace),
            )
            self.assertEqual(sources[0].runner_path.read_text(), "ARTIFACT_ONLY")
            self.assertEqual(threads, {"source-runner", "source-judge"})
            after = {
                path.relative_to(runs): _sha256_file(path)
                for path in runs.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)

    def test_predeclared_cost_bar_is_allowed_in_an_otherwise_empty_output_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            cost_bar = output_dir / "cost-evaluation-bar.md"
            cost_bar.write_text("bar", encoding="utf-8")

            self.assertEqual(
                cost_rejudge._unexpected_output_entries(output_dir, cost_bar), []
            )
            (output_dir / "unrelated.json").write_text("{}", encoding="utf-8")
            self.assertEqual(
                [
                    path.name
                    for path in cost_rejudge._unexpected_output_entries(
                        output_dir, cost_bar
                    )
                ],
                ["unrelated.json"],
            )

    def test_source_summary_preserves_the_cost_bar_file_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_plan = root / "plan.json"
            source_manifest = root / "campaign-manifest.json"
            source_traces = root / "traces.json"
            cost_bar = root / "cost-evaluation-bar.md"
            for path in (source_plan, source_manifest, source_traces):
                path.write_text("{}\n", encoding="utf-8")
            cost_bar.write_text("faithful bar\n", encoding="utf-8")

            summary = cost_rejudge._source_summary(
                source_plan=source_plan,
                source_runs=root,
                source_manifest=source_manifest,
                source_traces=source_traces,
                expected_trace_count=1,
                cost_bar_file=cost_bar,
                cost_bar=cost_bar.read_text(encoding="utf-8").strip(),
            )

            self.assertEqual(summary["cost_bar_sha256"], _sha256_file(cost_bar))
            self.assertNotEqual(
                summary["cost_bar_sha256"], summary["cost_bar_prompt_sha256"]
            )

    def test_dry_run_records_the_preregistered_cost_rejudge_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, runs, _ = self._write_one_source_campaign(root)
            cost_bar = root / "cost-evaluation-bar.md"
            cost_bar.write_text("faithful bar\n", encoding="utf-8")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["experiment"] = {
                "cost_rejudge_policy": {
                    "schema": "tmcp-composition-cost-rejudge-policy-v0.1",
                    "expected_trace_count": 1,
                    "model": "gpt-5.6-sol",
                    "judge_effort": "high",
                    "seed": 7,
                    "cost_bar_file": cost_bar.name,
                    "cost_bar_sha256": _sha256_file(cost_bar),
                    "raw_labels_preserved": True,
                    "complete_before_promotion": True,
                    "process_independence": {
                        "fresh_judge": True,
                        "fresh_session": True,
                        "judge_blinded": True,
                        "condition_hidden": True,
                        "source_artifact_only": True,
                        "isolated_session": True,
                        "model_identity_independence_claimed": False,
                    },
                    "claim_boundary": "cost-only blind adjudication",
                }
            }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            manifest_path = runs / "campaign-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["plan_sha256"] = _sha256_file(plan_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            args = Namespace(
                source_plan=plan_path,
                source_runs=runs,
                cost_bar_file=cost_bar,
                output_dir=root / "independent-rejudge",
                codex_home=root / "codex-home",
                cleanroom=root / "cleanroom",
                model="gpt-5.6-sol",
                judge_effort="high",
                seed=7,
                concurrency=1,
                timeout_seconds=10,
                max_transient_retries=0,
                retry_backoff_seconds=0.0,
                max_cells=None,
                expected_trace_count=1,
                codex_bin="codex",
                dry_run=True,
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = asyncio.run(cost_rejudge.run(args))

            self.assertEqual(exit_code, 0)
            rendered = json.loads(output.getvalue())
            self.assertEqual(
                rendered["preregistered_cost_rejudge"]["cost_bar_sha256"],
                _sha256_file(cost_bar),
            )
            self.assertEqual(
                rendered["source"]["cost_bar_sha256"], _sha256_file(cost_bar)
            )

    def test_harness_digest_covers_each_local_rejudge_module(self) -> None:
        self.assertTrue(
            {
                "tmcp_skill_eval_cost_rejudge.py",
                "tmcp_skill_eval_cost_rejudge_runtime.py",
                "tmcp_skill_eval_cost_rejudge_source.py",
            }.issubset(cost_rejudge._harness_digests())
        )

    def test_rejudge_execution_writes_only_independent_output_and_keeps_prompt_blind(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, runs, _ = self._write_one_source_campaign(root)
            _, _, sources, _ = cost_rejudge._load_source_traces(
                source_plan=plan_path,
                source_runs=runs,
                expected_trace_count=1,
            )
            source = sources[0]
            cell = cost_rejudge.build_cost_rejudge_cells(sources, seed=7)[0]
            output_dir = root / "independent-rejudge"
            cleanroom = root / "cleanroom"
            cleanroom.mkdir()
            args = Namespace(
                output_dir=output_dir,
                cleanroom=cleanroom,
                codex_bin="codex",
                model="gpt-5.6-sol",
                codex_home=root,
                timeout_seconds=10,
                judge_effort="high",
                prompt_context_sha256="context-sha",
            )
            captured: dict[str, str] = {}

            async def fake_run_stage(**kwargs: object) -> dict:
                output_path = kwargs["output_path"]
                assert isinstance(output_path, Path)
                captured["prompt"] = str(kwargs["prompt"])
                payload = {
                    "cost_regression": False,
                    "evidence": [
                        {
                            "criterion": COST_REJUDGE_CRITERION,
                            "status": "necessary",
                            "citation": "The artifact says to inspect checkout state.",
                        }
                    ],
                    "rationale": "The work is required by the bar.",
                }
                output_path.write_text(json.dumps(payload), encoding="utf-8")
                return {
                    "event_audit": {"passed": True, "thread_id": "fresh-judge"},
                    "output_sha256": _sha256_file(output_path),
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }

            source_digest_before = _sha256_file(source.runner_path)
            with patch.object(cost_rejudge_runtime, "_run_stage", fake_run_stage):
                entry = asyncio.run(
                    cost_rejudge._execute_cell(
                        cell,
                        source=source,
                        cost_bar="CHECKOUT_SWEEP_REQUIRED",
                        args=args,
                        semaphore=asyncio.Semaphore(1),
                    )
                )

            self.assertFalse(entry["cost_regression"])
            self.assertTrue(entry["provenance"]["fresh_judge"])
            self.assertTrue(entry["provenance"]["fresh_session"])
            self.assertTrue(entry["provenance"]["condition_hidden"])
            self.assertTrue(entry["provenance"]["source_artifact_only"])
            self.assertNotIn("original", captured["prompt"])
            self.assertNotIn("ablated", captured["prompt"])
            self.assertNotIn("skill_attachment", captured["prompt"])
            self.assertEqual(_sha256_file(source.runner_path), source_digest_before)
            self.assertTrue(
                (output_dir / "cells" / cell.cell_id / "cost-rejudge.json").is_file()
            )


if __name__ == "__main__":
    unittest.main()
