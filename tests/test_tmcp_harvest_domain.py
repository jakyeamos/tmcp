from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tmcp_runtime.services.harvest as harvest_service
from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.domain.harvest_nodes import (
    routing_metadata_for,
    source_node_from_text,
    source_type_for,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HARVEST_NODES_PATH = PLUGIN_ROOT / "tmcp_runtime" / "domain" / "harvest_nodes.py"
HARVEST_ROUTING_PATH = PLUGIN_ROOT / "tmcp_runtime" / "domain" / "harvest_routing.py"
HARVEST_SERVICE_PATH = PLUGIN_ROOT / "tmcp_runtime" / "services" / "harvest.py"


class HarvestDomainTests(unittest.TestCase):
    def test_contrast_gate_requires_accessibility_context(self) -> None:
        statistical = routing_metadata_for(
            "docs/evaluation.md",
            "Score the causal contrast in a controlled experimental design.",
        )
        visual = routing_metadata_for(
            "docs/ui.md",
            "Verify color contrast on the rendered interface.",
        )

        self.assertNotIn("Verify contrast.", statistical["verification_gates"])
        self.assertIn("Verify contrast.", visual["verification_gates"])

    def test_irreversible_confirmation_gate_survives_markdown_formatting(self) -> None:
        routing = routing_metadata_for(
            "SKILL.md",
            "Use `confirm` before any irreversible action.",
        )

        self.assertIn(
            "Wait for explicit user confirmation before irreversible or external actions.",
            routing["stop_conditions"],
        )

    def test_branch_safety_rules_survive_markdown_formatting(self) -> None:
        routing = routing_metadata_for(
            "SKILL.md",
            "\n".join(
                [
                    ("Verify the live remote head again before promotion and pruning."),
                    (
                        "Preserve every dirty worktree and every branch with unique "
                        "or ambiguous work."
                    ),
                    "Never force-push or use `git branch -D` on uncertain evidence.",
                    (
                        "Use ancestry and `git cherry` patch equivalence before "
                        "claiming that work is redundant."
                    ),
                ]
            ),
        )

        self.assertIn(
            "Preserve dirty worktrees and branches with unique or ambiguous work; "
            "do not prune on uncertain evidence.",
            routing["stop_conditions"],
        )
        self.assertIn(
            "Do not force-push, force-delete branches, or bypass hooks while "
            "branch evidence is uncertain.",
            routing["stop_conditions"],
        )
        self.assertIn(
            "Verify the live remote target head before any promotion or pruning.",
            routing["verification_gates"],
        )
        self.assertIn(
            "Verify ancestry and git cherry patch equivalence before declaring a "
            "branch superseded.",
            routing["verification_gates"],
        )

    def test_output_contract_ignores_incidental_return_language(self) -> None:
        routing = routing_metadata_for(
            "SKILL.md",
            "\n".join(
                [
                    "The API response returns a status code.",
                    "Return a compact repair handoff.",
                    "Keep the same return format for callers.",
                ]
            ),
        )

        self.assertEqual(
            routing["output_contract"], ["Return a compact repair handoff."]
        )

    def test_output_contract_ignores_headings_and_fenced_code(self) -> None:
        routing = routing_metadata_for(
            "docs/runtime.md",
            "\n".join(
                [
                    "## Output Contract",
                    "```python",
                    "return base + route_boost",
                    "```",
                    "Produce or cite the verification evidence.",
                ]
            ),
        )

        self.assertEqual(
            routing["output_contract"],
            ["Produce or cite the verification evidence."],
        )

    def test_output_contract_keeps_concrete_bullets_under_its_heading(self) -> None:
        routing = routing_metadata_for(
            "SKILL.md",
            "\n".join(
                [
                    "## Output Contract",
                    "Produce or cite:",
                    "",
                    "- Sources inspected.",
                    "- Verification evidence.",
                    "",
                    "## Safety",
                    "Do not write secrets.",
                ]
            ),
        )

        self.assertEqual(
            routing["output_contract"],
            ["Sources inspected.", "Verification evidence."],
        )

    def test_stop_condition_field_name_is_not_a_stop_instruction(self) -> None:
        routing = routing_metadata_for(
            "SKILL.md",
            "The packet returns stop_conditions and output_contract fields.",
        )

        self.assertEqual(routing["stop_conditions"], [])

    def test_documentation_with_workflow_words_is_not_a_workflow_prompt(self) -> None:
        self.assertEqual(
            source_type_for(
                Path("docs/guidebook.md"),
                "docs/guidebook.md",
                "This guidebook explains the workflow evidence boundary.",
            ),
            "project_documentation",
        )
        self.assertEqual(
            source_type_for(
                Path("workflow.md"),
                "workflow.md",
                "A concise project process.",
            ),
            "workflow_prompt",
        )
        self.assertEqual(
            source_type_for(
                Path("examples/workflows/review.md"),
                "examples/workflows/review.md",
                "A reusable example workflow.",
            ),
            "project_documentation",
        )

    def test_source_node_uses_an_explicit_advisory_callback(self) -> None:
        source_path = "/tmp/example/SKILL.md"
        source_text = "# Skill\nUse browser evidence before release."
        calls: list[tuple[Path, str, str, str]] = []

        def source_advisories(
            path: Path,
            text: str,
            relative_path: str,
            source_type: str,
        ) -> list[dict[str, object]]:
            calls.append((path, text, relative_path, source_type))
            return [{"pattern_id": "test", "warning": "advisory"}]

        node = source_node_from_text(
            root_path="/tmp/example",
            source_path=source_path,
            relative_path="SKILL.md",
            text=source_text,
            max_excerpt_chars=1200,
            redactions={},
            source_type="skill_definition",
            source_advisories=source_advisories,
        )

        self.assertEqual(
            calls,
            [(Path(source_path), source_text, "SKILL.md", "skill_definition")],
        )
        self.assertEqual(
            node["skill_eval_advisories"],
            [{"pattern_id": "test", "warning": "advisory"}],
        )

    def test_server_adapts_keyword_only_evaluator_advisories(self) -> None:
        server = helpers.load_server_module()
        source_text = "# Skill\nKeep the review evidence grounded."
        advisory = {"pattern_id": "test", "warning": "advisory"}

        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "SKILL.md"
            source_path.write_text(source_text, encoding="utf-8")
            with patch.object(
                server,
                "harvest_warnings_for_source",
                return_value=[advisory],
            ) as warnings_for_source:
                result = server._harvest_skills(
                    {
                        "source_path": directory,
                        "include_globs": ["**/SKILL.md"],
                        "write_artifacts": False,
                    }
                )

        warnings_for_source.assert_called_once_with(
            source_path,
            source_text,
            rel_path="SKILL.md",
            source_type="skill_definition",
        )
        self.assertEqual(
            result["source_nodes"][0]["skill_eval_advisories"],
            [advisory],
        )

    def test_harvest_node_policy_has_no_adapter_import(self) -> None:
        module = ast.parse(HARVEST_NODES_PATH.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(module)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        self.assertFalse(
            any(module_name.startswith("scripts") for module_name in imported_modules)
        )

    def test_harvest_routing_policy_has_no_adapter_or_storage_import(self) -> None:
        module = ast.parse(HARVEST_ROUTING_PATH.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(module)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        self.assertFalse(
            any(
                module_name.startswith(
                    ("scripts", "tmcp_runtime.adapters", "tmcp_runtime.storage")
                )
                for module_name in imported_modules
            )
        )

    def test_harvest_service_is_read_only_and_has_no_storage_import(self) -> None:
        module = ast.parse(HARVEST_SERVICE_PATH.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(module)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertFalse(
            any(
                module_name.startswith(("scripts", "tmcp_runtime.storage"))
                for module_name in imported_modules
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text(
                "# Skill\n\nUse verification.\n",
                encoding="utf-8",
            )
            result = harvest_service.harvest_skills(
                {"source_path": str(root), "write_artifacts": True}
            )

            self.assertNotIn("artifact_paths", result)
            self.assertFalse((root / ".tmcp").exists())


if __name__ == "__main__":
    unittest.main()
