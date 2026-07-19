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

    def test_preflight_ranks_objective_relevance_before_generic_contracts(self) -> None:
        preflight = ci.prepare_composition(
            [
                _node(
                    "generic-contract",
                    "skill_definition",
                    "skills/generic/SKILL.md",
                    "# Output Contract\n\nProduce a generic receipt and handoff.",
                ),
                _node(
                    "host-composition",
                    "skill_definition",
                    "skills/host-composition/SKILL.md",
                    "# Host-assisted composition\n\nFreeze the source snapshot and validate the cited skill graph.",
                ),
            ],
            "Harden TMCP host-assisted composition with a cited skill graph.",
            max_slices=3,
            max_total_chars=2_000,
            max_total_tokens=1_000,
        )

        selected = preflight["candidate_source_slices"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["source_node_id"], "host-composition")
        self.assertIn("Freeze the source snapshot", selected[0]["content"])
        self.assertEqual(
            preflight["diagnostics"]["semantic_evidence"][
                "objective_relevant_source_ids"
            ],
            ["host-composition"],
        )
        self.assertEqual(
            preflight["diagnostics"]["semantic_evidence"][
                "deferred_irrelevant_source_count"
            ],
            1,
        )

    def test_preflight_defers_shared_only_active_skills_without_demoting_scope(
        self,
    ) -> None:
        objective = (
            "Implement a native host-assisted composition adapter with frozen origin "
            "provenance, runtime recompilation, and harvest evidence."
        )
        explicit_path = "tests/fixtures/explicit-runtime/SKILL.md"
        shared_nodes = [
            _node(
                f"harvest-{index}",
                "skill_definition",
                f"skills/harvest-{index}/SKILL.md",
                "Harvest runtime evidence after composition.",
                token_estimate=None,
            )
            for index in range(8)
        ] + [
            _node(
                "shared-path",
                "skill_definition",
                "skills/adapter-alias/SKILL.md",
                "Harvest runtime evidence after composition.",
                token_estimate=None,
            )
        ]
        preflight = ci.prepare_composition(
            [
                _node(
                    "governing",
                    "agent_operating_contract",
                    "AGENTS.md",
                    "Preserve governing constraints.",
                    token_estimate=None,
                ),
                _node(
                    "host-core",
                    "skill_definition",
                    "skills/host-core/SKILL.md",
                    "Native host-assisted composition adapter preserves frozen origin provenance during recompilation.",
                    token_estimate=None,
                ),
                _node(
                    "runtime-seed",
                    "scoped_packet_seed",
                    "scoped-packet-seeds.json#runtime-seed",
                    "Runtime coordinator hands off evidence at verification.",
                    token_estimate=None,
                ),
                _node(
                    "explicit-runtime",
                    "skill_definition",
                    explicit_path,
                    "Harvest runtime proof.",
                    token_estimate=None,
                ),
                _node(
                    "node-flag-runtime",
                    "skill_definition",
                    "tests/fixtures/node-flag-runtime/SKILL.md",
                    "Harvest runtime proof.",
                    token_estimate=None,
                    explicitly_scoped=True,
                ),
                _node(
                    "reference",
                    "project_documentation",
                    "docs/host-reference.md",
                    "Supporting host composition reference evidence.",
                    token_estimate=None,
                ),
                *shared_nodes,
            ],
            objective,
            explicitly_scoped_paths=[explicit_path],
            max_slices=20,
            max_total_chars=12_000,
            max_total_tokens=5_000,
        )

        selected_source_ids = {
            item["source_node_id"] for item in preflight["candidate_source_slices"]
        }
        self.assertTrue(
            {
                "governing",
                "host-core",
                "runtime-seed",
                "explicit-runtime",
                "node-flag-runtime",
                "reference",
            }.issubset(selected_source_ids)
        )
        shared_source_ids = {item["id"] for item in shared_nodes}
        self.assertTrue(shared_source_ids.isdisjoint(selected_source_ids))
        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertIn(
            "native", evidence["discriminative_active_objective_terms"]
        )
        self.assertNotIn(
            "runtime", evidence["discriminative_active_objective_terms"]
        )
        self.assertEqual(
            evidence["deferred_shared_only_active_source_ids"],
            sorted(shared_source_ids),
        )

    def test_preflight_all_active_mode_keeps_shared_only_active_skills(self) -> None:
        objective = (
            "Implement a native host-assisted composition adapter with frozen origin "
            "provenance, runtime recompilation, and harvest evidence."
        )
        nodes = [
            _node(
                "host-core",
                "skill_definition",
                "skills/host-core/SKILL.md",
                "Native host-assisted composition adapter preserves frozen origin provenance during recompilation.",
                token_estimate=None,
            ),
            *[
                _node(
                    f"harvest-{index}",
                    "skill_definition",
                    f"skills/harvest-{index}/SKILL.md",
                    "Harvest runtime evidence after composition.",
                    token_estimate=None,
                )
                for index in range(9)
            ],
        ]
        preflight = ci.prepare_composition(
            nodes,
            objective,
            max_slices=12,
            max_total_chars=12_000,
            max_total_tokens=5_000,
            include_all_active_source_slices=True,
        )

        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertEqual(
            evidence["selected_active_source_ids"],
            sorted(item["id"] for item in nodes),
        )
        self.assertIn(
            "native", evidence["discriminative_active_objective_terms"]
        )
        self.assertEqual(evidence["deferred_shared_only_active_source_ids"], [])

    def test_preflight_keeps_shared_active_skills_when_no_term_is_discriminative(
        self,
    ) -> None:
        nodes = [
            _node(
                "schema-one",
                "skill_definition",
                "skills/schema-one/SKILL.md",
                "Schema compatibility ledger.",
                token_estimate=None,
            ),
            _node(
                "schema-two",
                "skill_definition",
                "skills/schema-two/SKILL.md",
                "Schema compatibility ledger.",
                token_estimate=None,
            ),
        ]
        preflight = ci.prepare_composition(
            nodes,
            "Implement schema compatibility.",
            max_total_tokens=1_000,
        )

        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertEqual(
            evidence["selected_active_source_ids"], ["schema-one", "schema-two"]
        )
        self.assertEqual(evidence["discriminative_active_objective_terms"], [])
        self.assertEqual(evidence["deferred_shared_only_active_source_ids"], [])

    def test_preflight_handles_empty_active_sources_without_breaking_all_active_mode(
        self,
    ) -> None:
        nodes = [
            _node(
                "normal",
                "skill_definition",
                "skills/normal/SKILL.md",
                "Host composition evidence.",
                token_estimate=None,
            ),
            _node(
                "empty",
                "skill_definition",
                "skills/empty/SKILL.md",
                "",
                token_estimate=None,
            ),
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Host composition evidence.",
            max_total_tokens=1_000,
        )

        self.assertEqual(
            [item["source_node_id"] for item in preflight["candidate_source_slices"]],
            ["normal"],
        )
        self.assertEqual(preflight["diagnostics"]["uncitable_source_ids"], ["empty"])
        with self.assertRaisesRegex(ValueError, "citable nonempty slice"):
            ci.prepare_composition(
                nodes,
                "Host composition evidence.",
                max_total_tokens=1_000,
                include_all_active_source_slices=True,
            )


if __name__ == "__main__":
    unittest.main()
