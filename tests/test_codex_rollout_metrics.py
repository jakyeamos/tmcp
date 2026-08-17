from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "extract_codex_rollout_metrics",
    ROOT / "scripts" / "extract_codex_rollout_metrics.py",
)
assert SPEC and SPEC.loader
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class CodexRolloutMetricsTests(unittest.TestCase):
    def _write_rollout(
        self,
        *,
        tool_name: str | None = "not_tmcp",
        omit_output: bool = False,
        duplicate_records: bool = False,
        conflicting_duplicate: bool = False,
        orphan_output: bool = False,
        session_id: str = "session-1",
        turn_id: str = "turn-1",
    ) -> Path:
        rows = [
            {
                "timestamp": "2026-08-03T12:00:00Z",
                "type": "session_meta",
                "payload": {
                    "session_id": session_id,
                    "model_provider": "openai",
                    "originator": "Codex Desktop",
                    "source": "vscode",
                    "cli_version": "test",
                    "base_instructions": "must not be copied",
                },
            },
            {
                "timestamp": "2026-08-03T12:00:01Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": self._tokens(10, 2),
                        "total_token_usage": self._tokens(10, 2),
                    },
                },
            },
            {
                "timestamp": "2026-08-03T12:01:00Z",
                "type": "turn_context",
                "payload": {"turn_id": turn_id, "model": "gpt-test"},
            },
            {
                "timestamp": "2026-08-03T12:01:00Z",
                "type": "event_msg",
                "payload": {"type": "task_started", "turn_id": turn_id},
            },
            {
                "timestamp": "2026-08-03T12:01:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "exec_command",
                    "arguments": "private tool arguments",
                },
            },
            {
                "timestamp": "2026-08-03T12:01:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "private tool output",
                },
            },
            {
                "timestamp": "2026-08-03T12:01:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": self._tokens(20, 3),
                        "total_token_usage": self._tokens(30, 5),
                    },
                },
            },
            {
                "timestamp": "2026-08-03T12:01:03Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "call-2",
                    "name": tool_name,
                },
            },
        ]
        if not omit_output:
            rows.append(
                {
                    "timestamp": "2026-08-03T12:01:04Z",
                    "type": "response_item",
                    "payload": {"type": "custom_tool_call_output", "call_id": "call-2"},
                }
            )
        rows.extend(
            [
                {
                    "timestamp": "2026-08-03T12:01:04Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": self._tokens(40, 7),
                            "total_token_usage": self._tokens(70, 12),
                        },
                    },
                },
                {
                    "timestamp": "2026-08-03T12:01:05Z",
                    "type": "response_item",
                    "payload": {"type": "message", "content": "private answer"},
                },
                {
                    "timestamp": "2026-08-03T12:01:05Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete",
                        "turn_id": turn_id,
                        "duration_ms": 5000,
                    },
                },
            ]
        )
        if duplicate_records:
            rows.extend(
                [
                    {
                        "timestamp": "2026-08-03T12:01:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "exec_command",
                        },
                    },
                    {
                        "timestamp": "2026-08-03T12:01:02Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "call_id": "call-1",
                        },
                    },
                    {
                        "timestamp": "2026-08-03T12:01:03Z",
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "call_id": "call-2",
                            "name": tool_name,
                        },
                    },
                ]
            )
            if not omit_output:
                rows.append(
                    {
                        "timestamp": "2026-08-03T12:01:04Z",
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call_output",
                            "call_id": "call-2",
                        },
                    }
                )
        if conflicting_duplicate:
            rows.append(
                {
                    "timestamp": "2026-08-03T12:01:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": "call-2",
                        "name": "tmcp_status_conflict",
                    },
                }
            )
        if orphan_output:
            rows.append(
                {
                    "timestamp": "2026-08-03T12:01:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": "orphan-call",
                    },
                }
            )
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        with handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return Path(handle.name)

    @staticmethod
    def _tokens(input_tokens: int, output_tokens: int) -> dict[str, int]:
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": 0,
            "total_tokens": input_tokens + output_tokens,
        }

    def test_extracts_provider_native_metrics_and_stays_incomplete(self) -> None:
        result = extractor.extract_turn(self._write_rollout(), "turn-1")

        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["model"], "gpt-test")
        self.assertEqual(
            result["provider_metrics_available"],
            {
                "wall_time_ms": 5000,
                "input_tokens": 60,
                "output_tokens": 10,
                "model_round_trips": 2,
                "tool_round_trips": 2,
                "tmcp_model_visible_round_trips": 0,
            },
        )
        self.assertFalse(result["scorer_ready"])
        self.assertEqual(
            result["missing_host_metrics"], list(extractor.HOST_COUNTER_FIELDS)
        )
        self.assertEqual(
            result["rollout_tool_calls"],
            [
                {"call_id": "call-1", "name": "exec_command"},
                {"call_id": "call-2", "name": "not_tmcp"},
            ],
        )
        self.assertNotIn("must not be copied", json.dumps(result))
        self.assertNotIn("private", json.dumps(result))

    def test_rejects_terminal_rollout_without_host_observation(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")

        with self.assertRaises(extractor.HostObservationUnavailableError) as context:
            extractor.finalize_terminal_turn(extracted, None)

        self.assertEqual(
            context.exception.disposition,
            extractor.UNAVAILABLE_ATTRIBUTION_DISPOSITION,
        )
        self.assertIn("task_complete", str(context.exception))
        self.assertIn("missing companion evidence is not zero", str(context.exception))
        self.assertNotIn("skill_read_calls", extracted["provider_metrics_available"])
        self.assertNotIn(
            "skill_read_input_tokens", extracted["provider_metrics_available"]
        )

    def test_cli_rejects_terminal_rollout_without_host_observation(self) -> None:
        rollout = self._write_rollout()

        with patch.object(
            sys,
            "argv",
            [
                "extract_codex_rollout_metrics.py",
                "--rollout",
                str(rollout),
                "--turn-id",
                "turn-1",
            ],
        ):
            with self.assertRaises(extractor.HostObservationUnavailableError):
                extractor.main()

    def test_derives_one_tmcp_round_trip_from_exact_authoritative_name(self) -> None:
        result = extractor.extract_turn(
            self._write_rollout(tool_name="tmcp_status"), "turn-1"
        )

        self.assertEqual(
            result["provider_metrics_available"]["tmcp_model_visible_round_trips"],
            1,
        )

    def test_exact_predicate_rejects_lookalike_tool_names(self) -> None:
        self.assertEqual(
            extractor.TMCP_TOOL_NAMES,
            frozenset(extractor.PUBLIC_TOOL_NAMES),
        )
        self.assertIn("expert_rubric_review_plan", extractor.TMCP_TOOL_NAMES)
        self.assertEqual(
            extractor.extract_turn(
                self._write_rollout(tool_name="expert_rubric_review_plan"), "turn-1"
            )["provider_metrics_available"]["tmcp_model_visible_round_trips"],
            1,
        )
        for lookalike in (
            "tmcp_status_extra",
            "prefix_tmcp_status",
            "cat tmcp_status",
            "tmcp/status",
        ):
            with self.subTest(tool_name=lookalike):
                result = extractor.extract_turn(
                    self._write_rollout(tool_name=lookalike), "turn-1"
                )
                self.assertEqual(
                    result["provider_metrics_available"][
                        "tmcp_model_visible_round_trips"
                    ],
                    0,
                )

    def test_rejects_unpaired_tool_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "tool-call evidence is incomplete"):
            extractor.extract_turn(self._write_rollout(omit_output=True), "turn-1")

    def test_rejects_orphan_output_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "tool-call evidence is incomplete"):
            extractor.extract_turn(self._write_rollout(orphan_output=True), "turn-1")

    def test_rejects_inconsistent_provider_token_counters(self) -> None:
        path = self._write_rollout()
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        token_rows = [
            row
            for row in rows
            if row["type"] == "event_msg"
            and row["payload"].get("type") == "token_count"
        ]
        token_rows[-1]["payload"]["info"]["total_token_usage"]["input_tokens"] += 1
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

        with self.assertRaisesRegex(
            ValueError, "provider token evidence is inconsistent"
        ):
            extractor.extract_turn(path, "turn-1")

    def test_deduplicates_repeated_call_and_output_records_by_call_id(self) -> None:
        result = extractor.extract_turn(
            self._write_rollout(tool_name="tmcp_status", duplicate_records=True),
            "turn-1",
        )

        self.assertEqual(result["provider_metrics_available"]["tool_round_trips"], 2)
        self.assertEqual(
            result["provider_metrics_available"]["tmcp_model_visible_round_trips"],
            1,
        )

    def test_rejects_conflicting_duplicate_call_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            extractor.extract_turn(
                self._write_rollout(
                    tool_name="tmcp_status", conflicting_duplicate=True
                ),
                "turn-1",
            )

    def test_rejects_mismatched_call_output_types(self) -> None:
        path = self._write_rollout(tool_name="tmcp_status")
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if (
                row["type"] == "response_item"
                and row["payload"].get("call_id") == "call-2"
            ):
                if row["payload"]["type"] == "custom_tool_call_output":
                    row["payload"]["type"] = "function_call_output"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

        with self.assertRaisesRegex(ValueError, "output types do not match"):
            extractor.extract_turn(path, "turn-1")

    def test_rejects_malformed_tool_name_and_rollout_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "custom_tool_call.name"):
            extractor.extract_turn(self._write_rollout(tool_name=None), "turn-1")

        path = self._write_rollout()
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows.append(
            {
                "timestamp": "2026-08-03T12:01:04Z",
                "type": "response_item",
                "payload": "truncated",
            }
        )
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(ValueError, "payload must be an object"):
            extractor.extract_turn(path, "turn-1")

    def test_merges_only_matching_host_owned_counters(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        observation = self._host_observation()

        result = extractor.merge_host_observation(extracted, observation)

        self.assertTrue(result["scorer_ready"])
        self.assertEqual(
            result["trace"]["provider_metrics"],
            {
                "wall_time_ms": 5000,
                "input_tokens": 60,
                "output_tokens": 10,
                "model_round_trips": 2,
                "tool_round_trips": 2,
                "skill_read_calls": 1,
                "skill_read_input_tokens": 25,
                "tmcp_model_visible_round_trips": 0,
            },
        )
        self.assertEqual(result["trace"]["trace_source"], "codex-host")

    def test_accepts_v04_zero_skill_terminal_observation(self) -> None:
        result = extractor.finalize_terminal_turn(
            extractor.extract_turn(self._write_rollout(), "turn-1"),
            self._host_observation(skill_read_calls=0, skill_read_input_tokens=0),
        )

        self.assertTrue(result["scorer_ready"])
        self.assertEqual(
            result["trace"]["provider_metrics"]["skill_read_calls"],
            0,
        )
        self.assertEqual(
            result["trace"]["provider_metrics"]["skill_read_input_tokens"],
            0,
        )

    def test_accepts_v04_exact_skill_terminal_observation(self) -> None:
        result = extractor.finalize_terminal_turn(
            extractor.extract_turn(self._write_rollout(), "turn-1"),
            self._host_observation(skill_read_calls=1, skill_read_input_tokens=25),
        )

        self.assertTrue(result["scorer_ready"])
        self.assertEqual(
            result["trace"]["provider_metrics"]["skill_read_calls"],
            1,
        )
        self.assertEqual(
            result["trace"]["provider_metrics"]["skill_read_input_tokens"],
            25,
        )

    def test_merges_rollout_derived_tmcp_counter_and_accepts_matching_compat_field(
        self,
    ) -> None:
        extracted = extractor.extract_turn(
            self._write_rollout(tool_name="tmcp_status"), "turn-1"
        )
        observation = self._host_observation(tmcp_round_trips=1)

        result = extractor.merge_host_observation(extracted, observation)

        self.assertEqual(
            result["trace"]["provider_metrics"]["tmcp_model_visible_round_trips"],
            1,
        )

    def test_derived_tmcp_counter_does_not_require_legacy_host_field(self) -> None:
        extracted = extractor.extract_turn(
            self._write_rollout(tool_name="tmcp_status"), "turn-1"
        )
        observation = self._host_observation(tmcp_round_trips=None)

        result = extractor.merge_host_observation(extracted, observation)

        self.assertEqual(
            result["trace"]["provider_metrics"]["tmcp_model_visible_round_trips"],
            1,
        )

    def test_accepts_zero_and_one_full_skill_reads_as_host_owned(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        for skill_read_calls, input_tokens in ((0, 0), (1, 25)):
            with self.subTest(skill_read_calls=skill_read_calls):
                observation = self._host_observation(
                    skill_read_calls=skill_read_calls,
                    skill_read_input_tokens=input_tokens,
                )
                result = extractor.merge_host_observation(extracted, observation)
                self.assertEqual(
                    result["trace"]["provider_metrics"]["skill_read_calls"],
                    skill_read_calls,
                )

    def test_rejects_structured_duplicate_or_cached_skill_read_records(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        observation = self._host_observation()
        observation["host_metrics"]["skill_read_records"] = [
            {"path": "SKILL.md", "input_tokens": 25},
            {"path": "SKILL.md", "input_tokens": 25},
        ]

        with self.assertRaisesRegex(ValueError, "incomplete or unexpected"):
            extractor.merge_host_observation(extracted, observation)

    def test_rejects_truncated_or_invalid_skill_read_counter(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        for field, value in (
            ("skill_read_calls", "truncated"),
            ("skill_read_input_tokens", -1),
            ("skill_read_input_tokens", None),
        ):
            with self.subTest(field=field, value=value):
                observation = self._host_observation()
                observation["host_metrics"][field] = value
                with self.assertRaisesRegex(ValueError, "host_metrics"):
                    extractor.merge_host_observation(extracted, observation)

    def test_rejects_structured_duplicate_host_metrics(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        observation = self._host_observation()
        observation["host_metrics"]["skill_read_records"] = [
            {"path": "SKILL.md", "input_tokens": 25},
            {"path": "SKILL.md", "input_tokens": 25},
        ]

        with self.assertRaisesRegex(ValueError, "incomplete or unexpected"):
            extractor.merge_host_observation(extracted, observation)

    def test_preserves_normal_and_substitution_routing_validation(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        normal = self._host_observation(
            routing_mode="normal",
            packet_injected=False,
            normal_full_skill_load_count=1,
        )
        substitution = self._host_observation(
            routing_mode="substitution",
            packet_injected=True,
            normal_full_skill_load_count=0,
        )

        self.assertTrue(
            extractor.merge_host_observation(extracted, normal)["scorer_ready"]
        )
        self.assertTrue(
            extractor.merge_host_observation(extracted, substitution)["scorer_ready"]
        )

    def test_rejects_inconsistent_substitution_routing(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        observation = self._host_observation(
            routing_mode="substitution", packet_injected=False
        )

        with self.assertRaisesRegex(ValueError, "packet_injected"):
            extractor.merge_host_observation(extracted, observation)

    def test_rejects_duplicate_host_observation_records_at_schema_boundary(
        self,
    ) -> None:
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with handle:
            json.dump([self._host_observation(), self._host_observation()], handle)

        with self.assertRaisesRegex(ValueError, "must contain a JSON object"):
            extractor._read_host_observation(path)

    def test_rejects_observation_that_overrides_rollout_metrics(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        observation = self._host_observation()
        observation["trace"]["provider"] = "proxy"

        with self.assertRaisesRegex(ValueError, "cannot override rollout-owned fields"):
            extractor.merge_host_observation(extracted, observation)

    def test_rejects_mismatched_session_and_turn_ids(self) -> None:
        extracted = extractor.extract_turn(self._write_rollout(), "turn-1")
        for field, value in (
            ("session_id", "other-session"),
            ("turn_id", "other-turn"),
        ):
            with self.subTest(field=field):
                observation = self._host_observation()
                observation[field] = value
                with self.assertRaisesRegex(ValueError, f"{field} does not match"):
                    extractor.merge_host_observation(extracted, observation)

    def test_rejects_companion_tmcp_counter_mismatch(self) -> None:
        extracted = extractor.extract_turn(
            self._write_rollout(tool_name="tmcp_status"), "turn-1"
        )
        observation = self._host_observation(tmcp_round_trips=0)

        with self.assertRaisesRegex(ValueError, "rollout-derived value"):
            extractor.merge_host_observation(extracted, observation)

    @staticmethod
    def _host_observation(
        *,
        skill_read_calls: int = 1,
        skill_read_input_tokens: int = 25,
        tmcp_round_trips: int | None = 0,
        routing_mode: str = "substitution",
        packet_injected: bool = True,
        normal_full_skill_load_count: int = 0,
    ) -> dict:
        host_metrics = {
            "skill_read_calls": skill_read_calls,
            "skill_read_input_tokens": skill_read_input_tokens,
        }
        if tmcp_round_trips is not None:
            host_metrics["tmcp_model_visible_round_trips"] = tmcp_round_trips
        return {
            "schema": "codex-tmcp-host-observation-v0.1",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "host_metrics": host_metrics,
            "trace": {
                "run_id": "run-1",
                "task_id": "task-1",
                "fresh_context": True,
                "stratum": "positive",
                "human_expected_action": "compose",
                "human_label_blinded": True,
                "review_or_audit_task": False,
                "admission": {
                    "mode": "automatic",
                    "action": "compose",
                    "recommended_action": "compose",
                    "policy_version": "v0.7",
                },
                "routing": {
                    "mode": routing_mode,
                    "packet_injected": packet_injected,
                    "selected_source_count": 1,
                    "review_source_count": 0,
                    "normal_full_skill_load_count": normal_full_skill_load_count,
                    "supplemental_full_skill_load_count": 0,
                },
            },
        }
