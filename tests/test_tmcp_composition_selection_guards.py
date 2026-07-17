from __future__ import annotations

import unittest
from typing import Any

from tmcp_runtime.domain import composition


def _signal(node: dict[str, Any]) -> str:
    return str(node.get("signal") or "")


def _node(
    path: str,
    signal: str,
    *,
    source_role: str = "active_skill",
    source_type: str = "skill_definition",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": path.replace("/", "-"),
        "relative_path": path,
        "source_role": source_role,
        "source_type": source_type,
        "signal": signal,
        **extra,
    }


class CompositionSelectionGuardTests(unittest.TestCase):
    def test_process_overlap_and_phase_hints_cannot_activate_unrelated_skill(
        self,
    ) -> None:
        governing = _node(
            "AGENTS.md",
            "Use the project operating contract.",
            source_role="governing_instruction",
            source_type="agent_operating_contract",
        )
        relevant = _node(
            "skills/entitlement-ledger/SKILL.md",
            "Maintain entitlement ledger provenance.",
        )
        phase_only = _node(
            "skills/release-process/SKILL.md",
            "Implement, validate, test, and verify the result.",
            routing_metadata={"phase_hints": ["implementation"]},
        )

        selected, diagnostics = composition.select_composition_nodes_with_diagnostics(
            [governing, phase_only, relevant],
            "Implement an entitlement ledger migration.",
            "implementation",
            {},
            node_signal_text=_signal,
        )

        self.assertEqual(
            [node["relative_path"] for node in selected],
            ["AGENTS.md", "skills/entitlement-ledger/SKILL.md"],
        )
        rejected = {
            item["source"]: item["reason"]
            for item in diagnostics["rejected_sources"]
        }
        self.assertEqual(
            rejected["skills/release-process/SKILL.md"],
            "phase_hint_without_non_process_relevance",
        )

    def test_phase_is_only_a_tie_break_after_non_process_relevance(self) -> None:
        phase_only = _node(
            "skills/a-phase-only/SKILL.md",
            "Implement, test, and verify.",
            routing_metadata={"phase_hints": ["implementation"]},
        )
        base = _node(
            "skills/a-base/SKILL.md",
            "Entitlement ledger.",
        )
        phase_relevant = _node(
            "skills/z-phase-relevant/SKILL.md",
            "Entitlement ledger.",
            routing_metadata={"phase_hints": ["implementation"]},
        )

        self.assertEqual(
            composition.score_composition_node(
                phase_only,
                "Implement the entitlement ledger.",
                "implementation",
                {},
                node_signal_text=_signal,
            ),
            0.0,
        )
        self.assertGreater(
            composition.score_composition_node(
                phase_relevant,
                "Implement the entitlement ledger.",
                "implementation",
                {},
                node_signal_text=_signal,
            ),
            composition.score_composition_node(
                base,
                "Implement the entitlement ledger.",
                "implementation",
                {},
                node_signal_text=_signal,
            ),
        )

        selected = composition.select_composition_nodes(
            [phase_only, base, phase_relevant],
            "Implement the entitlement ledger.",
            "implementation",
            {},
            node_signal_text=_signal,
        )
        self.assertEqual(
            [node["relative_path"] for node in selected],
            ["skills/z-phase-relevant/SKILL.md"],
        )

    def test_no_proposal_path_caps_automatic_selection_to_one_bootstrap_skill(
        self,
    ) -> None:
        first = _node(
            "skills/a-semantic-handoff/SKILL.md",
            "Semantic handoff provenance.",
        )
        second = _node(
            "skills/b-graph-provenance/SKILL.md",
            "Semantic graph provenance.",
        )

        selected, diagnostics = composition.select_composition_nodes_with_diagnostics(
            [second, first],
            "Stabilize semantic handoff provenance.",
            "implementation",
            {},
            node_signal_text=_signal,
        )

        self.assertEqual(
            [node["relative_path"] for node in selected],
            ["skills/a-semantic-handoff/SKILL.md"],
        )
        self.assertEqual(diagnostics["selection_mode"], "narrow_bootstrap")
        self.assertEqual(
            diagnostics["selected_automatic_bootstrap_sources"],
            ["skills/a-semantic-handoff/SKILL.md"],
        )
        rejected = {
            item["source"]: item["reason"]
            for item in diagnostics["rejected_sources"]
        }
        self.assertEqual(
            rejected["skills/b-graph-provenance/SKILL.md"],
            "deferred_after_narrow_bootstrap_cap",
        )
        self.assertTrue(diagnostics["warnings"])

    def test_exact_route_phrase_remains_stronger_than_its_generic_tokens(self) -> None:
        release = _node(
            "skills/tmcp-release-readiness/SKILL.md",
            "Use for release readiness and package checks.",
        )
        performance = _node(
            "skills/tmcp-performance-readiness/SKILL.md",
            "Use for performance readiness and capacity checks.",
        )

        selected = composition.select_composition_nodes(
            [performance, release],
            "Improve TMCP release readiness before release.",
            "start",
            {},
            node_signal_text=_signal,
        )

        self.assertEqual(
            [node["relative_path"] for node in selected],
            ["skills/tmcp-release-readiness/SKILL.md"],
        )

    def test_explicit_scope_and_matched_seed_remain_available(self) -> None:
        explicitly_scoped = _node(
            "skills/explicit/SKILL.md",
            "Implement and verify the result.",
            explicitly_scoped=True,
        )
        bootstrap = _node(
            "skills/semantic-handoff/SKILL.md",
            "Semantic handoff provenance.",
        )
        seed = _node(
            "scoped-packet-seeds.json#handoff_seed",
            "Implement and verify the result.",
            source_type="scoped_packet_seed",
            seed_id="handoff_seed",
        )
        seed_primary = _node(
            "skills/seed-primary/SKILL.md",
            "Implement and verify the result.",
        )

        selected, diagnostics = composition.select_composition_nodes_with_diagnostics(
            [bootstrap, explicitly_scoped, seed, seed_primary],
            "Handle an unrelated administrative request.",
            "implementation",
            {},
            family_context={
                "active_seed_id": "handoff_seed",
                "primary_source_patterns": ["skills/seed-primary/SKILL.md"],
            },
            node_signal_text=_signal,
        )

        self.assertEqual(
            {node["relative_path"] for node in selected},
            {
                "scoped-packet-seeds.json#handoff_seed",
                "skills/seed-primary/SKILL.md",
                "skills/explicit/SKILL.md",
            },
        )
        self.assertEqual(diagnostics["selection_mode"], "family_scoped")
        self.assertIn(
            "scoped-packet-seeds.json#handoff_seed",
            diagnostics["selected_explicit_sources"],
        )


if __name__ == "__main__":
    unittest.main()
