from __future__ import annotations

import unittest

from tmcp_runtime.domain.composition_lift_host_packet import (
    project_external_skill_ids,
    project_external_stage_skill_ids,
    source_node_ids_by_skill_id,
)


class CompositionLiftHostPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "skill_roles": [
                {
                    "node_id": "node-discovery",
                    "activation": "active",
                    "source_role": "active_skill",
                },
                {
                    "node_id": "node-implementation",
                    "activation": "deferred",
                    "source_role": "active_skill",
                },
                {
                    "node_id": "node-governing",
                    "activation": "deferred",
                    "source_role": "governing_instruction",
                },
            ],
            "runtime_capsule": {
                "cited_source_slices": [
                    {
                        "original_node_id": "node-discovery",
                        "relative_path": "skills/discovery/SKILL.md",
                    },
                    {
                        "original_node_id": "node-implementation",
                        "relative_path": "skills/implementation/SKILL.md",
                    },
                    {
                        "original_node_id": "node-governing",
                        "relative_path": "AGENTS.md",
                    },
                ]
            },
        }
        self.source_paths = {
            "discovery": "skills/discovery/SKILL.md",
            "implementation": "skills/implementation/SKILL.md",
            "governing": "AGENTS.md",
        }

    def test_resolves_skill_ids_through_content_bound_paths(self) -> None:
        self.assertEqual(
            source_node_ids_by_skill_id(
                self.plan,
                ["discovery", "implementation", "governing"],
                self.source_paths,
            ),
            {
                "discovery": "node-discovery",
                "implementation": "node-implementation",
                "governing": "node-governing",
            },
        )

    def test_semantic_arms_hydrate_active_and_governing_only(self) -> None:
        self.assertEqual(
            project_external_skill_ids(
                self.plan,
                ["discovery", "implementation", "governing"],
                self.source_paths,
                variant_id="full_composition",
            ),
            (["discovery", "governing"], ["implementation"]),
        )

    def test_naive_union_retains_all_bodies_as_control(self) -> None:
        self.assertEqual(
            project_external_skill_ids(
                self.plan,
                ["implementation", "discovery"],
                self.source_paths,
                variant_id="naive_union",
            ),
            (["discovery", "implementation"], []),
        )

    def test_phase_projection_hydrates_only_the_current_stage(self) -> None:
        self.assertEqual(
            project_external_stage_skill_ids(
                self.plan,
                ["discovery", "implementation", "governing"],
                self.source_paths,
                ["node-implementation"],
            ),
            ["implementation"],
        )

    def test_unresolved_skill_is_deferred_instead_of_hydrated(self) -> None:
        self.assertEqual(
            project_external_skill_ids(
                self.plan,
                ["unknown"],
                self.source_paths,
                variant_id="singleton:unknown",
            ),
            ([], ["unknown"]),
        )


if __name__ == "__main__":
    unittest.main()
