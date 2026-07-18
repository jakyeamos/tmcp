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
import scripts.verify_cost_rejudge as verify_cost_rejudge
from scripts.tmcp_skill_eval_campaign_protocol import (
    CAMPAIGN_PROTOCOL,
    COST_REJUDGE_PROTOCOL,
    COST_REJUDGE_CRITERION,
    COST_REJUDGE_SCHEMA_VERSION,
    DISABLED_CODEX_FEATURES,
    _audit_event_stream,
    _sha256_file,
    _sha256_text,
    cost_rejudge_output_schema,
    cost_rejudge_prompt,
    judge_prompt,
    validate_cost_rejudgment,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


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

    def _write_complete_rejudge_bundle(
        self, root: Path
    ) -> tuple[Path, Path, Path, Path]:
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
        source_manifest_path = runs / "campaign-manifest.json"
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        source_manifest["plan_sha256"] = _sha256_file(plan_path)
        source_manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
        _, source_manifest, sources, _ = cost_rejudge._load_source_traces(
            source_plan=plan_path,
            source_runs=runs,
            expected_trace_count=1,
        )
        cell = cost_rejudge.build_cost_rejudge_cells(sources, seed=7)[0]
        source = sources[0]
        output_dir = root / "independent-rejudge"
        cell_dir = output_dir / "cells" / cell.cell_id
        cell_dir.mkdir(parents=True)
        schema = cost_rejudge_output_schema()
        root_schema_path = output_dir / "cost-rejudge-output.schema.json"
        root_schema_path.write_text(
            json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8"
        )
        cell_schema_path = cell_dir / "cost-rejudge-output.schema.json"
        cell_schema_path.write_text(
            json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8"
        )
        verdict = {
            "cost_regression": False,
            "evidence": [
                {
                    "criterion": COST_REJUDGE_CRITERION,
                    "status": "necessary",
                    "citation": "The bar requires the one verification step.",
                }
            ],
            "rationale": "The verification is necessary under the supplied bar.",
        }
        marker = self._write_stage(
            cell_dir,
            stage="cost-rejudge",
            output_name="cost-rejudge.json",
            output=json.dumps(verdict),
            thread_id="independent-cost-judge",
        )
        marker["prompt_sha256"] = _sha256_text(
            cost_rejudge_prompt(
                source.row["prompt"],
                source.runner_path.read_text(encoding="utf-8").strip(),
                cost_bar=cost_bar.read_text(encoding="utf-8").strip(),
            )
        )
        marker["output_schema_sha256"] = _sha256_file(cell_schema_path)
        (cell_dir / "cost-rejudge-complete.json").write_text(
            json.dumps(marker), encoding="utf-8"
        )
        launch_args = Namespace(
            expected_trace_count=1,
            model="gpt-5.6-sol",
            judge_effort="high",
            seed=7,
            cost_bar_file=cost_bar,
        )
        binding = cost_rejudge.preregistered_cost_rejudge_binding_for_args(
            plan, launch_args
        )
        prompt_context_sha256 = "sha256:prompt-input-preflight"
        preflight_audit = {
            "passed": True,
            "message_count": 2,
            "roles": ["developer", "user"],
            "forbidden_markers": ["<skills_instructions>"],
            "prompt_context_sha256": prompt_context_sha256,
        }
        source_summary = cost_rejudge._source_summary(
            source_plan=plan_path,
            source_runs=runs,
            source_manifest=runs / "campaign-manifest.json",
            source_traces=runs / "traces.json",
            expected_trace_count=1,
            cost_bar_file=cost_bar,
            cost_bar=cost_bar.read_text(encoding="utf-8").strip(),
        )
        manifest = {
            "schema": COST_REJUDGE_PROTOCOL,
            "cost_rejudgments_schema": cost_rejudge.COST_REJUDGMENTS_SCHEMA,
            "experiment_id": source_manifest["experiment_id"],
            "source": source_summary,
            "preregistered_cost_rejudge": binding,
            "cost_rejudge_schema_version": COST_REJUDGE_SCHEMA_VERSION,
            "cost_rejudge_schema_sha256": _sha256_text(
                json.dumps(schema, sort_keys=True, separators=(",", ":"))
            ),
            "cost_rejudge_protocol_sha256": _sha256_text(
                cost_rejudge_prompt("<TASK>", "<ARTIFACT>", cost_bar="<COST_BAR>")
            ),
            "model": "gpt-5.6-sol",
            "judge_effort": "high",
            "seed": 7,
            "cell_count": 1,
            "cells": [
                {
                    "order": cell.order,
                    "cell_id": cell.cell_id,
                    "trace_id": cell.trace_id,
                    "source_trace_digest": cell.source_trace_digest,
                    "matrix_row_id": cell.matrix_row_id,
                    "runner_artifact": cell.runner_artifact,
                    "runner_artifact_sha256": cell.runner_artifact_sha256,
                    "raw_judge_artifact": cell.raw_judge_artifact,
                    "raw_judge_artifact_sha256": cell.raw_judge_artifact_sha256,
                }
            ],
            "isolation": {
                "ephemeral_process_per_role": True,
                "temporary_codex_home_per_role": True,
                "skills_include_instructions": False,
                "disabled_features": list(DISABLED_CODEX_FEATURES),
                "event_stream_audited": True,
                "sandbox": "read-only",
                "prompt_input_preflight": preflight_audit,
                "remote_schema_preflight_required": True,
            },
        }
        (output_dir / "cost-rejudge-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (output_dir / "prompt-input-preflight.json").write_text(
            json.dumps({"audit": preflight_audit, "prompt_input": []}),
            encoding="utf-8",
        )
        remote_prompt = cost_rejudge_prompt(
            "State whether the sentence requires unnecessary work.",
            "The sentence states one necessary verification step.",
            cost_bar=(
                "Necessary verification work is not a cost regression; mark a "
                "regression only for material unnecessary execution work."
            ),
        )
        (output_dir / "remote-schema-preflight.json").write_text(
            json.dumps(
                {
                    "schema": "tmcp-remote-schema-preflight-v0.1",
                    "passed": True,
                    "model": "gpt-5.6-sol",
                    "effort": "high",
                    "output_schema_sha256": _sha256_file(root_schema_path),
                    "prompt_sha256": _sha256_text(remote_prompt),
                }
            ),
            encoding="utf-8",
        )
        entry = {
            "trace_id": cell.trace_id,
            "source_trace_digest": cell.source_trace_digest,
            "cost_regression": verdict["cost_regression"],
            "evidence": verdict["evidence"],
            "rationale": verdict["rationale"],
            "provenance": {
                "fresh_judge": True,
                "fresh_session": True,
                "judge_blinded": True,
                "condition_hidden": True,
                "source_artifact_only": True,
                "isolated_session": True,
                "prompt_context_sha256": prompt_context_sha256,
                "disabled_features": list(DISABLED_CODEX_FEATURES),
                "judge_event_audit": marker["event_audit"],
                "rejudge_artifact_sha256": marker["output_sha256"],
                "usage": marker["usage"],
            },
        }
        (output_dir / "cost-rejudgments.json").write_text(
            json.dumps(
                {
                    "schema": cost_rejudge.COST_REJUDGMENTS_SCHEMA,
                    "source": source_summary,
                    "preregistered_cost_rejudge": binding,
                    "rejudgments": [entry],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "cost-rejudge-summary.json").write_text(
            json.dumps(
                {
                    "planned_cells": 1,
                    "selected_cells": 1,
                    "completed_cells": 1,
                    "errors": 0,
                    "cost_regressions": 0,
                    "unique_judge_threads": 1,
                    "expected_judge_threads_at_completion": 1,
                    "usage": {"traces": 1, "input_tokens": 1, "output_tokens": 1},
                }
            ),
            encoding="utf-8",
        )
        return plan_path, runs, cost_bar, output_dir

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

    def test_standalone_verifier_accepts_a_complete_policy_bound_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, runs, cost_bar, output_dir = self._write_complete_rejudge_bundle(
                root
            )
            before = {
                path.relative_to(root): _sha256_file(path)
                for path in root.rglob("*")
                if path.is_file()
            }

            report = verify_cost_rejudge.verify_cost_rejudge(
                source_plan=plan_path,
                source_runs=runs,
                cost_bar_file=cost_bar,
                rejudge_runs=output_dir,
                expected_trace_count=1,
            )

            self.assertTrue(report["static"]["promotion_ready"])
            self.assertEqual(report["static"]["policy_binding"], "bound")
            after = {
                path.relative_to(root): _sha256_file(path)
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_standalone_verifier_rejects_a_sidecar_changed_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, runs, cost_bar, output_dir = self._write_complete_rejudge_bundle(
                root
            )
            sidecar_path = output_dir / "cost-rejudgments.json"
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar["rejudgments"][0]["rationale"] = "Rewritten after review."
            sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match cell artifacts"):
                verify_cost_rejudge.verify_cost_rejudge(
                    source_plan=plan_path,
                    source_runs=runs,
                    cost_bar_file=cost_bar,
                    rejudge_runs=output_dir,
                    expected_trace_count=1,
                )

    def test_archived_cost_rejudges_are_not_reproducible_without_their_bars(
        self,
    ) -> None:
        evidence_root = REPO_ROOT / "docs/evidence/skill-eval-multiconfig-2026-07-17"
        cases = (
            {
                "source_plan": evidence_root / "generated/tmcp-skill-evaluation-plan.json",
                "source_runs": evidence_root / "runs",
                "cost_bar_file": evidence_root / "cost-rejudge/cost-evaluation-bar.md",
                "rejudge_runs": evidence_root / "cost-rejudge/approved-run-v2",
                "expected_trace_count": 72,
            },
            {
                "source_plan": evidence_root
                / "fresh-baseline/generated/tmcp-skill-evaluation-plan.json",
                "source_runs": evidence_root / "fresh-baseline/runs",
                "cost_bar_file": evidence_root
                / "fresh-baseline/inputs/cost-evaluation-bar.md",
                "rejudge_runs": evidence_root / "fresh-baseline/cost-rejudge/run",
                "expected_trace_count": 36,
            },
        )
        for case in cases:
            with self.subTest(rejudge_runs=case["rejudge_runs"]):
                with self.assertRaisesRegex(
                    ValueError,
                    "(source cost_bar_sha256 does not match inputs|Cost bar file is missing)",
                ):
                    verify_cost_rejudge.verify_cost_rejudge(**case)

    def test_guidebook_and_catalog_keep_archived_cost_adjudication_unresolved(
        self,
    ) -> None:
        guidebook = (REPO_ROOT / "docs/SKILL_WRITING_GUIDEBOOK.md").read_text(
            encoding="utf-8"
        )
        catalog = json.loads(
            (REPO_ROOT / "docs/SKILL_PATTERN_CATALOG.json").read_text(
                encoding="utf-8"
            )
        )
        entry = next(
            item
            for item in catalog["guidebook_entries"]
            if item["pattern_id"] == "evaluation.staged-workflow-section"
        )
        sample = entry["sample"]

        self.assertIn("diagnostic history, not a reproducible adjudication", guidebook)
        self.assertIn("Every currently shipped entry is on `hold`.", guidebook)
        self.assertNotIn(
            "resolved the raw checkout-sweep labels as non-regressions", guidebook
        )
        self.assertTrue(
            all(
                (item.get("promotion") or {}).get("eligible") is False
                for item in catalog["guidebook_entries"]
            )
        )
        self.assertFalse(sample["cost_rejudgment_applied"])
        self.assertIsNone(sample["cost_regression"])
        self.assertIsNone(sample["regression_free"])
        self.assertEqual(sample["cost_adjudication"]["status"], "unresolved")
        self.assertIn(
            "historical cost sidecar is not reproducible against the retained cost bar",
            entry["promotion"]["gaps"],
        )

    def test_campaign_ledger_keeps_composition_evidence_tiers_distinct(self) -> None:
        ledger_path = (
            REPO_ROOT
            / "docs/evidence/skill-eval-multiconfig-2026-07-17"
            / "skill-campaign-queue.md"
        )
        if not ledger_path.is_file():
            self.skipTest("source-only campaign ledger is not packaged")
        ledger = ledger_path.read_text(encoding="utf-8")

        self.assertIn("evidence-aware intake ledger, not a launch order", ledger)
        self.assertIn("`composition-study-acaca2f2eef3c864`", ledger)
        self.assertIn(
            "does not test TMCP live selection, source adherence, or corpus quality",
            ledger,
        )
        self.assertIn("Packet-probed", ledger)
        self.assertIn("**selection-only**", ledger)
        self.assertIn("Candidate", ledger)
        self.assertIn(
            "TMCP compiler + `refactor-clean` | Fixture approved for preregistration; packet-probed",
            ledger,
        )
        self.assertIn("TMCP compiler + `write-docs` | Packet-probed", ledger)
        self.assertIn("TMCP compiler + `wizard` | Packet-probed", ledger)
        self.assertIn("TMCP compiler + `fold-feature-branches` | Packet-probed", ledger)
        self.assertIn("TMCP compiler + `opencli-autofix` | Packet-probed", ledger)
        self.assertIn("no behavioral calls have\n  been made", ledger)
        self.assertIn(
            "cannot authorize a corpus rewrite or a behavioral claim", ledger
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
