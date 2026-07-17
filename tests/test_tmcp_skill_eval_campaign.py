from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.tmcp_skill_eval_campaign import (
    CampaignCell,
    DISABLED_CODEX_FEATURES,
    _audit_event_stream,
    _load_completed_stage,
    _sha256_file,
    _sha256_text,
    _stable_id,
    _validate_trace,
    _validate_judgment,
    build_cells,
    codex_command,
    judge_criteria,
    judge_output_schema,
    judge_prompt,
    runner_prompt,
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
                    "runner_effort": cell.runner_effort,
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
