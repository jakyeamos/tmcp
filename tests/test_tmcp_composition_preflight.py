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

    def test_preflight_does_not_bootstrap_shared_active_candidates(
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
        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertEqual(preflight["candidate_source_slices"], [])
        self.assertEqual(costs["hydrated_candidate_tokens"], 0)
        self.assertLess(
            costs["hydrated_candidate_tokens"], costs["naive_candidate_tokens"]
        )
        self.assertFalse(costs["context_target_achievable"])
        self.assertFalse(costs["context_target_met"])
        self.assertEqual(costs["mandatory_context_overrides"], [])
        self.assertEqual(costs["minimum_active_context_override"], "")
        self.assertTrue(evidence["no_high_confidence_active_skill"])

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

    def test_preflight_defers_shared_active_skills_without_positive_signal(
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
            _node(
                "schema-three",
                "skill_definition",
                "skills/schema-three/SKILL.md",
                "Schema compatibility ledger.",
                token_estimate=None,
            ),
            _node(
                "schema-four",
                "skill_definition",
                "skills/schema-four/SKILL.md",
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
        self.assertEqual(evidence["selected_active_source_ids"], [])
        self.assertEqual(evidence["discriminative_active_objective_terms"], [])
        self.assertEqual(
            evidence["deferred_shared_only_active_source_ids"],
            ["schema-four", "schema-one", "schema-three", "schema-two"],
        )
        self.assertTrue(evidence["no_high_confidence_active_skill"])

    def test_preflight_does_not_treat_add_as_active_skill_evidence(self) -> None:
        nodes = [
            _node(
                "behavior-inventory",
                "skill_definition",
                "skills/behavior-inventory/SKILL.md",
                "Add a complete behavior inventory and regression coverage.",
                token_estimate=None,
            ),
            _node(
                "regression-check",
                "skill_definition",
                "skills/regression-check/SKILL.md",
                "Maintain regression coverage.",
                token_estimate=None,
            ),
            _node(
                "coverage-check",
                "skill_definition",
                "skills/coverage-check/SKILL.md",
                "Maintain regression coverage.",
                token_estimate=None,
            ),
            _node(
                "verification-check",
                "skill_definition",
                "skills/verification-check/SKILL.md",
                "Maintain regression coverage.",
                token_estimate=None,
            ),
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Add cache rehydration regression coverage.",
            max_total_tokens=1_000,
        )

        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertNotIn("add", evidence["discriminative_active_objective_terms"])
        self.assertEqual(evidence["selected_active_source_ids"], [])
        self.assertEqual(
            evidence["deferred_shared_only_active_source_ids"],
            [
                "behavior-inventory",
                "coverage-check",
                "regression-check",
                "verification-check",
            ],
        )
        self.assertTrue(evidence["no_high_confidence_active_skill"])

    def test_preflight_keeps_a_small_explicitly_compositional_set(self) -> None:
        nodes = [
            _node(
                "research",
                "skill_definition",
                "skills/research/SKILL.md",
                "Research source evidence.",
                token_estimate=None,
            ),
            _node(
                "implement",
                "skill_definition",
                "skills/implement/SKILL.md",
                "Implement from the evidence.",
                token_estimate=None,
            ),
            _node(
                "verify",
                "skill_definition",
                "skills/verify/SKILL.md",
                "Verify the implementation.",
                token_estimate=None,
            ),
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Research, implement, and verify a product change.",
            max_total_tokens=1_000,
        )

        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertEqual(
            evidence["selected_active_source_ids"],
            ["implement", "research", "verify"],
        )
        self.assertTrue(evidence["low_cardinality_active_fallback"])
        self.assertFalse(evidence["no_high_confidence_active_skill"])

    def test_preflight_prefers_an_explicit_multiword_skill_phrase(self) -> None:
        nodes = [
            _node(
                "skill-harvest",
                "skill_definition",
                "skills/tmcp-skill-harvest/SKILL.md",
                "---\nname: tmcp-skill-harvest\n---\nHarvest reusable instructions from repository files.",
                token_estimate=None,
            ),
            _node(
                "test-strategy",
                "skill_definition",
                "skills/tmcp-test-strategy/SKILL.md",
                "---\nname: tmcp-test-strategy\n---\nProduce a test strategy and regression-risk review.",
                token_estimate=None,
            ),
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Develop a test strategy for this repository.",
            max_total_tokens=1_000,
        )

        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertEqual(evidence["selected_active_source_ids"], ["test-strategy"])
        self.assertEqual(
            evidence["declared_skill_phrase_active_source_ids"], ["test-strategy"]
        )
        self.assertEqual(
            evidence["deferred_shared_only_active_source_ids"], ["skill-harvest"]
        )
        self.assertFalse(evidence["no_high_confidence_active_skill"])

    def test_preflight_honors_a_skill_negative_activation_clause(self) -> None:
        nodes = [
            _node(
                "behavior-loop",
                "skill_definition",
                "skills/tmcp-repo-behavior-spec-loop/SKILL.md",
                "Inventory behavior and add regression coverage. Do not use it for a narrow bug fix unless the user asks for a full behavior inventory.",
                token_estimate=None,
            )
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Perform a narrow bug fix with regression coverage.",
            max_total_tokens=1_000,
        )

        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertEqual(evidence["selected_active_source_ids"], [])
        self.assertEqual(
            evidence["negative_constraint_active_source_ids"], ["behavior-loop"]
        )
        self.assertTrue(evidence["no_high_confidence_active_skill"])

    def test_preflight_defers_an_unrelated_seed_dependency_bundle(self) -> None:
        nodes = [
            _node(
                "migration-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#migration-seed",
                "Migration coordinator prepares migration evidence.",
                chains_after=["checksum-verifier"],
                token_estimate=None,
            ),
            _node(
                "checksum-verifier",
                "skill_definition",
                "skills/checksum-verifier/SKILL.md",
                "Calculate checksum evidence for a migration artifact.",
                token_estimate=None,
            ),
            _node(
                "release-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#release-seed",
                "Release coordinator prepares release evidence.",
                chains_after=["release-verifier"],
                token_estimate=None,
            ),
            _node(
                "release-verifier",
                "skill_definition",
                "skills/release-verifier/SKILL.md",
                "Verify release package evidence.",
                token_estimate=None,
            ),
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Prepare migration evidence.",
            max_slices=2,
            max_total_chars=2_000,
            max_total_tokens=1_000,
        )

        selected = {
            str(item["source_node_id"])
            for item in preflight["candidate_source_slices"]
        }
        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertSetEqual(selected, {"migration-seed", "checksum-verifier"})
        self.assertEqual(
            evidence["deferred_nonroot_scoped_seed_ids"], ["release-seed"]
        )
        self.assertNotIn("release-verifier", selected)

    def test_preflight_never_promotes_an_unmatched_seed_as_a_fallback(self) -> None:
        nodes = [
            _node(
                "governing",
                "agent_operating_contract",
                "AGENTS.md",
                "Preserve governing constraints.",
            ),
            _node(
                "release-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#release-seed",
                "Release coordinator prepares package evidence.",
                chains_after=["release-verifier"],
            ),
            _node(
                "release-verifier",
                "skill_definition",
                "skills/release-verifier/SKILL.md",
                "Verify release package evidence.",
            ),
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Fix a visual layout alignment bug and verify color contrast.",
            max_slices=3,
            max_total_chars=3_000,
            max_total_tokens=1_000,
        )

        selected = {
            str(item["source_node_id"])
            for item in preflight["candidate_source_slices"]
        }
        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertNotIn("release-seed", selected)
        self.assertEqual(evidence["declared_dependency_root_seed_ids"], [])
        self.assertEqual(
            evidence["deferred_nonroot_scoped_seed_ids"], ["release-seed"]
        )

    def test_preflight_resolves_an_explicit_fixture_dependency(self) -> None:
        fixture_path = "tests/fixtures/checksum/SKILL.md"
        nodes = [
            _node(
                "migration-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#migration-seed",
                "Migration coordinator prepares migration evidence.",
                chains_after=["fixture-checksum"],
                token_estimate=None,
            ),
            _node(
                "fixture-checksum",
                "skill_definition",
                fixture_path,
                "Verify migration checksum evidence.",
                source_role="evidence_only",
                activation_eligible=False,
                token_estimate=None,
            ),
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Prepare migration evidence.",
            explicitly_scoped_paths=[fixture_path],
            max_slices=2,
            max_total_chars=2_000,
            max_total_tokens=1_000,
        )

        closure = preflight["scoped_seed_graph_hints"][
            "declared_dependency_closure"
        ]
        self.assertEqual(
            closure["required_dependency_nodes"][0]["source_node_id"],
            "fixture-checksum",
        )
        fixture_slice = next(
            item
            for item in preflight["candidate_source_slices"]
            if item["source_node_id"] == "fixture-checksum"
        )
        self.assertEqual(fixture_slice["source_role"], "active_skill")
        self.assertTrue(fixture_slice["explicitly_scoped"])

    def test_preflight_omits_inert_seed_graph_scaffolding_from_context_budget(
        self,
    ) -> None:
        preflight = ci.prepare_composition(
            [
                _node(
                    "verification",
                    "skill_definition",
                    "skills/verification/SKILL.md",
                    "Verify focused regression evidence.",
                    token_estimate=None,
                )
            ],
            "Verify focused regression evidence.",
            max_slices=1,
            max_chars_per_slice=160,
            max_total_chars=160,
            max_total_tokens=100,
        )

        costs = preflight["diagnostics"]["context_cost"]
        self.assertEqual(
            preflight["scoped_seed_graph_hints"],
            {"scoped_seeds": [], "typed_edges": []},
        )
        self.assertLess(costs["scoped_seed_hint_tokens"], 5)
        self.assertLessEqual(costs["preflight_total_tokens"], 100)

    def test_preflight_rejects_ambiguous_relevant_seed_root_ids(self) -> None:
        nodes = [
            _node(
                "duplicate-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#one",
                "Migration coordinator prepares migration evidence.",
                token_estimate=None,
            ),
            _node(
                "duplicate-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#two",
                "Migration coordinator prepares migration evidence.",
                token_estimate=None,
            ),
        ]

        with self.assertRaisesRegex(ValueError, "unique scoped seed ids"):
            ci.prepare_composition(
                nodes,
                "Prepare migration evidence.",
                max_slices=2,
                max_total_chars=2_000,
                max_total_tokens=1_000,
            )

    def test_preflight_does_not_treat_an_objective_prefix_as_seed_phrase_match(
        self,
    ) -> None:
        preflight = ci.prepare_composition(
            [
                _node(
                    "release-seed",
                    "scoped_packet_seed",
                    "scoped-packet-seeds.json#release-seed",
                    "Release coordinator for verified production packages.",
                    use_when=["Handle request and release production."],
                    token_estimate=None,
                ),
            ],
            "Handle request.",
            max_slices=1,
            max_total_chars=2_000,
            max_total_tokens=1_000,
        )

        evidence = preflight["diagnostics"]["semantic_evidence"]
        self.assertEqual(evidence["declared_phrase_scoped_seed_root_ids"], [])
        self.assertEqual(evidence["declared_dependency_root_seed_ids"], [])

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
