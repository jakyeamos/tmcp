from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.storage import artifact_persistence_available


ADAPTIVE_PACK_SCHEMA_PATH = (
    helpers.PLUGIN_ROOT / "schemas" / "tmcp-adaptive-workflow-pack-v0.1.schema.json"
)

class TmcpWorkflowRecommendationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_recommend_workflows_uses_harvested_priority_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: frontend-ui-review",
                        "---",
                        "# UI Review",
                        "Use screenshots, responsive layout checks, design-system fit, visual polish, and component state evidence.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text(
                "# Agent Rules\n\nVerify UI states with evidence before implementation.\n",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {"source_path": str(root), "limit": 10},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-workflow-recommendation-v1")
        self.assertIn("ui_quality", result["priority_profile"]["primary_signals"])
        self.assertEqual(
            result["recommended_workflows"][0]["id"], "expert_ui_rubric_workflow"
        )
        self.assertEqual(
            result["recommended_workflows"][0]["stability"], "experimental"
        )
        self.assertEqual(
            result["recommended_workflows"][0]["template"]["stability"],
            "experimental",
        )
        self.assertTrue(result["recommended_workflows"][0]["evidence"])
        self.assertIn("starter_prompt", result["recommended_workflows"][0])

    def test_recommend_workflows_does_not_match_ui_inside_public(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SECURITY.md").write_text(
                "# Public Trust\n\nUse public-sector evidence, source citations, and artifact contracts.",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["ui_quality"],
                    "min_confidence": 0.1,
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["recommended_workflows"], [])
        self.assertEqual(
            result["signal_scores"][0]["workflow_id"], "expert_ui_rubric_workflow"
        )
        self.assertEqual(result["signal_scores"][0]["confidence"], 0.0)

    def test_recommend_workflows_labels_ui_guidance_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: controls-review",
                        "---",
                        "# Controls Review",
                        "Use icon buttons, tooltips, segmented controls, and toolbar actions for dense tools.",
                        "Verify browser screenshots, responsive behavior, and contrast for visible states.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["ui_quality"],
                    "min_confidence": 0.1,
                },
            )

        self.assertTrue(result["ok"])
        recommendation = result["recommended_workflows"][0]
        guidance_label_ids = {
            label["id"]
            for evidence in recommendation["evidence"]
            for label in evidence["guidance_labels"]
        }
        self.assertIn("ui:buttons-controls", guidance_label_ids)
        self.assertIn("ui:browser-verification", guidance_label_ids)
        source_map_label_ids = {
            label["id"]
            for node in result["adaptive_workflow_pack"]["harvested_source_map"]
            for label in node["guidance_labels"]
        }
        self.assertIn("ui:buttons-controls", source_map_label_ids)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_recommend_workflows_returns_adaptive_pack_and_custom_ideas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "recommendations"
            (root / "AGENTS.md").write_text(
                "\n".join(
                    [
                        "# Agent Rules",
                        "Keep command discovery, onboarding, setup docs, and release handoff evidence current.",
                        "Preserve source traceability, quality gates, and ordered next actions in every workflow.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                    "min_confidence": 0.1,
                },
            )

            pack = result["adaptive_workflow_pack"]
            self.assertEqual(pack["schema"], "tmcp-adaptive-workflow-pack-v0.1")
            self.assertEqual(pack["artifact_type"], "adaptive_workflow_pack")
            self.assertIn("workflow_stability", pack)
            self.assertTrue(pack["harvested_source_map"])
            self.assertTrue(pack["operating_profile"]["source_scope_counts"])
            self.assertTrue(pack["strongest_behavior_signals"])
            self.assertTrue(pack["recommended_default_templates"])
            self.assertTrue(pack["generated_custom_workflow_ideas"])
            self.assertEqual(
                result["custom_workflow_ideas"],
                pack["generated_custom_workflow_ideas"],
            )
            self.assertTrue(
                all(
                    item["stability"] == "experimental"
                    for item in result["custom_workflow_ideas"]
                )
            )
            self.assertTrue(pack["suggested_routing_triggers"])
            self.assertTrue(pack["documented_process_gaps"])
            self.assertEqual(pack["next_workflow_selection"]["approval_required"], True)
            self.assertTrue(
                Path(result["artifact_paths"]["adaptive_pack_json"]).exists()
            )

    def test_recommend_workflows_promotes_public_sector_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            (docs / "crimclock-readiness.md").write_text(
                "\n".join(
                    [
                        "# CrimClock Public Sector Readiness",
                        "A government launch gate must cite compliance policy, governance owners,",
                        "UAT signoff, accessibility and WCAG evidence, auditability, tenant boundaries,",
                        "legal calculation fixtures, risk register entries, acceptance criteria, and release blockers.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {"source_path": str(root), "limit": 10, "min_confidence": 0.1},
            )

        recommendation = result["recommended_workflows"][0]
        self.assertEqual(recommendation["id"], "public_sector_readiness_workflow")
        self.assertEqual(recommendation["signal_family"], "public_sector_readiness")
        self.assertIn(
            "public_sector_readiness", result["priority_profile"]["primary_signals"]
        )
        self.assertEqual(
            recommendation["template"]["profile"], "public_sector_readiness"
        )
        self.assertEqual(
            recommendation["rubric_seed"]["profile"], "public_sector_readiness"
        )
        dimension_ids = {
            item["id"] for item in recommendation["rubric_seed"]["dimension_seeds"]
        }
        self.assertIn("governance_policy_fit", dimension_ids)
        self.assertIn("legal_calculation_safety", dimension_ids)
        self.assertIn("accessibility_public_use", dimension_ids)
        required_evidence = " ".join(
            recommendation["workflow_instance"]["required_evidence"]
        ).lower()
        self.assertIn("uat", required_evidence)
        self.assertIn("accessibility", required_evidence)
        self.assertIn("compliance", required_evidence)

    def test_recommend_workflows_filters_public_sector_signal_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public-sector-uat.md").write_text(
                "# UAT Gate\n\nTrack government compliance, public-sector accessibility, and policy acceptance criteria.",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["public_sector_readiness"],
                    "min_confidence": 0.1,
                },
            )

        self.assertEqual(
            [item["id"] for item in result["recommended_workflows"]],
            ["public_sector_readiness_workflow"],
        )
        self.assertEqual(result["not_recommended"], [])

    def test_recommended_workflows_separate_template_and_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "# UI Audit\n\nUse screenshots, visual polish, responsive checks, and design-system evidence.",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {"source_path": str(root), "min_confidence": 0.1},
            )

        recommendation = result["recommended_workflows"][0]
        self.assertEqual(recommendation["template"]["id"], recommendation["id"])
        self.assertEqual(recommendation["template"]["kind"], "default_template")
        self.assertEqual(
            recommendation["workflow_instance"]["template_id"], recommendation["id"]
        )
        self.assertEqual(recommendation["workflow_instance"]["status"], "candidate")
        self.assertTrue(recommendation["workflow_instance"]["adapted_from"])
        self.assertTrue(recommendation["workflow_instance"]["generated_rubric"])
        self.assertTrue(recommendation["workflow_instance"]["required_evidence"])
        self.assertTrue(recommendation["workflow_instance"]["routing_trigger"])
        self.assertEqual(
            recommendation["workflow_instance"]["next_step"],
            "Ask the user to approve this workflow before running expert_rubric_review_plan.",
        )

    def test_adaptive_workflow_pack_schema_required_fields_match_output(self) -> None:
        self.assertTrue(ADAPTIVE_PACK_SCHEMA_PATH.exists())
        schema = json.loads(ADAPTIVE_PACK_SCHEMA_PATH.read_text(encoding="utf-8"))
        result = self.server._call_tool(
            "tmcp_recommend_workflows",
            {
                "source_path": str(helpers.PLUGIN_ROOT / "examples" / "workflows"),
                "limit": 5,
                "min_confidence": 0.1,
            },
        )

        pack = result["adaptive_workflow_pack"]
        self.assertEqual(schema["properties"]["schema"]["const"], pack["schema"])
        missing = [field for field in schema["required"] if field not in pack]
        self.assertEqual(missing, [])

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_recommend_workflows_filters_candidates_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "recommendations"
            (root / "SECURITY.md").write_text(
                "# Security\n\nRedact secrets, review permissions, audit auth tokens, and inspect data flow privacy.\n",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["security_privacy_review_workflow"],
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                },
            )

            self.assertEqual(
                [item["id"] for item in result["recommended_workflows"]],
                ["security_privacy_review_workflow"],
            )
            self.assertEqual(
                result["recommended_workflows"][0]["stability"], "experimental"
            )
            self.assertEqual(result["not_recommended"], [])
            paths = result["artifact_paths"]
            self.assertTrue(Path(paths["recommendation_json"]).exists())
            self.assertTrue(Path(paths["recommendation_markdown"]).exists())

    def test_recommend_workflows_includes_adaptive_default_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workflows.md").write_text(
                "\n".join(
                    [
                        "# Operating Workflows",
                        "Run incident postmortem and regression analysis after outages.",
                        "Write ADR architecture decision records with alternatives and tradeoffs.",
                        "Plan migrations, upgrades, deprecation cleanup, and rollback validation.",
                        "Create handoff and continuity packets for agents before pausing work.",
                        "Review PR risk, pull request diffs, changed contracts, and merge safety.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": [
                        "incident_postmortem_workflow",
                        "architecture_decision_workflow",
                        "migration_readiness_workflow",
                        "agent_handoff_workflow",
                        "pr_risk_review_workflow",
                    ],
                    "min_confidence": 0.1,
                },
            )

        recommended_ids = {item["id"] for item in result["recommended_workflows"]}
        self.assertEqual(
            {item["stability"] for item in result["recommended_workflows"]},
            {"experimental"},
        )
        self.assertEqual(
            recommended_ids,
            {
                "incident_postmortem_workflow",
                "architecture_decision_workflow",
                "migration_readiness_workflow",
                "agent_handoff_workflow",
                "pr_risk_review_workflow",
            },
        )

    def test_recommend_workflows_filters_expanded_signal_families(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Agent Rules\n\nPrepare handoff continuity packets with state, blockers, next commands, and open questions.\n",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["agent_handoff"],
                    "min_confidence": 0.1,
                },
            )

        self.assertEqual(
            [item["id"] for item in result["recommended_workflows"]],
            ["agent_handoff_workflow"],
        )
        self.assertEqual(
            result["recommended_workflows"][0]["stability"], "experimental"
        )
        self.assertEqual(result["not_recommended"], [])

    def test_recommend_workflows_promotes_repo_behavior_spec_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: repo-behavior-spec-loop",
                        "---",
                        "# Repo Behavior Spec Loop",
                        "Create one canonical spreadsheet with stable Feature ID values,",
                        "code-derived expected behavior, user-acceptable behavior, source files/functions,",
                        "test command/actions, observed behavior, Status, Defect ID, Defect type,",
                        "Regression test added, Complexity review, Evidence, Iteration, and Last tested commit.",
                        "Drive every feature from spec -> tested -> fixed -> verified -> regression-covered.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["repo_behavior_spec_loop"],
                    "min_confidence": 0.1,
                },
            )

        self.assertEqual(
            [item["id"] for item in result["recommended_workflows"]],
            ["repo_behavior_spec_loop_workflow"],
        )
        recommendation = result["recommended_workflows"][0]
        self.assertEqual(recommendation["signal_family"], "repo_behavior_spec_loop")
        self.assertEqual(recommendation["stability"], "experimental")
        self.assertEqual(
            recommendation["template"]["profile"], "repo_behavior_spec_loop"
        )
        self.assertEqual(
            recommendation["rubric_seed"]["profile"], "repo_behavior_spec_loop"
        )
        dimension_ids = {
            item["id"] for item in recommendation["rubric_seed"]["dimension_seeds"]
        }
        self.assertIn("code_derived_feature_inventory", dimension_ids)
        self.assertIn("canonical_spreadsheet_contract", dimension_ids)
        self.assertIn("running_app_verification_loop", dimension_ids)
        required_evidence = " ".join(
            recommendation["workflow_instance"]["required_evidence"]
        ).lower()
        self.assertIn("canonical spreadsheet", required_evidence)
        self.assertIn("feature ids", required_evidence)
        self.assertIn("last tested commit", required_evidence)
        self.assertEqual(result["not_recommended"], [])

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_promote_harvest_writes_durable_graph_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "promotion"
            tmcp_home = root / "tmcp-home"
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            (root / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: repo-behavior-spec-loop",
                        "---",
                        "# Repo Behavior Spec Loop",
                        "Maintain a canonical spreadsheet with stable Feature IDs, Evidence,",
                        "source files/functions, observed behavior, Last tested commit, and Status.",
                        "Run the test/fix/re-test loop until verified and regression-covered.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text(
                "# Agent Rules\n\nKeep evidence-backed claims and source traceability in behavior verification work.",
                encoding="utf-8",
            )

            try:
                result = self.server._call_tool(
                    "tmcp_promote_harvest",
                    {
                        "source_path": str(root),
                        "candidate_workflows": ["repo_behavior_spec_loop"],
                        "selected_workflows": ["repo_behavior_spec_loop_workflow"],
                        "min_confidence": 0.1,
                        "promotion_name": "repo-behavior-spec-loop",
                        "output_dir": str(output_dir),
                    },
                )
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            graph_path = Path(result["artifact_paths"]["promotion_graph_json"])
            self.assertTrue(graph_path.exists())
            graph = json.loads(graph_path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-harvest-promotion-v0.1")
        self.assertEqual(result["status"], "promoted")
        self.assertEqual(
            result["promoted_workflow_ids"], ["repo_behavior_spec_loop_workflow"]
        )
        self.assertEqual(graph["schema"], "tmcp-promoted-harvest-graph-v0.1")
        self.assertTrue(graph["source_nodes"])
        self.assertTrue(graph["behavior_atoms"])
        self.assertTrue(
            any(edge["relation"] == "declares_behavior_atom" for edge in graph["edges"])
        )
        self.assertTrue(
            any(edge["relation"] == "supports_workflow" for edge in graph["edges"])
        )

    def test_promote_harvest_preview_does_not_write_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Release\n\nUse release readiness, verification evidence, and quality gates.",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_promote_harvest",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["release_readiness"],
                    "min_confidence": 0.1,
                    "write_artifacts": False,
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["artifact_paths"], {})
        self.assertTrue(result["promotion_graph"]["edges"])

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_default_promotion_directory_uses_a_slugged_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "# Release Readiness\n\nUse release checks and package verification.\n",
                encoding="utf-8",
            )
            result = self.server._call_tool(
                "tmcp_promote_harvest",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["release_readiness"],
                    "selected_workflows": ["release_readiness_workflow"],
                    "min_confidence": 0.1,
                    "promotion_name": "../../outside",
                    "persist_global": False,
                },
            )

            output_dir = root / ".tmcp" / "promoted-harvests" / "outside"

            self.assertTrue(result["artifact_paths"])
            self.assertTrue((output_dir / "promotion-graph.json").exists())
            self.assertFalse((root / "outside").exists())

    def test_compose_packet_combines_impeccable_and_agent_slices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "impeccable"
            refs = skill / "reference"
            refs.mkdir(parents=True)
            (root / "AGENTS.md").write_text(
                "\n".join(
                    [
                        "# Agent Rules",
                        "Use pnpm only.",
                        "Read before modifying.",
                        "Search existing behavior first.",
                    ]
                ),
                encoding="utf-8",
            )
            (skill / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: impeccable",
                        "---",
                        "# Impeccable",
                        "For craft commands, run scripts/context.mjs, then read reference/craft.md.",
                        "Choose the brand or product register before implementation.",
                        "If no design tokens exist, run scripts/palette.mjs.",
                        "Verify contrast, reduced motion, responsive behavior, and browser screenshots.",
                    ]
                ),
                encoding="utf-8",
            )
            (refs / "craft.md").write_text(
                "# Craft\n\nBuild production UI only after discovery and browser verification.",
                encoding="utf-8",
            )
            (refs / "brand.md").write_text(
                "# Brand\n\nUse distinctive visual direction for landing pages.",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_compose_packet",
                {
                    "source_path": str(root),
                    "objective": "impeccable craft landing page",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 10,
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-composed-packet-v0.1")
        packet_text = " ".join(result["active_instructions"]).lower()
        required_reads = " ".join(result["required_reads"])
        tool_prompts = " ".join(result["tool_script_prompts"])
        verification = " ".join(result["verification_gates"]).lower()
        active_atoms = set(result["active_atoms"])

        self.assertIn("pnpm", packet_text)
        self.assertIn("existing behavior", packet_text)
        self.assertIn("reference/craft.md", required_reads)
        self.assertIn("reference/brand.md", required_reads)
        self.assertIn("scripts/context.mjs", tool_prompts)
        self.assertIn("scripts/palette.mjs", tool_prompts)
        self.assertIn("contrast", verification)
        self.assertIn("reduced motion", verification)
        self.assertIn("browser", verification)
        self.assertIn("ui-browser-verification", active_atoms)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_compose_packet_consumes_global_promoted_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            project = Path(tmp) / "project"
            tmcp_home = Path(tmp) / "tmcp-home"
            root.mkdir()
            project.mkdir()
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                (root / "SKILL.md").write_text(
                    "\n".join(
                        [
                            "---",
                            "name: repo-behavior-spec-loop",
                            "---",
                            "# Repo Behavior Spec Loop",
                            "Maintain one canonical spreadsheet with stable Feature IDs,",
                            "source files/functions, observed behavior, Status, Evidence,",
                            "Last tested commit, and regression-covered verification.",
                        ]
                    ),
                    encoding="utf-8",
                )

                promote = self.server._call_tool(
                    "tmcp_promote_harvest",
                    {
                        "source_path": str(root),
                        "candidate_workflows": ["repo_behavior_spec_loop"],
                        "selected_workflows": ["repo_behavior_spec_loop_workflow"],
                        "min_confidence": 0.1,
                        "promotion_name": "repo-behavior-spec-loop",
                        "output_dir": str(Path(tmp) / "promotion"),
                    },
                )
                result = self.server._call_tool(
                    "tmcp_compose_packet",
                    {
                        "source_path": str(project),
                        "objective": "run a repo behavior sweep",
                        "project_path": str(project),
                        "phase": "start",
                        "cache_policy": "global",
                    },
                )
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

        self.assertTrue(promote["global_artifact_paths"]["promotion_graph_json"])
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["global_cache"]["promoted_graph_count"], 1)
        packet_text = " ".join(result["active_instructions"]).lower()
        self.assertIn("canonical spreadsheet", packet_text)
        self.assertIn("feature id", packet_text)

    def test_compose_packet_keeps_release_readiness_packet_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "tmcp-release-readiness").mkdir(parents=True)
            (root / "skills" / "tmcp-pr-risk-review").mkdir(parents=True)
            (root / "skills" / "tmcp-repo-behavior-spec-loop").mkdir(parents=True)
            (root / "skills" / "tmcp-ui-rubric").mkdir(parents=True)
            (root / "skills" / "tmcp-migration-readiness").mkdir(parents=True)
            (root / "skills" / "tmcp-performance-readiness").mkdir(parents=True)
            (root / "skills" / "tmcp-release-readiness" / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: tmcp-release-readiness",
                        "---",
                        "# TMCP Release Readiness",
                        "Use for release readiness, ship/no-ship planning, quality gates, package checks, CI evidence, and changelog review.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "skills" / "tmcp-pr-risk-review" / "SKILL.md").write_text(
                "# PR Risk Review\n\nUse for changed-surface maps and merge risk reviews.",
                encoding="utf-8",
            )
            (root / "skills" / "tmcp-repo-behavior-spec-loop" / "SKILL.md").write_text(
                "# Repo Behavior Spec Loop\n\nMaintain one canonical spreadsheet with stable Feature IDs and last tested commit evidence.",
                encoding="utf-8",
            )
            (root / "skills" / "tmcp-ui-rubric" / "SKILL.md").write_text(
                "# UI Rubric\n\nVerify browser screenshots, contrast, reduced motion, and responsive behavior.",
                encoding="utf-8",
            )
            (root / "skills" / "tmcp-migration-readiness" / "SKILL.md").write_text(
                "# Migration Readiness\n\nUse for migration readiness, deprecation, rollout, and compatibility risk.",
                encoding="utf-8",
            )
            (root / "skills" / "tmcp-performance-readiness" / "SKILL.md").write_text(
                "# Performance Readiness\n\nUse for performance readiness, latency, load, and capacity risk.",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_compose_packet",
                {
                    "source_path": str(root),
                    "objective": "Improve TMCP release readiness before release",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 12,
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-composed-packet-v0.1")
        active_text = " ".join(result["active_instructions"]).lower()
        verification_text = " ".join(result["verification_gates"]).lower()
        cited_sources = {
            str(citation.get("source") or "")
            for citation in result["evidence_citations"]
        }
        self.assertTrue(
            any(
                source.endswith("tmcp-release-readiness/SKILL.md")
                for source in cited_sources
            )
        )
        self.assertFalse(
            any(
                source.endswith("tmcp-repo-behavior-spec-loop/SKILL.md")
                for source in cited_sources
            )
        )
        self.assertFalse(
            any(source.endswith("tmcp-ui-rubric/SKILL.md") for source in cited_sources)
        )
        self.assertFalse(
            any(
                source.endswith("tmcp-migration-readiness/SKILL.md")
                for source in cited_sources
            )
        )
        self.assertFalse(
            any(
                source.endswith("tmcp-performance-readiness/SKILL.md")
                for source in cited_sources
            )
        )
        self.assertNotIn("canonical spreadsheet", active_text)
        self.assertNotIn("browser", verification_text)
        self.assertNotIn("screenshot", verification_text)

    def test_runtime_next_activates_contextual_packet_deltas(self) -> None:
        result = self.server._call_tool(
            "tmcp_runtime_next",
            {
                "objective": "fix the dashboard UI bug",
                "project_path": "/tmp/project",
                "current_phase": "final",
                "previous_packet_id": "packet-old",
                "files_changed": ["app/page.tsx", "app/styles.css"],
                "failures": ["vitest failed"],
                "browser_evidence": ["screenshot shows overlap"],
                "latest_user_message": "actually verify it before final",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-runtime-next-v0.1")
        self.assertEqual(result["previous_packet_id"], "packet-old")
        activated = set(result["packet_delta"]["activated_atoms"])
        self.assertIn("ui-browser-verification", activated)
        self.assertIn("debugging-regression", activated)
        self.assertIn("verification-before-completion", activated)
        self.assertTrue(result["packet_delta"]["newly_required_reads"])
        self.assertIn("browser", " ".join(result["next_verification_gate"]).lower())

    def test_runtime_next_treats_pending_hosted_release_evidence_as_gap(
        self,
    ) -> None:
        result = self.server._call_tool(
            "tmcp_runtime_next",
            {
                "objective": "Improve TMCP release readiness before release",
                "project_path": "/tmp/project",
                "current_phase": "verification",
                "failures": [
                    "python3 scripts/check_release_evidence.py . failed because hosted release evidence is pending"
                ],
                "latest_user_message": "dogfood tmcp and iterate improvements until satisfied",
                "cache_policy": "none",
            },
        )

        self.assertTrue(result["ok"])
        activated = set(result["packet_delta"]["activated_atoms"])
        next_gate = " ".join(result["next_verification_gate"]).lower()
        self.assertIn("explicit-evidence-gaps", activated)
        self.assertNotIn("debugging-regression", activated)
        self.assertIn("hosted evidence", next_gate)
        self.assertIn("release", next_gate)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_record_receipt_writes_global_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                result = self.server._call_tool(
                    "tmcp_record_receipt",
                    {
                        "packet_id": "packet-123",
                        "activated_atoms": ["ui-browser-verification"],
                        "ignored_atoms": ["release_readiness"],
                        "commands_run": ["python3 -m unittest"],
                        "verification_results": ["passed"],
                        "user_overrides": ["keep impeccable active"],
                        "outcome": "passed",
                    },
                )
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            receipt_path = Path(result["artifact_paths"]["receipt_json"])
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"], "tmcp-run-receipt-v0.1")
        self.assertEqual(receipt["packet_id"], "packet-123")
        self.assertEqual(receipt["outcome"], "passed")
        self.assertEqual(receipt["trust"], "advisory_untrusted")

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_receipt_redacts_direct_values_and_uses_a_safe_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secret = "sk-" + "S" * 40
            tmcp_home = Path(tmp) / "tmcp-home"
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                result = self.server._call_tool(
                    "tmcp_record_receipt",
                    {
                        "packet_id": secret,
                        "commands_run": [f"deploy --token {secret}"],
                        "user_overrides": [secret],
                        "outcome": secret,
                    },
                )
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            receipt_path = Path(result["artifact_paths"]["receipt_json"])
            receipt_text = receipt_path.read_text(encoding="utf-8")

        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, receipt_text)
        self.assertNotIn(secret, receipt_path.name)
        self.assertIn("[REDACTED:", receipt_text)
        self.assertGreater(result["redaction_summary"].get("openai_key", 0), 0)

    def test_global_cache_read_redacts_legacy_payload_and_skips_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            secret = "sk-" + "G" * 40
            tmcp_home = sandbox / "tmcp-home"
            cache_dir = tmcp_home / "promoted-harvests" / "safe"
            cache_dir.mkdir(parents=True)
            graph_path = cache_dir / "promotion-graph.json"
            graph_path.write_text(
                json.dumps({"schema": "legacy", "secret": secret}),
                encoding="utf-8",
            )
            outside = sandbox / "outside"
            outside.mkdir()
            (outside / "promotion-graph.json").write_text(
                json.dumps({"schema": "legacy", "secret": "EXTERNAL_ONLY"}),
                encoding="utf-8",
            )
            linked_dir = tmcp_home / "promoted-harvests" / "linked"
            try:
                linked_dir.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"Symlinks are unavailable in this environment: {exc}")
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                graphs, warnings = self.server._load_global_promoted_graphs("global")
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

        serialized = json.dumps({"graphs": graphs, "warnings": warnings})
        self.assertEqual(len(graphs), 1)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("EXTERNAL_ONLY", serialized)
        self.assertIn("[REDACTED:", serialized)

    def test_existing_tools_include_composed_packet_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Agent Rules\n\nUse pnpm, read before modifying, and verify UI with browser evidence.",
                encoding="utf-8",
            )

            explain = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Review dashboard UI quality",
                    "project_path": str(root),
                    "source_path": str(root),
                    "compose": True,
                },
            )
            recommend = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "objective": "Review dashboard UI quality",
                    "compose": True,
                    "min_confidence": 0.1,
                },
            )

        self.assertEqual(
            explain["composed_packet"]["schema"], "tmcp-composed-packet-v0.1"
        )
        self.assertEqual(
            recommend["composed_packet"]["schema"], "tmcp-composed-packet-v0.1"
        )
