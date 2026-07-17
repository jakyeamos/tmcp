from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_packets as evaluation_packets


class EvaluationPacketServiceTests(unittest.TestCase):
    def test_packet_diff_projects_expected_variant_and_composed_sources(self) -> None:
        decomposition = {
            "skill_path": "/project/skills/example/SKILL.md",
            "routing_slices": {
                "required_reads": ["AGENTS.md"],
                "verification_gates": ["Run pnpm test"],
                "stop_conditions": ["Ask before editing"],
                "output_contract": ["Report results"],
            },
            "behavior_atoms": ["behavior-verification"],
        }
        expectations = evaluation_packets.packet_inclusion_expectations(decomposition)
        composed = {
            "packet_id": "packet-1",
            "evidence_citations": [
                {"path": "/project/skills/example/SKILL.md", "source": "SKILL.md"}
            ],
            "required_reads": ["AGENTS.md"],
            "verification_gates": ["Run pnpm test"],
            "stop_conditions": ["Ask before editing"],
            "output_contract": ["Report results"],
            "active_atoms": ["behavior-verification"],
            "ignored_sources": [],
            "conflicts": [],
        }

        diff = evaluation_packets.diff_packet_inclusion(
            expectations,
            composed,
            skill_path=decomposition["skill_path"],
            variant_id="original",
        )

        self.assertEqual(diff["score"], 1.0)
        self.assertTrue(diff["signals"]["skill_selected_in_packet"])
        self.assertEqual(diff["composed_packet_id"], "packet-1")

    def test_compose_callback_is_the_only_packet_dependency(self) -> None:
        row = {"task_id": "task-1", "variant_id": "original"}
        calls: list[tuple[dict[str, object], str | None]] = []

        def compose(
            received_row: dict[str, object], project_path: str | None
        ) -> dict[str, object]:
            calls.append((received_row, project_path))
            return {"packet_id": "packet-2"}

        result = evaluation_packets.compose_packet_for_eval_row(
            row,
            compose,
            project_path="/project",
        )

        self.assertEqual(result, {"packet_id": "packet-2"})
        self.assertEqual(calls, [(row, "/project")])

    def test_matrix_row_id_resolves_one_ablation(self) -> None:
        plan = {
            "task_matrix": [
                {
                    "matrix_row_id": "row-a",
                    "task_id": "task-1",
                    "variant_id": "ablated",
                    "ablation_section": "verification",
                },
                {
                    "matrix_row_id": "row-b",
                    "task_id": "task-1",
                    "variant_id": "ablated",
                    "ablation_section": "output",
                },
            ]
        }

        row = evaluation_packets.task_matrix_row(plan, matrix_row_id="row-b")

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["ablation_section"], "output")
        with self.assertRaisesRegex(ValueError, "multiple task-matrix rows"):
            evaluation_packets.task_matrix_row(plan, "task-1", "ablated")

    def test_row_specific_packet_contract_wins_over_full_skill_contract(self) -> None:
        row_contract = {
            "required_reads": [],
            "verification_gates": ["Run pnpm test"],
            "stop_conditions": [],
            "output_contract": [],
            "behavior_atoms": ["behavior-verification"],
        }
        plan = {
            "packet_inclusion_contracts": [
                {
                    "skill_path": "/project/SKILL.md",
                    "expected": {"required_reads": ["AGENTS.md"]},
                }
            ]
        }
        row = {
            "skill_path": "/project/SKILL.md",
            "variant_id": "verification-only",
            "expected_packet_contract": row_contract,
        }

        expectations = evaluation_packets.expectations_for_plan_row(plan, row)

        self.assertEqual(expectations["required_reads"], [])
        self.assertEqual(expectations["verification_gates"], ["Run pnpm test"])

    def test_packet_diff_requires_expected_output_contract(self) -> None:
        expectations = {
            "output_contract": ["Must include sources"],
        }
        composed = {
            "evidence_citations": [{"path": "/project/SKILL.md", "source": "SKILL.md"}]
        }

        diff = evaluation_packets.diff_packet_inclusion(
            expectations,
            composed,
            skill_path="/project/SKILL.md",
            variant_id="output-contract-only",
        )

        self.assertFalse(diff["signals"]["included_output_contract"])
        self.assertLess(diff["score"], 1.0)

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_packets))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "datetime",
            "os",
            "pathlib",
            "scripts",
            "shutil",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "uuid",
        )

        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
