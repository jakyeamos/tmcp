from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_invocation_admission_overhead_pilot",
    ROOT / "scripts" / "run_invocation_admission_overhead_pilot.py",
)
assert SPEC and SPEC.loader
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class InvocationAdmissionOverheadPilotTests(unittest.TestCase):
    def _manifest(self, repetitions: int = 3) -> dict:
        return {
            "schema": "tmcp-invocation-admission-overhead-pilot-v0.5",
            "tasks": [
                {
                    "id": "one",
                    "objective": "one",
                    "source_path": ".",
                    "expected_automatic_action": "bypass",
                    "negative_control": True,
                },
                {
                    "id": "two",
                    "objective": "two",
                    "source_path": ".",
                    "expected_automatic_action": "bypass",
                    "negative_control": True,
                },
            ],
            "benchmark": {
                "randomization_seed": 7,
                "warmups_per_cell": 1,
                "measured_pairs_per_task": repetitions,
                "measurement": "test monotonic timing",
                "pair_policies": [
                    {
                        "id": "always-on",
                        "admission_mode": "forced",
                        "expected_action": "forced",
                    },
                    {
                        "id": "admission-controlled",
                        "admission_mode": "automatic",
                        "expected_action": "bypass",
                    },
                ],
            },
            "acceptance": {
                "minimum_median_paired_overhead_reduction_vs_always_on": 0.15,
                "minimum_per_task_median_paired_reduction": 0.0,
            },
            "evidence_boundary": "test",
        }

    def _observations(self, automatic_ns: int = 70, repetitions: int = 3) -> list[dict]:
        rows = []
        for task_id in ("one", "two"):
            for repeat in range(1, repetitions + 1):
                rows.extend(
                    [
                        {
                            "task_id": task_id,
                            "repeat": repeat,
                            "pair_order": 1,
                            "policy_id": "always-on",
                            "wall_time_ns": 100,
                            "admission_action": "forced",
                            "packet_injected": True,
                            "packet_markdown_chars": 100,
                        },
                        {
                            "task_id": task_id,
                            "repeat": repeat,
                            "pair_order": 2,
                            "policy_id": "admission-controlled",
                            "wall_time_ns": automatic_ns,
                            "admission_action": "bypass",
                            "packet_injected": False,
                            "packet_markdown_chars": 0,
                        },
                    ]
                )
        return rows

    def test_paired_overhead_gate_passes_with_stable_reduction(self) -> None:
        report = pilot.score(self._manifest(), self._observations())

        self.assertTrue(report["promotion_authorized"])
        self.assertAlmostEqual(
            report["acceptance_gates"][
                "median_paired_overhead_reduction_vs_always_on"
            ]["observed"],
            0.3,
        )
        self.assertEqual(
            report["acceptance_gates"][
                "median_paired_overhead_reduction_vs_always_on"
            ]["measure"],
            "test monotonic timing",
        )
        self.assertTrue(
            report["acceptance_gates"]["no_per_task_overhead_regression"]["passed"]
        )

    def test_incomplete_pair_fails_closed(self) -> None:
        rows = self._observations()
        rows.pop()
        with self.assertRaisesRegex(ValueError, "incomplete benchmark"):
            pilot.score(self._manifest(), rows)

    def test_duplicate_observation_fails_closed(self) -> None:
        rows = self._observations()
        rows[-1] = dict(rows[0])
        with self.assertRaisesRegex(ValueError, "duplicate benchmark observation"):
            pilot.score(self._manifest(), rows)

    def test_per_task_regression_blocks_promotion(self) -> None:
        rows = self._observations()
        for row in rows:
            if row["task_id"] == "two" and row["policy_id"] == "admission-controlled":
                row["wall_time_ns"] = 110
        report = pilot.score(self._manifest(), rows)

        self.assertFalse(report["promotion_authorized"])
        self.assertFalse(
            report["acceptance_gates"]["no_per_task_overhead_regression"]["passed"]
        )

    def test_manifest_accepts_only_declared_transports(self) -> None:
        manifest = self._manifest()
        manifest["benchmark"]["transport"] = "unknown"

        with self.assertRaisesRegex(ValueError, "unsupported benchmark transport"):
            pilot._validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
