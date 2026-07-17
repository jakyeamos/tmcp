from __future__ import annotations

import unittest
from typing import Any

from tmcp_runtime.domain import compositional_intelligence as ci


def _node(
    node_id: str,
    source_type: str,
    relative_path: str,
    content: str,
    **extra: object,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "source_type": source_type,
        "relative_path": relative_path,
        "title": node_id.replace("-", " ").title(),
        "excerpt": content,
        "token_estimate": max(256, len(content) // 4),
        "behavior_atoms": [],
        "routing_metadata": {},
        **extra,
    }


class CompositionPreflightBudgetTests(unittest.TestCase):
    def test_manifest_index_identity_ignores_paths_but_tracks_content(self) -> None:
        initial = ci.prepare_composition(
            [_node("one", "skill_definition", "skills/one/SKILL.md", "Verify output.")],
            "Verify output.",
        )
        renamed = ci.prepare_composition(
            [_node("two", "skill_definition", "renamed/two/SKILL.md", "Verify output.")],
            "Verify output.",
        )
        edited = ci.prepare_composition(
            [_node("one", "skill_definition", "skills/one/SKILL.md", "Verify all output.")],
            "Verify output.",
        )

        self.assertEqual(
            initial["behavior_manifest_index"]["index_digest"],
            renamed["behavior_manifest_index"]["index_digest"],
        )
        self.assertNotEqual(
            initial["behavior_manifest_index"]["index_digest"],
            edited["behavior_manifest_index"]["index_digest"],
        )

    def test_preflight_bounds_source_blocks_before_manifest_indexing(self) -> None:
        content = "\n".join(
            f"# Block {index}\nVerify deterministic block {index} evidence."
            for index in range(30)
        )
        preflight = ci.prepare_composition(
            [
                _node(
                    "long-skill",
                    "skill_definition",
                    "skills/long/SKILL.md",
                    content,
                    token_estimate=10_000,
                )
            ],
            "Verify deterministic evidence.",
            max_slices=24,
            max_chars_per_slice=64,
            max_total_chars=2_000,
            max_total_tokens=3_000,
        )

        self.assertEqual(len(preflight["candidate_source_slices"]), 24)
        self.assertEqual(
            preflight["behavior_manifest_index"]["manifest_summaries"][0][
                "behavior_block_count"
            ],
            24,
        )
        self.assertGreater(preflight["diagnostics"]["unindexed_behavior_block_count"], 0)
        self.assertTrue(preflight["diagnostics"]["source_block_truncations"])

    def test_preflight_uses_one_active_bootstrap_when_target_is_unachievable(
        self,
    ) -> None:
        nodes = [
            _node(
                f"skill-{index}",
                "skill_definition",
                f"skills/{index}/SKILL.md",
                f"Tiny behavior {index}.",
                token_estimate=4,
            )
            for index in range(10)
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Use tiny behavior.",
            max_total_tokens=1_000,
        )

        costs = preflight["diagnostics"]["context_cost"]
        self.assertEqual(len(preflight["candidate_source_slices"]), 1)
        self.assertLess(costs["hydrated_candidate_tokens"], costs["naive_candidate_tokens"])
        self.assertFalse(costs["context_target_achievable"])
        self.assertFalse(costs["context_target_met"])
        self.assertEqual(costs["mandatory_context_overrides"], [])
        self.assertTrue(costs["minimum_active_context_override"])


if __name__ == "__main__":
    unittest.main()
