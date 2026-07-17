from __future__ import annotations

import json
import tempfile
import unittest
import asyncio
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import scripts.tmcp_skill_eval_campaign_runtime as campaign_runtime
import scripts.tmcp_skill_eval_campaign_protocol as campaign_protocol
import scripts.tmcp_skill_eval_campaign as campaign
from scripts.tmcp_skill_eval_campaign_protocol import (
    CampaignCell,
    CodexRunError,
    DISABLED_CODEX_FEATURES,
    _audit_event_stream,
    _sha256_file,
    _sha256_text,
    _stable_id,
    _validate_judgment,
    build_cells,
    campaign_readiness_report,
    codex_command,
    judge_criteria,
    judge_output_schema,
    judge_prompt,
    remote_schema_preflight,
    runner_prompt,
)
from scripts.tmcp_skill_eval_campaign_runtime import (
    _load_completed_stage,
    _run_stage,
    _validate_trace,
)


class SkillEvalCampaignTests(unittest.TestCase):
    def _plan(self) -> dict:
        rows = []
        for fixture_index in range(6):
            for variant in ("original", "ablated"):
                rows.append(
                    {
                        "experiment_id": "experiment-1",
                        "matrix_row_id": f"row-{fixture_index}-{variant}",
                        "task_id": f"task-{fixture_index}",
                        "fixture_family": f"family-{fixture_index}",
                        "fixture_digest": f"fixture-{fixture_index}",
                        "pattern_id": "evaluation.staged-workflow-section",
                        "intervention_target": "workflow",
                        "variant_id": variant,
                        "ablation_section": "workflow"
                        if variant == "ablated"
                        else None,
                        "skill_attachment": "ATTACHMENT_ONLY",
                        "prompt": "TASK_ONLY",
                        "expected_observables": ["BAR_SECRET"],
                        "failure_smells": ["SMELL_SECRET"],
                    }
                )
        return {
            "experiment": {"experiment_id": "experiment-1"},
            "task_matrix": rows,
        }

    def test_builds_full_randomized_72_cell_matrix(self) -> None:
        cells = build_cells(
            self._plan(),
            pattern_id="evaluation.staged-workflow-section",
            intervention_target="workflow",
            model="gpt-5.6-sol",
            runner_efforts=["low", "high", "max"],
            repetitions=2,
            expected_fixtures=6,
            seed=7,
            codex_version="codex-cli-0.144.2",
        )

        self.assertEqual(len(cells), 72)
        self.assertEqual(len({cell.cell_id for cell in cells}), 72)
        self.assertEqual({cell.order for cell in cells}, set(range(1, 73)))
        self.assertEqual({cell.runner_effort for cell in cells}, {"low", "high", "max"})

    def test_builds_baseline_and_cross_model_configuration_matrices(self) -> None:
        baseline = build_cells(
            self._plan(),
            pattern_id="evaluation.staged-workflow-section",
            intervention_target="workflow",
            model="fallback-model",
            runner_efforts=[],
            runner_configurations=[
                ("model-a", "low"),
                ("model-a", "high"),
                ("model-b", "high"),
            ],
            design="baseline_reliability",
            repetitions=2,
            expected_fixtures=6,
            seed=7,
            codex_version="codex-cli-0.144.2",
        )

        self.assertEqual(len(baseline), 36)
        self.assertEqual({cell.variant_id for cell in baseline}, {"original"})
        self.assertEqual(
            {cell.runner_model for cell in baseline}, {"model-a", "model-b"}
        )
        self.assertEqual(len({cell.cell_id for cell in baseline}), 36)

    def test_remote_schema_roles_cover_every_runner_and_the_judge(self) -> None:
        args = Namespace(
            model="fallback",
            runner_effort=[],
            runner_config=["runner-a:high", "runner-b:high", "runner-c:high"],
            judge_model="judge-model",
            judge_effort="high",
        )

        roles = campaign._remote_schema_roles(args)

        self.assertEqual(
            [role["role"] for role in roles], ["runner"] * 3 + ["judge"]
        )
        self.assertEqual(
            {role["model"] for role in roles[:3]},
            {"runner-a", "runner-b", "runner-c"},
        )
        self.assertEqual(roles[-1]["model"], "judge-model")

    def test_first_principles_file_is_bound_as_an_inspectable_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "first-principles.txt"
            source.write_text("Faithful evaluation bar.", encoding="utf-8")
            args = Namespace(
                first_principles=None,
                first_principles_file=source,
            )

            campaign._resolve_first_principles(args)

        self.assertEqual(args.first_principles, "Faithful evaluation bar.")
        self.assertEqual(args.first_principles_source["kind"], "file")
        self.assertEqual(args.first_principles_source["path"], str(source.resolve()))
        self.assertEqual(
            args.first_principles_source["sha256"],
            _sha256_text("Faithful evaluation bar."),
        )

    def test_runner_prompt_does_not_leak_bar_or_variant(self) -> None:
        row = self._plan()["task_matrix"][0]

        prompt = runner_prompt(row)

        self.assertIn("ATTACHMENT_ONLY", prompt)
        self.assertIn("TASK_ONLY", prompt)
        self.assertNotIn("BAR_SECRET", prompt)
        self.assertNotIn("SMELL_SECRET", prompt)
        self.assertNotIn("original", prompt)
        wrapper = prompt.split("<instruction_attachment>", 1)[0].lower()
        for forbidden in ("blind", "experiment", "criteria", "variant"):
            self.assertNotIn(forbidden, wrapper)

    def test_judge_prompt_is_condition_blind(self) -> None:
        row = self._plan()["task_matrix"][0]

        prompt = judge_prompt(row, "ARTIFACT", first_principles="PRINCIPLES")

        self.assertIn("BAR_SECRET", prompt)
        self.assertIn("SMELL_SECRET", prompt)
        self.assertIn("PRINCIPLES", prompt)
        self.assertIn("ARTIFACT", prompt)
        self.assertIn("TASK_ONLY", prompt)
        self.assertNotIn("original", prompt)
        self.assertNotIn("ATTACHMENT_ONLY", prompt)
        criteria = judge_criteria(row)
        self.assertEqual(len(criteria), 2)
        self.assertTrue(criteria[1].startswith("S1 (failure smell must be absent)"))

    def test_codex_command_enforces_cleanroom_isolation(self) -> None:
        command = codex_command(
            codex_bin="codex",
            model="gpt-5.6-sol",
            effort="high",
            cleanroom=Path("/tmp/cleanroom"),
            output_path=Path("/tmp/output.txt"),
            output_schema=None,
        )

        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("skills.include_instructions=false", command)
        self.assertIn("read-only", command)
        for feature in DISABLED_CODEX_FEATURES:
            self.assertIn(feature, command)
        self.assertEqual(command[-1], "-")

    def test_judgment_requires_exact_criteria_and_citations(self) -> None:
        criteria = ["O1: expected", "S1 (failure smell must be absent): unsafe"]
        valid = {
            "passed": False,
            "evidence": [
                {"criterion": criteria[0], "status": "pass", "citation": "quote"},
                {
                    "criterion": criteria[1],
                    "status": "fail",
                    "citation": "unsafe recommendation",
                },
            ],
            "safety_regression": True,
            "cost_regression": False,
            "rationale": "The smell is present.",
        }

        self.assertEqual(
            _validate_judgment(valid, expected_criteria=criteria),
            valid,
        )
        malformed = {**valid, "evidence": [{"status": "fail"}, valid["evidence"][1]]}
        with self.assertRaisesRegex(ValueError, "invalid fields"):
            _validate_judgment(malformed, expected_criteria=criteria)
        misaligned = {
            **valid,
            "evidence": [valid["evidence"][1], valid["evidence"][0]],
        }
        with self.assertRaisesRegex(ValueError, "does not match"):
            _validate_judgment(misaligned, expected_criteria=criteria)

        keyed = {
            **valid,
            "evidence": {
                "O1": {"status": "pass", "citation": "quote"},
                "S1": {"status": "fail", "citation": "unsafe recommendation"},
            },
        }
        normalized = _validate_judgment(keyed, expected_criteria=criteria)
        self.assertEqual(normalized["evidence"], valid["evidence"])
        schema = judge_output_schema(criteria)
        self.assertEqual(schema["properties"]["evidence"]["required"], ["O1", "S1"])
        self.assertEqual(
            schema["properties"]["evidence"]["properties"]["O1"]["properties"][
                "status"
            ]["type"],
            "string",
        )

    def test_event_audit_rejects_tool_items(self) -> None:
        safe_events = "\n".join(
            json.dumps(event)
            for event in (
                {"type": "thread.started", "thread_id": "thread-1"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message"},
                },
                {"type": "turn.completed", "usage": {"input_tokens": 1}},
            )
        )
        tool_events = safe_events.replace("agent_message", "command_execution")

        self.assertTrue(_audit_event_stream(safe_events)["passed"])
        with self.assertRaisesRegex(ValueError, "Disallowed Codex item"):
            _audit_event_stream(tool_events)
        unknown_events = safe_events.replace("turn.started", "turn.failed")
        with self.assertRaisesRegex(ValueError, "Disallowed Codex event"):
            _audit_event_stream(unknown_events)

    def test_remote_schema_preflight_uses_a_synthetic_isolated_output(self) -> None:
        criteria = ["O1: expected"]

        async def fake_run_codex(**kwargs: object) -> tuple:
            command = kwargs.get("command")
            if not isinstance(command, list) or not all(
                isinstance(item, str) for item in command
            ):
                raise AssertionError("test double expected a Codex command list")
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "evidence": {"O1": {"status": "pass", "citation": "yes"}},
                        "safety_regression": False,
                        "cost_regression": False,
                        "rationale": "The synthetic sentence is present.",
                    }
                ),
                encoding="utf-8",
            )
            return (
                "events",
                "",
                {"input_tokens": 1},
                {"passed": True, "thread_id": "schema-thread"},
            )

        with patch.object(campaign_protocol, "_run_codex", fake_run_codex):
            preflight = asyncio.run(
                remote_schema_preflight(
                    codex_bin="codex",
                    model="judge-model",
                    effort="high",
                    base_codex_home=Path("/unused"),
                    timeout_seconds=10,
                    output_schema=judge_output_schema(criteria),
                    prompt="Synthetic schema acceptance prompt.",
                    validate_output=lambda payload: _validate_judgment(
                        payload, expected_criteria=criteria
                    ),
                )
            )

        self.assertTrue(preflight["passed"])
        self.assertEqual(preflight["model"], "judge-model")
        self.assertEqual(preflight["event_audit"]["thread_id"], "schema-thread")
        self.assertEqual(preflight["retry_audit"]["attempts"], [])

    def test_remote_schema_preflight_retries_only_transient_failures(self) -> None:
        criteria = ["O1: expected"]
        calls = 0

        async def fake_run_codex(**kwargs: object) -> tuple:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise CodexRunError("at capacity")
            command = kwargs["command"]
            assert isinstance(command, list)
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "evidence": {"O1": {"status": "pass", "citation": "yes"}},
                        "safety_regression": False,
                        "cost_regression": False,
                        "rationale": "The synthetic sentence is present.",
                    }
                ),
                encoding="utf-8",
            )
            return ("events", "", {"input_tokens": 1}, {"passed": True})

        with patch.object(campaign_protocol, "_run_codex", fake_run_codex):
            preflight = asyncio.run(
                remote_schema_preflight(
                    codex_bin="codex",
                    model="judge-model",
                    effort="high",
                    base_codex_home=Path("/unused"),
                    timeout_seconds=10,
                    output_schema=judge_output_schema(criteria),
                    prompt="Synthetic schema acceptance prompt.",
                    validate_output=lambda payload: _validate_judgment(
                        payload, expected_criteria=criteria
                    ),
                    retry_backoff_seconds=0,
                )
            )

        self.assertEqual(calls, 2)
        self.assertEqual(preflight["retry_audit"]["successful_attempt"], 2)
        self.assertEqual(
            preflight["retry_audit"]["attempts"][0]["classification"],
            "model_capacity",
        )

    def test_transient_failure_classification_recognizes_service_statuses(self) -> None:
        self.assertEqual(
            campaign_protocol.transient_failure_classification(
                CodexRunError("request failed with 429")
            ),
            "rate_limited",
        )
        self.assertEqual(
            campaign_protocol.transient_failure_classification(
                CodexRunError("request failed with 503")
            ),
            "service_unavailable",
        )

    def test_partial_stage_is_invalidated_instead_of_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell_dir = Path(temporary)
            output_path = cell_dir / "runner.txt"
            output_path.write_text("partial", encoding="utf-8")

            marker = _load_completed_stage(cell_dir, "runner", output_path)

            self.assertIsNone(marker)
            self.assertFalse(output_path.exists())
            invalidations = json.loads(
                (cell_dir / "invalidated-stages.json").read_text(encoding="utf-8")
            )
            self.assertEqual(invalidations[0]["stage"], "runner")
            self.assertTrue(
                (cell_dir / invalidations[0]["archive"] / "runner.txt").is_file()
            )

    def test_missing_final_output_preserves_raw_streams(self) -> None:
        async def completed_without_output(**_kwargs: object) -> tuple:
            return (
                '{"type":"thread.started","thread_id":"thread-1"}\n',
                "diagnostic",
                {"input_tokens": 1},
                {"passed": True, "thread_id": "thread-1"},
            )

        with tempfile.TemporaryDirectory() as temporary:
            cell_dir = Path(temporary)
            args = Namespace(
                codex_bin="codex",
                model="gpt-5.6-sol",
                cleanroom=cell_dir,
                codex_home=cell_dir,
                timeout_seconds=10,
            )
            with patch.object(campaign_runtime, "_run_codex", completed_without_output):
                with self.assertRaisesRegex(RuntimeError, "without writing"):
                    import asyncio

                    asyncio.run(
                        _run_stage(
                            cell_dir=cell_dir,
                            stage="runner",
                            output_path=cell_dir / "runner.txt",
                            output_schema=None,
                            prompt="prompt",
                            effort="low",
                            args=args,
                        )
                    )

            invalidations = json.loads(
                (cell_dir / "invalidated-stages.json").read_text(encoding="utf-8")
            )
            archive = cell_dir / invalidations[0]["archive"]
            self.assertIn(
                "thread.started", (archive / "runner-events.jsonl").read_text()
            )
            self.assertEqual((archive / "runner-stderr.log").read_text(), "diagnostic")

    def test_transient_capacity_failure_is_archived_and_retried(self) -> None:
        calls = 0

        async def capacity_then_success(**kwargs: object) -> tuple:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise CodexRunError(
                    "Codex process exited 1: Selected model is at capacity.",
                    stdout='{"type":"error","message":"Selected model is at capacity."}',
                )
            command = kwargs.get("command")
            if not isinstance(command, list) or not all(
                isinstance(item, str) for item in command
            ):
                raise AssertionError("test double expected a Codex command list")
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("artifact", encoding="utf-8")
            return (
                '{"type":"thread.started","thread_id":"thread-2"}\n'
                '{"type":"turn.started"}\n'
                '{"type":"turn.completed","usage":{"input_tokens":1}}\n',
                "",
                {"input_tokens": 1},
                {"passed": True, "thread_id": "thread-2"},
            )

        async def no_sleep(_seconds: float) -> None:
            return None

        with tempfile.TemporaryDirectory() as temporary:
            cell_dir = Path(temporary)
            args = Namespace(
                codex_bin="codex",
                model="gpt-5.6-sol",
                cleanroom=cell_dir,
                codex_home=cell_dir,
                timeout_seconds=10,
                max_transient_retries=1,
                retry_backoff_seconds=0,
            )
            with (
                patch.object(campaign_runtime, "_run_codex", capacity_then_success),
                patch.object(campaign_runtime.asyncio, "sleep", no_sleep),
            ):
                marker = asyncio.run(
                    _run_stage(
                        cell_dir=cell_dir,
                        stage="runner",
                        output_path=cell_dir / "runner.txt",
                        output_schema=None,
                        prompt="prompt",
                        effort="low",
                        args=args,
                    )
                )

            self.assertEqual(calls, 2)
            self.assertEqual(marker["usage"], {"input_tokens": 1})
            audit = json.loads((cell_dir / "runner-retry-audit.json").read_text())
            self.assertEqual(audit["attempts"][0]["classification"], "model_capacity")
            self.assertTrue((cell_dir / "invalidated" / "runner-attempt-1").is_dir())

    def test_preregistered_readiness_requires_independent_models(self) -> None:
        plan = self._plan()
        plan["experiment"]["analysis_policy"] = {
            "clustered_interval": {
                "method": "fixture_block_bootstrap_by_configuration",
                "confidence": 0.95,
                "cluster_unit": "fixture_digest",
                "resamples": 10000,
                "seed": 7,
            }
        }
        plan["experiment"]["promotion_thresholds"] = {
            "controlled_multi_agent_eval": {
                "minimum_control_pass_rate": 0.5,
                "minimum_per_fixture_control_pass_rate": 0.5,
            }
        }
        configurations = [("model-a", "low"), ("model-a", "high"), ("model-b", "high")]
        plan["experiment"]["campaign_policy"] = {
            "schema": "tmcp-skill-eval-campaign-policy-v0.1",
            "design": "baseline_reliability",
            "runner_configurations": [
                {"model": model, "reasoning_effort": effort}
                for model, effort in configurations
            ],
            "baseline_reliability": {
                "control_variant": "original",
                "minimum_control_pass_rate": 0.5,
                "minimum_per_fixture_control_pass_rate": 0.5,
                "require_predeclared_clustered_interval": True,
            },
            "fixture_review": {
                "independent_reviewer": True,
                "prompt_event_directness": True,
                "bar_skill_expressibility": True,
            },
            "judge_configuration": {"model": "judge-model", "reasoning_effort": "high"},
            "cross_model_confirmation": {
                "required": True,
                "minimum_distinct_runner_models": 2,
                "minimum_fixture_count_per_model": 6,
                "minimum_repetitions_per_cell": 2,
                "require_directional_replication": True,
            },
        }
        cells = build_cells(
            plan,
            pattern_id="evaluation.staged-workflow-section",
            intervention_target="workflow",
            model="fallback-model",
            runner_efforts=[],
            runner_configurations=configurations,
            design="baseline_reliability",
            repetitions=2,
            expected_fixtures=6,
            seed=7,
            codex_version="codex-cli-0.144.2",
        )

        readiness = campaign_readiness_report(
            plan, cells=cells, design="baseline_reliability", judge_model="judge-model"
        )

        self.assertTrue(readiness["ready"])

    def test_resumed_trace_is_bound_to_stage_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            cell = CampaignCell(
                order=1,
                cell_id="cell-1",
                matrix_row_id="row-0-original",
                task_id="task-0",
                variant_id="original",
                fixture_family="family-0",
                fixture_digest="fixture-0",
                replicate_id="replicate-1",
                runner_model="gpt-5.6-sol",
                runner_effort="low",
                configuration_id="config-1",
            )
            row = self._plan()["task_matrix"][0]
            plan = {"experiment": {"experiment_id": "experiment-1"}}
            args = Namespace(
                output_dir=output_dir,
                model="gpt-5.6-sol",
                judge_effort="high",
                first_principles="PRINCIPLES",
                prompt_context_sha256="context-sha",
            )
            cell_dir = output_dir / "cells" / cell.cell_id
            cell_dir.mkdir(parents=True)
            runner_output = cell_dir / "runner.txt"
            judge_output = cell_dir / "judge.json"
            runner_output.write_text("ARTIFACT", encoding="utf-8")
            criteria = judge_criteria(row)
            judge_payload = {
                "passed": True,
                "evidence": {
                    "O1": {"status": "pass", "citation": "artifact quote"},
                    "S1": {"status": "pass", "citation": "smell absent"},
                },
                "safety_regression": False,
                "cost_regression": False,
                "rationale": "All criteria pass.",
            }
            judge_output.write_text(json.dumps(judge_payload), encoding="utf-8")
            judge_schema_path = cell_dir / "judge-output.schema.json"
            judge_schema_path.write_text(
                json.dumps(judge_output_schema(criteria)), encoding="utf-8"
            )

            def write_stage(
                stage: str,
                output_path: Path,
                prompt: str,
                thread_id: str,
                output_schema: Path | None,
            ) -> dict:
                events = "\n".join(
                    json.dumps(event)
                    for event in (
                        {"type": "thread.started", "thread_id": thread_id},
                        {"type": "turn.started"},
                        {
                            "type": "item.completed",
                            "item": {"type": "agent_message"},
                        },
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
                    "prompt_sha256": _sha256_text(prompt),
                    "output_schema_sha256": _sha256_file(output_schema)
                    if output_schema is not None
                    else None,
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

            runner_marker = write_stage(
                "runner", runner_output, runner_prompt(row), "thread-runner", None
            )
            judge_marker = write_stage(
                "judge",
                judge_output,
                judge_prompt(row, "ARTIFACT", first_principles="PRINCIPLES"),
                "thread-judge",
                judge_schema_path,
            )
            judgment = _validate_judgment(judge_payload, expected_criteria=criteria)
            trace = {
                "schema": "tmcp-skill-eval-trace-v0.1",
                "trace_id": _stable_id(cell.cell_id, prefix="trace"),
                "experiment_id": "experiment-1",
                "matrix_row_id": cell.matrix_row_id,
                "replicate_id": cell.replicate_id,
                "task_id": cell.task_id,
                "variant_id": cell.variant_id,
                "agent": {
                    "name": "codex-cli-blind-runner",
                    "model": args.model,
                    "configuration_id": cell.configuration_id,
                },
                "provenance": {
                    "runner_blinded": True,
                    "judge_blinded": True,
                    "isolated_session": True,
                    "prompt_context_sha256": args.prompt_context_sha256,
                    "disabled_features": list(DISABLED_CODEX_FEATURES),
                    "runner_event_audit": runner_marker["event_audit"],
                    "judge_event_audit": judge_marker["event_audit"],
                },
                "observations": [{"kind": "assistant_message", "value": "ARTIFACT"}],
                "human_labels": [{"judge_rationale": judgment["rationale"]}],
                "case_verdict": {
                    "passed": judgment["passed"],
                    "evidence": judgment["evidence"],
                    "safety_regression": False,
                    "cost_regression": False,
                },
                "campaign": {
                    "cell_id": cell.cell_id,
                    "order": cell.order,
                    "runner_model": cell.runner_model,
                    "runner_effort": cell.runner_effort,
                    "judge_model": args.model,
                    "judge_effort": args.judge_effort,
                    "runner_artifact": "cells/cell-1/runner.txt",
                    "judge_artifact": "cells/cell-1/judge.json",
                    "runner_artifact_sha256": runner_marker["output_sha256"],
                    "judge_artifact_sha256": judge_marker["output_sha256"],
                    "usage": {
                        "runner": runner_marker["usage"],
                        "judge": judge_marker["usage"],
                    },
                },
            }

            self.assertEqual(
                _validate_trace(trace, cell=cell, row=row, plan=plan, args=args),
                trace,
            )
            tampered_trace = {**trace, "observations": []}
            with self.assertRaisesRegex(ValueError, "observation"):
                _validate_trace(
                    tampered_trace, cell=cell, row=row, plan=plan, args=args
                )
            runner_output.write_text("TAMPERED", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "completed stage"):
                _validate_trace(trace, cell=cell, row=row, plan=plan, args=args)


if __name__ == "__main__":
    unittest.main()
