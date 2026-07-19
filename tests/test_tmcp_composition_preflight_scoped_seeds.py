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


class CompositionPreflightScopedSeedTests(unittest.TestCase):
    def test_preflight_preserves_selected_seed_dependency_without_lexical_overlap(
        self,
    ) -> None:
        nodes = [
            _node(
                "migration",
                "skill_definition",
                "skills/migration/SKILL.md",
                "Migrate the schema and prepare a rollback plan.",
                token_estimate=None,
            ),
            _node(
                "migration-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#migration-seed",
                "Migration coordinator prepares migration checksum evidence.",
                chains_after=["checksum-verifier"],
                token_estimate=None,
            ),
            _node(
                "checksum-verifier",
                "skill_definition",
                "skills/checksum-verifier/SKILL.md",
                "Calculate a SHA-256 digest for the generated artifact.",
                token_estimate=None,
            ),
            *[
                _node(
                    f"generic-{index}",
                    "skill_definition",
                    f"skills/generic-{index}/SKILL.md",
                    "Apply shared process guidance.",
                    token_estimate=None,
                )
                for index in range(4)
            ],
        ]

        preflight = ci.prepare_composition(
            nodes,
            "Migrate the schema with checksum rollback evidence.",
            max_slices=3,
            max_total_chars=3_000,
            max_total_tokens=1_000,
        )

        selected = {
            str(item["source_node_id"])
            for item in preflight["candidate_source_slices"]
        }
        evidence = preflight["diagnostics"]["semantic_evidence"]
        closure = preflight["scoped_seed_graph_hints"][
            "declared_dependency_closure"
        ]
        self.assertTrue({"migration-seed", "checksum-verifier"}.issubset(selected))
        self.assertIn(
            "checksum-verifier",
            evidence["required_declared_dependency_source_ids"],
        )
        self.assertNotIn(
            "checksum-verifier",
            evidence["deferred_shared_only_active_source_ids"],
        )
        self.assertEqual(
            closure["required_dependency_nodes"][0]["source_node_id"],
            "checksum-verifier",
        )
        self.assertTrue(
            preflight["scoped_seed_graph_hints"]["scoped_seeds"][0]["citations"]
        )
        costs = preflight["diagnostics"]["context_cost"]
        self.assertGreater(costs["scoped_seed_hint_tokens"], 0)
        self.assertEqual(
            costs["reserved_metadata_tokens"],
            costs["scoped_seed_hint_tokens"],
        )
        self.assertEqual(
            costs["preflight_total_tokens"],
            costs["always_on_index_tokens"]
            + costs["hydrated_candidate_tokens"]
            + costs["scoped_seed_hint_tokens"],
        )
        self.assertLessEqual(costs["preflight_total_tokens"], 1_000)

    def test_preflight_rejects_selected_seed_with_truncated_metadata(self) -> None:
        nodes = [
            _node(
                "migration-seed",
                "scoped_packet_seed",
                "scoped-packet-seeds.json#migration-seed",
                "Migration coordinator prepares migration evidence.",
                use_when=["Prepare migration evidence."],
                chains_after=[f"verifier-{index}" for index in range(13)],
                token_estimate=None,
            ),
        ]

        with self.assertRaisesRegex(ValueError, "truncated scoped seed metadata"):
            ci.prepare_composition(
                nodes,
                "Prepare migration evidence.",
                max_slices=1,
                max_total_chars=2_000,
                max_total_tokens=1_000,
            )

    def test_preflight_rejects_limits_that_drop_declared_dependency_closure(
        self,
    ) -> None:
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
                "Calculate a SHA-256 digest for the generated artifact.",
                token_estimate=None,
            ),
        ]

        with self.assertRaisesRegex(ValueError, "declared dependency closure"):
            ci.prepare_composition(
                nodes,
                "Prepare migration evidence.",
                max_slices=1,
                max_total_chars=2_000,
                max_total_tokens=1_000,
            )


if __name__ == "__main__":
    unittest.main()
