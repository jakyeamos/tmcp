from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.compose as compose_service
from tmcp_runtime.services.compose import (
    active_instructions_for_source_node,
    compose_packet_from_source_nodes,
    enrich_packet_from_source_nodes,
)


class TmcpComposeServiceTests(unittest.TestCase):
    @staticmethod
    def _source_node(
        relative_path: str,
        signal_excerpt: str,
        *,
        behavior_atoms: list[str] | None = None,
        source_type: str = "agent_operating_contract",
    ) -> dict[str, object]:
        return {
            "relative_path": relative_path,
            "path": f"[REDACTED:path]/{relative_path}",
            "source_type": source_type,
            "title": relative_path,
            "signal_excerpt": signal_excerpt,
            "behavior_atoms": behavior_atoms or [],
            "routing_metadata": {},
            "trust": "untrusted_harvested_text",
        }

    @staticmethod
    def _global_graph() -> dict[str, object]:
        return {
            "workflow_nodes": [
                {
                    "id": "repo_behavior_spec_loop_workflow",
                    "active_instructions": ["MALICIOUS_INSTRUCTION"],
                }
            ],
            "_global_cache_path": "[REDACTED:path]/promotion-graph.json",
            "promotion_name": "repo-behavior",
            "trust": "advisory_untrusted",
        }

    def test_compose_from_injected_nodes_preserves_inputs_and_guidance(self) -> None:
        arguments = {
            "objective": "Implement the project behavior",
            "project_path": "[REDACTED:path]",
            "phase": "start",
            "cache_policy": "none",
        }
        source_nodes = [
            self._source_node(
                "AGENTS.md",
                "Use pnpm. Read before modifying. Search existing behavior first.",
                behavior_atoms=["behavior-preservation"],
            )
        ]
        original_arguments = copy.deepcopy(arguments)
        original_nodes = copy.deepcopy(source_nodes)

        packet = compose_packet_from_source_nodes(
            arguments,
            source_nodes=source_nodes,
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )

        self.assertEqual(arguments, original_arguments)
        self.assertEqual(source_nodes, original_nodes)
        self.assertEqual(packet["schema"], "tmcp-composed-packet-v0.1")
        self.assertEqual(packet["phase"], "start")
        self.assertIn(
            "AGENTS.md", [item["source"] for item in packet["evidence_citations"]]
        )
        self.assertIn(
            "Use pnpm for JavaScript dependency management, installs, and scripts.",
            packet["active_instructions"],
        )
        self.assertIn(
            "Read relevant project files before modifying behavior.",
            packet["active_instructions"],
        )
        self.assertIn(
            "Search existing behavior first and reuse established components or helpers.",
            packet["active_instructions"],
        )
        self.assertEqual(
            packet["global_cache"],
            {
                "cache_policy": "none",
                "tmcp_home": "[REDACTED:path]",
                "promoted_graph_count": 0,
                "receipt_count": 0,
                "warnings": [],
                "trust": "advisory_untrusted",
            },
        )

    def test_global_policy_uses_only_injected_canonical_cache_inputs(self) -> None:
        packet = compose_packet_from_source_nodes(
            {
                "objective": "Run a repo behavior sweep",
                "project_path": "[REDACTED:path]",
                "phase": "start",
                "cache_policy": "global",
            },
            source_nodes=[],
            global_graphs=[self._global_graph()],
            receipts=[{"packet_id": "packet-1"}, {"packet_id": "packet-2"}],
            cache_warnings=["cache warning"],
            cache_home="[REDACTED:path]",
        )

        self.assertEqual(packet["global_cache"]["promoted_graph_count"], 1)
        self.assertEqual(packet["global_cache"]["receipt_count"], 2)
        self.assertEqual(packet["global_cache"]["warnings"], ["cache warning"])
        self.assertIn(
            "canonical spreadsheet",
            " ".join(packet["active_instructions"]).lower(),
        )
        self.assertIn("repo_behavior_spec_loop_workflow", packet["active_atoms"])
        self.assertNotIn("MALICIOUS", str(packet))
        self.assertEqual(
            packet["shortcut_candidate"]["compiled_from"]["receipt_count"],
            2,
        )

    def test_compose_preserves_selected_source_output_contract(self) -> None:
        source = self._source_node("SKILL.md", "Return sources inspected.")
        source["routing_metadata"] = {"output_contract": ["Return sources inspected."]}

        packet = compose_packet_from_source_nodes(
            {
                "objective": "Evaluate skill behavior",
                "project_path": "[REDACTED:path]",
                "phase": "start",
                "cache_policy": "none",
            },
            source_nodes=[source],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )

        self.assertEqual(packet["output_contract"], ["Return sources inspected."])
        self.assertIn("## Output Contract", packet["packet_markdown"])

    def test_documentary_contracts_do_not_pollute_an_unrelated_packet(self) -> None:
        source = self._source_node(
            "PROJECT_TRUTH.md",
            "The composition study requires fresh approval for remote model calls.",
            source_type="project_documentation",
        )
        source["routing_metadata"] = {
            "stop_conditions": [
                "Obtain fresh approval for the composition study remote model calls.",
                "Do not prune ambiguous branches.",
            ],
            "output_contract": ["Return base + route_boost."],
        }

        packet = compose_packet_from_source_nodes(
            {
                "objective": (
                    "Audit the composition study guidebook for remote model evidence "
                    "while local hardening continues."
                ),
                "project_path": "[REDACTED:path]",
                "phase": "verification",
                "cache_policy": "none",
            },
            source_nodes=[source],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )

        self.assertEqual(
            packet["stop_conditions"],
            ["Obtain fresh approval for the composition study remote model calls."],
        )
        self.assertEqual(packet["output_contract"], [])

    def test_none_policy_discards_even_directly_injected_cache_inputs(self) -> None:
        arguments = {
            "objective": "Run a repo behavior sweep",
            "project_path": "[REDACTED:path]",
            "phase": "start",
            "cache_policy": "none",
        }
        baseline = compose_packet_from_source_nodes(
            arguments,
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        injected = compose_packet_from_source_nodes(
            arguments,
            source_nodes=[],
            global_graphs=[self._global_graph()],
            receipts=[{"packet_id": "packet-1"}],
            cache_warnings=["must not appear"],
            cache_home="[REDACTED:path]",
        )

        self.assertEqual(injected, baseline)
        self.assertEqual(injected["global_cache"]["promoted_graph_count"], 0)
        self.assertEqual(injected["global_cache"]["receipt_count"], 0)
        self.assertEqual(injected["global_cache"]["warnings"], [])
        self.assertNotIn(
            "canonical spreadsheet",
            " ".join(injected["active_instructions"]).lower(),
        )

    def test_unknown_cache_policy_discards_injected_cache_inputs(self) -> None:
        packet = compose_packet_from_source_nodes(
            {
                "objective": "Run a repo behavior sweep",
                "project_path": "[REDACTED:path]",
                "phase": "start",
                "cache_policy": "globla",
            },
            source_nodes=[],
            global_graphs=[self._global_graph()],
            receipts=[{"packet_id": "packet-1"}],
            cache_warnings=["cache warning"],
            cache_home="[REDACTED:path]",
        )

        self.assertEqual(packet["global_cache"]["cache_policy"], "none")
        self.assertEqual(packet["global_cache"]["promoted_graph_count"], 0)
        self.assertEqual(packet["global_cache"]["receipt_count"], 0)
        self.assertEqual(packet["global_cache"]["warnings"], [])
        self.assertNotIn(
            "canonical spreadsheet",
            " ".join(packet["active_instructions"]).lower(),
        )

    def test_active_instruction_projection_and_enrichment_dedupe(self) -> None:
        rich_node = self._source_node(
            "guides/needed.md",
            (
                "Use pnpm. Read before modifying. Search existing behavior first. "
                "Choose the brand register. Maintain a canonical spreadsheet. "
                "Record the last tested commit. Verify contrast, reduced motion, and responsive behavior."
            ),
            behavior_atoms=["alpha", "beta"],
        )
        fallback_node = self._source_node(
            "rules/fallback.md",
            "",
            behavior_atoms=["alpha", "beta"],
        )

        self.assertEqual(
            active_instructions_for_source_node(rich_node),
            [
                "Use pnpm for JavaScript dependency management, installs, and scripts.",
                "Read relevant project files before modifying behavior.",
                "Search existing behavior first and reuse established components or helpers.",
                "Choose the brand or product register before implementation decisions.",
                "Maintain one canonical spreadsheet/status-machine source of truth with stable Feature IDs.",
                "Record the last tested commit with verification evidence.",
                "Apply UI verification atoms for contrast, reduced motion, responsive behavior, and browser evidence.",
            ],
        )
        self.assertEqual(
            active_instructions_for_source_node(fallback_node),
            [
                "Apply relevant harvested behavior atoms from rules/fallback.md: alpha, beta."
            ],
        )

        packet = {
            "evidence_citations": [{"source": "already.md"}],
            "active_instructions": ["Existing instruction"],
        }
        already_cited = self._source_node(
            "already.md",
            "Use pnpm.",
            behavior_atoms=["existing"],
        )
        enriched = enrich_packet_from_source_nodes(
            packet,
            [rich_node, already_cited],
            ["guides/needed.md", "guides/needed.md", "already.md", "missing.md"],
        )

        self.assertIs(enriched, packet)
        self.assertEqual(
            [item["source"] for item in enriched["evidence_citations"]],
            ["already.md", "guides/needed.md"],
        )
        self.assertEqual(
            enriched["evidence_citations"][1]["matched_atoms"],
            ["alpha", "beta"],
        )
        self.assertEqual(enriched["active_instructions"][0], "Existing instruction")
        self.assertEqual(len(enriched["active_instructions"]), 8)

    def test_statistical_contrast_does_not_project_ui_instructions(self) -> None:
        statistical_node = self._source_node(
            "docs/evaluation.md",
            "Score the causal contrast in a controlled experimental design.",
            behavior_atoms=["evidence-backed-claims"],
        )

        self.assertEqual(
            active_instructions_for_source_node(statistical_node),
            [
                "Apply relevant harvested behavior atoms from docs/evaluation.md: evidence-backed-claims."
            ],
        )

    def test_compose_rejects_blank_objective(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "^tmcp_compose_packet requires objective[.]$",
        ):
            compose_packet_from_source_nodes(
                {"objective": "   "},
                source_nodes=[],
                global_graphs=[],
                receipts=[],
                cache_warnings=[],
                cache_home="[REDACTED:path]",
            )

    def test_compose_service_has_no_adapter_storage_or_io_imports(self) -> None:
        source_path = Path(inspect.getfile(compose_service))
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
            "os",
            "pathlib",
            "shutil",
            "subprocess",
            "scripts",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "tmcp_runtime.services.harvest",
            "tmcp_runtime.services.promotion",
            "tmcp_runtime.services.recommendations",
            "tmcp_runtime.services.review",
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
