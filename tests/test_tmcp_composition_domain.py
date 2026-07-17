from __future__ import annotations

import copy
import unittest
from typing import cast

from tmcp_runtime.domain import composition, packets
from tmcp_runtime.domain.routes import ROUTE_CATALOG_VERSION


def _node_signal_text(node: dict[str, object]) -> str:
    return str(node.get("signal") or "").lower()


class CompositionDomainTests(unittest.TestCase):
    def test_cache_policy_requires_explicit_global_opt_in(self) -> None:
        self.assertEqual(composition.normalize_cache_policy("global"), "global")
        for value in (None, "globla", " global", True):
            with self.subTest(value=value):
                self.assertEqual(composition.normalize_cache_policy(value), "none")

    def test_ui_classifiers_preserve_signal_boundaries_and_astro_support(self) -> None:
        self.assertTrue(
            composition.is_uiish_text("Design a responsive frontend dashboard.")
        )
        self.assertFalse(
            composition.is_uiish_text("Build a guide for the API service.")
        )
        self.assertTrue(composition.is_ui_file("app/page.astro"))
        self.assertTrue(composition.is_ui_file("src/styles/site.CSS"))
        self.assertFalse(composition.is_ui_file("src/service.py"))

    def test_contextual_gates_prioritize_hosted_evidence_over_debugging(self) -> None:
        atoms, reads, gates = composition.contextual_atoms_and_gates(
            "Fix the final release failure.",
            "final",
            {"failures": ["No hosted evidence is pending for this release."]},
        )

        self.assertIn("explicit-evidence-gaps", atoms)
        self.assertNotIn("debugging-regression", atoms)
        self.assertIn("verification-before-completion", atoms)
        self.assertIn(
            "Hosted release evidence record and release evidence checker output.",
            reads,
        )
        self.assertIn(
            "Do not claim release readiness until hosted evidence is recorded for release.",
            gates,
        )
        self.assertIn(
            "Run the highest-signal verification gate before final response.", gates
        )

    def test_contextual_gates_cover_ui_files_and_browser_evidence(self) -> None:
        atoms, reads, gates = composition.contextual_atoms_and_gates(
            "Design the dashboard.",
            "start",
            {"files_changed": ["app/dashboard.astro"]},
        )

        self.assertEqual(atoms, ["ui-browser-verification"])
        self.assertIn("UI/browser verification guidance for changed surfaces.", reads)
        self.assertIn("Verify contrast on visible UI states.", gates)
        self.assertIn(
            "Verify reduced motion behavior where animation is present.", gates
        )
        self.assertIn(
            "Verify responsive behavior across relevant viewport sizes.", gates
        )

        evidence_atoms, _, evidence_gates = composition.contextual_atoms_and_gates(
            "Review the release notes.",
            "start",
            {"browser_evidence": ["screenshot captured"]},
        )
        self.assertEqual(evidence_atoms, ["ui-browser-verification"])
        self.assertEqual(
            evidence_gates, ["Use browser evidence to confirm the next claim."]
        )

    def test_source_gate_filtering_requires_matching_context(self) -> None:
        gates = [
            "Verify browser screenshot after interaction.",
            "Maintain canonical spreadsheet coverage.",
            "Run the focused unit test.",
        ]

        self.assertEqual(
            composition.filter_source_verification_gates(
                gates,
                "Improve release packaging.",
                {},
            ),
            ["Run the focused unit test."],
        )
        self.assertEqual(
            composition.filter_source_verification_gates(
                gates,
                "Audit the canonical spreadsheet behavior sweep.",
                {},
            ),
            ["Maintain canonical spreadsheet coverage.", "Run the focused unit test."],
        )
        self.assertEqual(
            composition.filter_source_verification_gates(
                gates,
                "Polish the frontend dashboard.",
                {"files_changed": ["app/page.tsx"]},
            ),
            [
                "Verify browser screenshot after interaction.",
                "Run the focused unit test.",
            ],
        )

    def test_matching_reference_reads_selects_only_relevant_references(self) -> None:
        source_nodes = [
            {"relative_path": "docs/reference/craft.md"},
            {"relative_path": "docs/references/brand.md"},
            {"relative_path": "docs/reference/product.md"},
            {"relative_path": "docs/reference/verification.md"},
            {"relative_path": "docs/other/brand.md"},
        ]

        self.assertEqual(
            composition.matching_reference_reads(
                source_nodes,
                "Craft a landing site dashboard and verify browser behavior.",
            ),
            [
                "docs/reference/craft.md",
                "docs/references/brand.md",
                "docs/reference/product.md",
                "docs/reference/verification.md",
            ],
        )

    def test_node_scoring_preserves_defer_and_contextual_guardrails(self) -> None:
        deferred_family = {
            "primary_skill_slugs": ["product-design-runtime"],
            "deferred_skill_slugs": ["ui-implementation"],
            "family_skills_root": "skills/",
        }
        deferred = {"relative_path": "skills/ui-implementation/SKILL.md"}

        def signal_must_not_run(_: dict[str, object]) -> str:
            raise AssertionError(
                "deferred family sibling should not require source text"
            )

        self.assertEqual(
            composition.score_composition_node(
                deferred,
                "Use product design runtime.",
                "start",
                {},
                family_context=deferred_family,
                node_signal_text=signal_must_not_run,
            ),
            0.0,
        )

        repo_behavior = {
            "relative_path": "skills/repo-behavior/SKILL.md",
            "signal": "behavior inventory",
        }
        self.assertEqual(
            composition.score_composition_node(
                repo_behavior,
                "Improve release packaging.",
                "start",
                {},
                node_signal_text=_node_signal_text,
            ),
            0.0,
        )

        ui_rubric = {
            "relative_path": "skills/ui-rubric/SKILL.md",
            "signal": "browser contrast responsive dashboard",
        }
        self.assertEqual(
            composition.score_composition_node(
                ui_rubric,
                "Improve release packaging.",
                "start",
                {},
                node_signal_text=_node_signal_text,
            ),
            0.0,
        )
        self.assertGreater(
            composition.score_composition_node(
                ui_rubric,
                "Improve release packaging.",
                "start",
                {"files_changed": ["app/page.tsx"]},
                node_signal_text=_node_signal_text,
            ),
            0.0,
        )

        release_node = {
            "relative_path": "skills/release-readiness/SKILL.md",
            "signal": "package checks release readiness",
        }
        blocked_release_node = {
            **release_node,
            "routing_metadata": {"do_not_use_when": ["release readiness"]},
        }
        objective = "Run package checks for release readiness."
        allowed_score = composition.score_composition_node(
            release_node,
            objective,
            "start",
            {},
            node_signal_text=_node_signal_text,
        )
        blocked_score = composition.score_composition_node(
            blocked_release_node,
            objective,
            "start",
            {},
            node_signal_text=_node_signal_text,
        )
        self.assertEqual(allowed_score - blocked_score, 6.0)

    def test_node_selection_orders_ties_caps_results_and_preserves_inputs(self) -> None:
        positive_nodes = [
            {
                "relative_path": f"docs/node-{index:02d}.md",
                "source_type": "agent_operating_contract",
                "signal": "alpha",
            }
            for index in range(8, -1, -1)
        ]
        source_nodes = [
            *positive_nodes,
            {
                "relative_path": "docs/ignored.md",
                "source_type": "project_doc",
                "signal": "",
            },
        ]
        before = copy.deepcopy(source_nodes)

        selected = composition.select_composition_nodes(
            source_nodes,
            "Alpha",
            "start",
            {},
            node_signal_text=_node_signal_text,
        )

        self.assertEqual(
            [node["relative_path"] for node in selected],
            [f"docs/node-{index:02d}.md" for index in range(8)],
        )
        self.assertEqual(source_nodes, before)

    def test_node_selection_uses_specific_routing_metadata_but_ignores_generic_trigger(
        self,
    ) -> None:
        plain = {
            "relative_path": "skills/a/SKILL.md",
            "source_type": "skill_definition",
            "signal": "review",
        }
        boosted = {
            "relative_path": "skills/z/SKILL.md",
            "source_type": "skill_definition",
            "signal": "review",
            "routing_metadata": {
                "trigger_phrases": ["review"],
                "commands": ["pnpm"],
                "phase_hints": ["start"],
            },
        }
        selected = composition.select_composition_nodes(
            [plain, boosted],
            "Review with pnpm.",
            "start",
            {},
            family_context={"kind": "test"},
            active_routes=[],
            node_signal_text=_node_signal_text,
        )
        self.assertEqual(selected[0]["relative_path"], boosted["relative_path"])

        generic = {
            "relative_path": "skills/z/SKILL.md",
            "source_type": "skill_definition",
            "signal": "review",
            "routing_metadata": {"trigger_phrases": ["release"]},
        }
        generic_selected = composition.select_composition_nodes(
            [generic, plain],
            "Review release readiness.",
            "start",
            {},
            family_context={"kind": "test"},
            active_routes=[],
            node_signal_text=_node_signal_text,
        )
        self.assertEqual(generic_selected[0]["relative_path"], plain["relative_path"])

    def test_node_selection_resolves_family_and_routes_when_not_supplied(self) -> None:
        source_nodes = [
            {
                "relative_path": "skills/frontend-design/SKILL.md",
                "source_type": "skill_definition",
                "signal": "frontend design",
            }
        ]

        selected = composition.select_composition_nodes(
            source_nodes,
            "Redesign the frontend.",
            "start",
            {},
            node_signal_text=_node_signal_text,
        )

        self.assertEqual(selected, source_nodes)

    def test_node_selection_preserves_family_deferral_and_route_ordering(self) -> None:
        family_context = {
            "primary_skill_slugs": ["product-design-runtime"],
            "deferred_skill_slugs": ["ui-implementation"],
            "family_skills_root": "skills/product-judgment/",
        }
        primary = {
            "relative_path": "skills/product-design-runtime/SKILL.md",
            "source_type": "skill_definition",
            "signal": "product design runtime",
        }
        sibling = {
            "relative_path": "skills/ui-implementation/SKILL.md",
            "source_type": "skill_definition",
            "signal": "ui implementation",
        }
        route_match = {
            "relative_path": "skills/frontend-design/SKILL.md",
            "source_type": "skill_definition",
            "signal": "design",
        }
        neutral = {
            "relative_path": "skills/plain/SKILL.md",
            "source_type": "skill_definition",
            "signal": "design",
        }
        source_nodes = [primary, sibling, neutral, route_match]
        objective = "Use product design runtime before implementation."

        selected = composition.select_composition_nodes(
            source_nodes,
            objective,
            "start",
            {},
            family_context=family_context,
            active_routes=["ui_ux_redesign"],
            node_signal_text=_node_signal_text,
        )
        selected_paths = [node["relative_path"] for node in selected]
        self.assertIn(primary["relative_path"], selected_paths)
        self.assertNotIn(sibling["relative_path"], selected_paths)
        self.assertLess(
            selected_paths.index(route_match["relative_path"]),
            selected_paths.index(neutral["relative_path"]),
        )

        explicit_sibling = composition.select_composition_nodes(
            source_nodes,
            "Use product design runtime, then ui implementation.",
            "start",
            {},
            family_context=family_context,
            active_routes=["ui_ux_redesign"],
            node_signal_text=_node_signal_text,
        )
        self.assertIn(
            sibling["relative_path"],
            [node["relative_path"] for node in explicit_sibling],
        )

    def test_compiled_from_packet_is_stable_across_citation_order(self) -> None:
        citations = [
            {"source": "skills/z/SKILL.md"},
            {"path": "skills/a/SKILL.md"},
            {"source": ""},
        ]
        compiled = packets.compiled_from_packet(
            cache_policy="none",
            family_context={"active_seed_id": " frontend-run "},
            evidence_citations=citations,
        )
        reordered = packets.compiled_from_packet(
            cache_policy="none",
            family_context={"active_seed_id": " frontend-run "},
            evidence_citations=list(reversed(citations)),
        )
        no_seed = packets.compiled_from_packet(
            cache_policy="global",
            family_context=None,
            evidence_citations=[],
        )

        self.assertEqual(compiled, reordered)
        self.assertEqual(compiled["route_catalog_version"], ROUTE_CATALOG_VERSION)
        self.assertEqual(compiled["seed_id"], "frontend-run")
        self.assertEqual(compiled["cache_policy"], "none")
        self.assertIsNone(no_seed["seed_id"])

    def test_shortcut_candidate_uses_seed_then_identity_and_honors_overrides(
        self,
    ) -> None:
        compiled = {"graph_version": "graph"}
        no_match = packets.shortcut_candidate_for_composed_packet(
            packet={},
            compiled_from=compiled,
            receipt_count=2,
        )
        seeded = packets.shortcut_candidate_for_composed_packet(
            packet={
                "family_context": {"active_seed_id": "seed-id"},
                "task_identity": {"primary": "route-id"},
            },
            compiled_from=compiled,
            receipt_count=3,
        )
        overridden = packets.shortcut_candidate_for_composed_packet(
            packet={"task_identity": {"primary": "route-id"}},
            compiled_from=compiled,
            receipt_count=4,
            user_overrides=["keep legacy behavior"],
        )

        self.assertEqual(no_match["status"], "none")
        self.assertFalse(no_match["matched"])
        self.assertEqual(no_match["compiled_from"], compiled)
        self.assertEqual(seeded["shortcut_id"], "seed-id")
        self.assertEqual(seeded["status"], "eligible")
        self.assertTrue(seeded["matched"])
        self.assertEqual(seeded["compiled_from"]["receipt_count"], 3)
        self.assertEqual(overridden["shortcut_id"], "route-id")
        self.assertEqual(overridden["status"], "needs_revalidation")
        self.assertFalse(overridden["matched"])

    def test_selection_rationale_preserves_fallback_and_seed_branches(self) -> None:
        self.assertEqual(
            packets.selection_rationale({}),
            "TMCP selected sources from the harvested skill graph for the stated objective.",
        )
        self.assertEqual(
            packets.selection_rationale({"task_identity": {"primary": "audit"}}),
            "TMCP inferred primary task identity `audit` from the objective and runtime context.",
        )
        seeded = packets.selection_rationale(
            {
                "task_identity": {
                    "primary": "frontend_product_redesign",
                    "signals": [
                        {
                            "route": "ui_ux_redesign",
                            "score": 4.5,
                            "evidence": ["design", "dashboard"],
                        },
                        {"route": "frontend_implementation", "score": 3.0},
                    ],
                },
                "family_context": {"active_seed_id": "frontend-run"},
            }
        )

        self.assertIn("scoped packet seed `frontend-run`", seeded)
        self.assertIn("route `ui_ux_redesign`", seeded)
        self.assertIn("ui_ux_redesign (4.5)", seeded)
        self.assertIn("design, dashboard", seeded)

    def test_composed_markdown_preserves_sections_caps_and_trailing_newline(
        self,
    ) -> None:
        packet = {
            "objective": "Redesign the dashboard.",
            "phase": "implementation",
            "packet_id": "packet-123",
            "task_identity": {
                "primary": "frontend_product_redesign",
                "secondary": ["motion_interaction"],
                "active_routes": ["ui_ux_redesign"],
                "signals": [{"route": "ui_ux_redesign", "score": 5, "evidence": []}],
            },
            "family_context": {"active_seed_id": "frontend-run"},
            "evidence_citations": [
                {"source": "skill-with-atoms", "matched_atoms": ["a", "b"]},
                {"path": "skill-without-atoms"},
                *[{"source": f"extra-{index}"} for index in range(10)],
            ],
            "ignored_sources": [
                *[{"source": f"ignored-{index}"} for index in range(11)],
            ],
            "deferred_atoms": ["research"],
            "active_instructions": ["Read the existing component."],
            "verification_gates": ["Run the focused browser check."],
        }

        markdown = packets.render_composed_packet_markdown(packet)

        self.assertTrue(markdown.startswith("# TMCP Packet\n"))
        self.assertTrue(markdown.endswith("\n"))
        self.assertIn("## Task Identity", markdown)
        self.assertIn("## Active Routes", markdown)
        self.assertIn("- skill-with-atoms: a, b", markdown)
        self.assertIn("- skill-without-atoms", markdown)
        self.assertNotIn("extra-9", markdown)
        self.assertIn("## Excluded Skills", markdown)
        self.assertNotIn("ignored-10", markdown)
        self.assertIn("- deferred atoms: research", markdown)
        self.assertIn("1. Read the existing component.", markdown)
        self.assertIn("## Verification Gates", markdown)
        self.assertIn("## Recompile Triggers", markdown)
        self.assertIn("## Required Receipts", markdown)

    def test_build_composed_packet_owns_normalization_identity_and_receipt(
        self,
    ) -> None:
        selected = {
            "relative_path": "skills/selected/SKILL.md",
            "behavior_atoms": ["selected", "shared"],
        }
        unselected = [
            {
                "relative_path": f"skills/deferred-{index}/SKILL.md",
                "behavior_atoms": ["shared", f"deferred-{index}"],
            }
            for index in range(13)
        ]
        source_nodes = [selected, *unselected]
        active_instructions = [f" instruction {index} " for index in range(12)]
        required_reads = [f" read {index} " for index in range(14)]
        prompts = [f" prompt {index} " for index in range(12)]
        gates = [f" gate {index} " for index in range(12)]
        stops = [f" stop {index} " for index in range(10)]
        output_contract = [f" output {index} " for index in range(10)]
        atoms = ["selected", "shared", *[f"active-{index}" for index in range(20)]]
        global_cache = {
            "cache_policy": "none",
            "tmcp_home": "[redacted]",
            "promoted_graph_count": 0,
            "receipt_count": 2,
            "warnings": [],
            "trust": "advisory_untrusted",
        }
        inputs_before = copy.deepcopy(
            {
                "source_nodes": source_nodes,
                "active_instructions": active_instructions,
                "required_reads": required_reads,
                "atoms": atoms,
                "global_cache": global_cache,
            }
        )

        def build(objective: str) -> dict[str, object]:
            return packets.build_composed_packet(
                composed_packet_schema="tmcp-composed-packet-v0.1",
                objective=objective,
                project_path="/project",
                phase="implementation",
                task_identity={
                    "primary": "frontend_implementation",
                    "active_routes": ["frontend_implementation"],
                },
                family_context={"active_seed_id": "seed-id"},
                source_nodes=source_nodes,
                selected_nodes=[selected],
                active_instructions=active_instructions,
                required_reads=required_reads,
                tool_script_prompts=prompts,
                verification_gates=gates,
                stop_conditions=stops,
                output_contract=output_contract,
                active_atoms=atoms,
                evidence_citations=[{"source": "skills/selected/SKILL.md"}],
                conflicts=[{"id": "javascript_package_manager"}],
                cache_policy="none",
                global_cache=global_cache,
                receipt_count=2,
                user_overrides=[],
            )

        first = build("Implement the dashboard.")
        same = build("Implement the dashboard.")
        changed = build("Implement the settings page.")

        required_fields = {
            "schema",
            "packet_id",
            "objective",
            "project_path",
            "phase",
            "active_instructions",
            "required_reads",
            "tool_script_prompts",
            "verification_gates",
            "stop_conditions",
            "output_contract",
            "active_atoms",
            "deferred_atoms",
            "ignored_sources",
            "conflicts",
            "evidence_citations",
            "global_cache",
            "receipt_template",
            "safety",
        }
        self.assertTrue(required_fields.issubset(first))
        self.assertEqual(first["packet_id"], same["packet_id"])
        self.assertNotEqual(first["packet_id"], changed["packet_id"])
        self.assertEqual(
            first["active_instructions"],
            [f"instruction {index}" for index in range(10)],
        )
        self.assertEqual(
            first["required_reads"], [f"read {index}" for index in range(12)]
        )
        self.assertEqual(
            first["tool_script_prompts"], [f"prompt {index}" for index in range(10)]
        )
        self.assertEqual(
            first["verification_gates"], [f"gate {index}" for index in range(10)]
        )
        self.assertEqual(
            first["stop_conditions"], [f"stop {index}" for index in range(8)]
        )
        self.assertEqual(
            first["output_contract"], [f"output {index}" for index in range(8)]
        )
        self.assertEqual(
            first["active_atoms"],
            ["selected", "shared", *[f"active-{index}" for index in range(14)]],
        )
        self.assertEqual(
            first["deferred_atoms"], [f"deferred-{index}" for index in range(8)]
        )
        ignored_sources = cast(list[dict[str, object]], first["ignored_sources"])
        receipt_template = cast(dict[str, object], first["receipt_template"])
        safety = cast(dict[str, object], first["safety"])
        self.assertEqual(len(ignored_sources), 12)
        self.assertEqual(ignored_sources[0]["source"], "skills/deferred-0/SKILL.md")
        self.assertEqual(first["global_cache"], global_cache)
        self.assertEqual(first["conflicts"], [{"id": "javascript_package_manager"}])
        self.assertEqual(receipt_template["packet_id"], first["packet_id"])
        self.assertEqual(receipt_template["activated_atoms"], first["active_atoms"])
        self.assertEqual(receipt_template["user_overrides"], [])
        self.assertEqual(safety["harvested_text_trust"], "untrusted_evidence_only")
        packet_markdown = cast(str, first["packet_markdown"])
        self.assertIn(first["packet_id"], packet_markdown)
        self.assertEqual(
            first["packet_markdown"], packets.render_composed_packet_markdown(first)
        )
        self.assertEqual(
            inputs_before,
            {
                "source_nodes": source_nodes,
                "active_instructions": active_instructions,
                "required_reads": required_reads,
                "atoms": atoms,
                "global_cache": global_cache,
            },
        )

    def test_merge_composition_nodes_preserves_order_identity_and_caps(self) -> None:
        first = {"relative_path": "skills/first/SKILL.md"}
        duplicate = {"relative_path": "skills/first/SKILL.md"}
        second = {"relative_path": "docs/second.md"}
        third = {"relative_path": "docs/third.md"}
        primary = [first, duplicate]
        additional = [duplicate, second, {"title": "no path"}, third]
        before = copy.deepcopy({"primary": primary, "additional": additional})

        merged = composition.merge_composition_nodes(
            primary,
            additional,
            max_nodes=2,
        )

        self.assertEqual(
            [node["relative_path"] for node in merged],
            ["skills/first/SKILL.md", "docs/second.md"],
        )
        self.assertIs(merged[0], first)
        self.assertIs(merged[1], second)
        self.assertEqual({"primary": primary, "additional": additional}, before)


if __name__ == "__main__":
    unittest.main()
