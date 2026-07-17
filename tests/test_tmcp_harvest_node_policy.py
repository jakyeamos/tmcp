from __future__ import annotations

import unittest
from pathlib import Path

from tmcp_runtime.domain.harvest_node_policy import (
    node_source_role,
    source_role_for,
    source_role_is_activation_eligible,
    source_type_for,
)


class HarvestNodePolicyTests(unittest.TestCase):
    def test_only_dedicated_workflow_trees_become_active_workflow_prompts(
        self,
    ) -> None:
        dedicated_path = "workflows/release.md"
        self.assertEqual(
            source_type_for(Path(dedicated_path), dedicated_path, "# Release\n"),
            "workflow_prompt",
        )
        self.assertEqual(
            source_role_for(
                Path(dedicated_path), dedicated_path, "workflow_prompt"
            ),
            "active_skill",
        )

    def test_workflow_named_supporting_docs_never_activate(self) -> None:
        documentation_path = "docs/workflows/release.md"
        source_type = source_type_for(
            Path(documentation_path), documentation_path, "# Release\n"
        )
        self.assertEqual(source_type, "project_documentation")
        self.assertEqual(
            source_role_for(Path(documentation_path), documentation_path, source_type),
            "supporting_reference",
        )
        self.assertFalse(
            source_role_is_activation_eligible(
                source_role_for(
                    Path(documentation_path), documentation_path, source_type
                )
            )
        )
        notes_path = "notes/release-workflow.md"
        notes_source_type = source_type_for(
            Path(notes_path), notes_path, "# Release notes\n"
        )
        self.assertEqual(notes_source_type, "markdown_process_doc")
        self.assertEqual(
            source_role_for(Path(notes_path), notes_path, notes_source_type),
            "supporting_reference",
        )

    def test_direct_workflow_root_remains_active_when_relative_path_is_flat(self) -> None:
        source_path = Path("project/workflows/release.md")

        self.assertEqual(
            source_type_for(source_path, "release.md", "# Release\n"),
            "workflow_prompt",
        )
        self.assertEqual(
            source_role_for(source_path, "release.md", "workflow_prompt"),
            "active_skill",
        )

    def test_legacy_workflow_prompt_labels_cannot_activate_supporting_docs(
        self,
    ) -> None:
        node = {
            "relative_path": "docs/workflows/release.md",
            "source_type": "workflow_prompt",
            "source_role": "active_skill",
        }

        self.assertEqual(node_source_role(node), "supporting_reference")
        self.assertEqual(
            node_source_role(node, explicitly_scoped=True), "supporting_reference"
        )

    def test_explicitly_scoped_governing_and_skill_sources_remain_active(self) -> None:
        self.assertEqual(
            source_role_for(
                Path("AGENTS.md"),
                "AGENTS.md",
                "agent_operating_contract",
                explicitly_scoped=True,
            ),
            "governing_instruction",
        )
        self.assertEqual(
            source_role_for(
                Path("skills/review/SKILL.md"),
                "skills/review/SKILL.md",
                "skill_definition",
                explicitly_scoped=True,
            ),
            "active_skill",
        )


if __name__ == "__main__":
    unittest.main()
