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
            [
                _node(
                    "two", "skill_definition", "renamed/two/SKILL.md", "Verify output."
                )
            ],
            "Verify output.",
        )
        edited = ci.prepare_composition(
            [
                _node(
                    "one",
                    "skill_definition",
                    "skills/one/SKILL.md",
                    "Verify all output.",
                )
            ],
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
        self.assertGreater(
            preflight["diagnostics"]["unindexed_behavior_block_count"], 0
        )
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
        self.assertLess(
            costs["hydrated_candidate_tokens"], costs["naive_candidate_tokens"]
        )
        self.assertFalse(costs["context_target_achievable"])
        self.assertFalse(costs["context_target_met"])
        self.assertEqual(costs["mandatory_context_overrides"], [])
        self.assertTrue(costs["minimum_active_context_override"])

    def test_preflight_can_expose_bounded_evidence_for_every_active_source(
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
            include_all_active_source_slices=True,
        )

        self.assertEqual(len(preflight["candidate_source_slices"]), 10)
        self.assertEqual(
            preflight["diagnostics"]["semantic_evidence"]["selection_policy"],
            "all_active_source_candidates",
        )
        self.assertEqual(
            preflight["diagnostics"]["semantic_evidence"]["selected_active_source_ids"],
            [f"skill-{index}" for index in range(10)],
        )
        with self.assertRaisesRegex(ValueError, "every active source"):
            ci.prepare_composition(
                nodes,
                "Use tiny behavior.",
                max_slices=9,
                max_total_tokens=1_000,
                include_all_active_source_slices=True,
            )

    def test_preflight_prefers_skill_behavior_over_frontmatter_metadata(self) -> None:
        content = """---
name: runtime-hardening
description: Verify runtime provenance and regression behavior.
---

# Workflow

Inspect the current runtime capsule, preserve source provenance, and verify
the regression suite before producing a bounded handoff.
"""

        preflight = ci.prepare_composition(
            [
                _node(
                    "runtime-hardening",
                    "skill_definition",
                    "skills/runtime-hardening/SKILL.md",
                    content,
                )
            ],
            "Harden runtime provenance and verify the regression behavior.",
            max_slices=1,
            max_total_chars=2_000,
            max_total_tokens=1_000,
        )

        selected = preflight["candidate_source_slices"]
        self.assertEqual(len(selected), 1)
        self.assertIn("Inspect the current runtime capsule", selected[0]["content"])
        self.assertNotEqual(selected[0]["char_start"], 0)

    def test_preflight_prefers_an_executable_contract_over_trigger_copy(self) -> None:
        content = """# Runtime hardening

Use this skill when the user asks to harden runtime provenance.

## Workflow

Inspect current source provenance before changing runtime behavior.

## Output Contract

Produce a runtime provenance handoff with verified regression evidence.
"""

        preflight = ci.prepare_composition(
            [
                _node(
                    "runtime-hardening",
                    "skill_definition",
                    "skills/runtime-hardening/SKILL.md",
                    content,
                )
            ],
            "Harden runtime provenance and verify regression behavior.",
            max_slices=1,
            max_total_chars=2_000,
            max_total_tokens=1_000,
        )

        selected = preflight["candidate_source_slices"]
        self.assertEqual(len(selected), 1)
        self.assertIn("runtime provenance handoff", selected[0]["content"])


if __name__ == "__main__":
    unittest.main()
