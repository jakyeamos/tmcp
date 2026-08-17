from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "score_invocation_admission_rollout",
    ROOT / "scripts" / "score_invocation_admission_rollout.py",
)
assert SPEC and SPEC.loader
rollout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollout)


class InvocationAdmissionRolloutScoringTests(unittest.TestCase):
    def _manifest(self) -> dict:
        manifest = json.loads(
            (ROOT / "examples" / "workflows" / "invocation-admission-rollout-v0.7.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["shadow"]["minimum_tasks_total"] = 3
        manifest["shadow"]["minimum_tasks_per_stratum"] = 1
        manifest["canary"]["minimum_pairs_total"] = 3
        manifest["canary"]["minimum_pairs_per_stratum"] = 1
        return manifest

    def _metrics(
        self,
        *,
        wall: int = 100,
        tokens: int = 100,
        tools: int = 2,
        reads: int = 2,
        tmcp_round_trips: int = 0,
    ) -> dict:
        return {
            "wall_time_ms": wall,
            "input_tokens": tokens,
            "output_tokens": 20,
            "model_round_trips": 1,
            "tool_round_trips": tools,
            "skill_read_calls": reads,
            "skill_read_input_tokens": tokens // 2,
            "tmcp_model_visible_round_trips": tmcp_round_trips,
        }

    def _routing(self, *, injected: bool, mode: str) -> dict:
        return {
            "mode": mode,
            "packet_injected": injected,
            "selected_source_count": 1 if injected else 0,
            "review_source_count": 0,
            "normal_full_skill_load_count": 0 if injected else 1,
            "supplemental_full_skill_load_count": 0,
        }

    def _admission(self, action: str, *, shadow: bool = False) -> dict:
        return {
            "mode": "shadow" if shadow else "automatic",
            "action": "shadow" if shadow else action,
            "recommended_action": action,
            "policy_version": "test",
        }

    def _shadow_traces(self) -> list[dict]:
        rows = []
        for stratum, expected in (
            ("positive", "compose"),
            ("negative", "bypass"),
            ("ambiguous", "compose"),
        ):
            rows.append(
                {
                    "run_id": f"shadow-{stratum}",
                    "task_id": stratum,
                    "trace_source": "codex-host",
                    "provider": "test-provider",
                    "model": "test-model",
                    "fresh_context": True,
                    "stratum": stratum,
                    "human_expected_action": expected,
                    "human_label_blinded": True,
                    "review_or_audit_task": False,
                    "admission": self._admission(expected, shadow=True),
                    "routing": self._routing(injected=False, mode="shadow"),
                    "provider_metrics": self._metrics(reads=0, tools=0),
                }
            )
        return rows

    def _canary(self) -> tuple[list[dict], list[dict]]:
        traces = []
        judgments = []
        for pair_index, (stratum, expected) in enumerate((
            ("positive", "compose"),
            ("negative", "bypass"),
            ("ambiguous", "compose"),
        )):
            pair_id = f"pair-{stratum}"
            ordered_arms = (
                ("normal-codex-routing", "tmcp-admitted-substitution")
                if pair_index % 2 == 0
                else ("tmcp-admitted-substitution", "normal-codex-routing")
            )
            for pair_order, arm in enumerate(ordered_arms, start=1):
                run_id = f"{pair_id}-{arm}"
                tmcp = arm == "tmcp-admitted-substitution"
                compose = tmcp and expected == "compose"
                traces.append(
                    {
                        "run_id": run_id,
                        "pair_id": pair_id,
                        "pair_order": pair_order,
                        "task_id": stratum,
                        "trace_source": "codex-host",
                        "provider": "test-provider",
                        "model": "test-model",
                        "fresh_context": True,
                        "stratum": stratum,
                        "human_expected_action": expected,
                        "human_label_blinded": True,
                        "review_or_audit_task": False,
                        "arm": arm,
                        "admission": self._admission(expected) if tmcp else None,
                        "routing": self._routing(
                            injected=compose,
                            mode=(
                                "substitution"
                                if compose
                                else ("normal_after_bypass" if tmcp else "normal")
                            ),
                        ),
                        "provider_metrics": self._metrics(
                            wall=90 if tmcp else 100,
                            tokens=90 if tmcp else 100,
                            tools=1 if tmcp else 2,
                            reads=0 if compose else (1 if tmcp else 2),
                        ),
                    }
                )
                judgments.append(
                    {
                        "run_id": run_id,
                        "judge_blinded": True,
                        "pass": True,
                        "weighted_score": 0.9,
                        "verification_quality_score": 0.9,
                        "irrelevant_constraint_count": 0,
                        "unsafe_or_unjustified_action_count": 0,
                    }
                )
        return traces, judgments

    def test_shadow_passes_with_blinded_labels_and_no_model_visible_call(self) -> None:
        report = rollout.score_shadow(self._manifest(), self._shadow_traces())

        self.assertTrue(report["promotion_authorized"])
        self.assertTrue(all(gate["passed"] for gate in report["acceptance_gates"].values()))

    def test_shadow_rejects_packet_injection(self) -> None:
        traces = self._shadow_traces()
        traces[0]["routing"]["packet_injected"] = True

        with self.assertRaisesRegex(ValueError, "shadow mode injected a packet"):
            rollout.score_shadow(self._manifest(), traces)

    def test_canary_passes_when_tmcp_substitutes_and_provider_cost_falls(self) -> None:
        traces, judgments = self._canary()
        report = rollout.score_canary(
            self._manifest(),
            traces,
            judgments,
            {
                "schema": "tmcp-invocation-admission-shadow-score-v0.7",
                "status": "complete",
                "promotion_authorized": True,
            },
        )

        self.assertTrue(report["promotion_authorized"])
        self.assertTrue(report["acceptance_gates"]["substitution_integrity"]["passed"])
        self.assertLess(
            report["acceptance_gates"]["provider_tokens"]["observed_median_ratio"],
            1,
        )

    def test_canary_rejects_supplemental_full_skill_loading(self) -> None:
        traces, judgments = self._canary()
        tmcp_positive = next(
            row
            for row in traces
            if row["stratum"] == "positive"
            and row["arm"] == "tmcp-admitted-substitution"
        )
        tmcp_positive["routing"]["supplemental_full_skill_load_count"] = 1

        with self.assertRaisesRegex(ValueError, "supplemented normal routing"):
            rollout.score_canary(
                self._manifest(),
                traces,
                judgments,
                {
                    "schema": "tmcp-invocation-admission-shadow-score-v0.7",
                    "status": "complete",
                    "promotion_authorized": True,
                },
            )

    def test_canary_fails_provider_economics_without_weak_proxy(self) -> None:
        traces, judgments = self._canary()
        for row in traces:
            if row["arm"] == "tmcp-admitted-substitution":
                row["provider_metrics"]["input_tokens"] = 150
                row["provider_metrics"]["wall_time_ms"] = 120
        report = rollout.score_canary(
            self._manifest(),
            traces,
            judgments,
            {
                "schema": "tmcp-invocation-admission-shadow-score-v0.7",
                "status": "complete",
                "promotion_authorized": True,
            },
        )

        self.assertFalse(report["promotion_authorized"])
        self.assertFalse(report["acceptance_gates"]["provider_tokens"]["passed"])
        self.assertFalse(report["acceptance_gates"]["provider_wall_time"]["passed"])

    def test_canary_requires_complete_provider_metrics(self) -> None:
        traces, judgments = self._canary()
        del traces[0]["provider_metrics"]["input_tokens"]

        with self.assertRaisesRegex(ValueError, "provider metrics are incomplete"):
            rollout.score_canary(
                self._manifest(),
                traces,
                judgments,
                {
                    "schema": "tmcp-invocation-admission-shadow-score-v0.7",
                    "status": "complete",
                    "promotion_authorized": True,
                },
            )

    def test_canary_requires_passed_shadow(self) -> None:
        traces, judgments = self._canary()

        with self.assertRaisesRegex(ValueError, "requires a complete passed v0.7"):
            rollout.score_canary(
                self._manifest(),
                traces,
                judgments,
                {"promotion_authorized": False},
            )


if __name__ == "__main__":
    unittest.main()
