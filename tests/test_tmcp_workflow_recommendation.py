from __future__ import annotations

import importlib.util
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers


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
        self.assertTrue(result["recommended_workflows"][0]["evidence"])
        self.assertIn("starter_prompt", result["recommended_workflows"][0])

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
            self.assertTrue(pack["harvested_source_map"])
            self.assertTrue(pack["operating_profile"]["source_scope_counts"])
            self.assertTrue(pack["strongest_behavior_signals"])
            self.assertTrue(pack["recommended_default_templates"])
            self.assertTrue(pack["generated_custom_workflow_ideas"])
            self.assertEqual(
                result["custom_workflow_ideas"],
                pack["generated_custom_workflow_ideas"],
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
        self.assertEqual(result["not_recommended"], [])

    def test_release_package_check_smokes_adaptive_surface(self) -> None:
        path = helpers.PLUGIN_ROOT / "scripts" / "check_release_package.py"
        spec = importlib.util.spec_from_file_location("check_release_package", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load check_release_package module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            ok, output = module.check_adaptive_workflow_surface(
                helpers.PLUGIN_ROOT, Path(tmp)
            )

        self.assertTrue(ok, output)

    def test_release_package_excludes_local_artifact_directories(self) -> None:
        path = helpers.PLUGIN_ROOT / "scripts" / "check_release_package.py"
        spec = importlib.util.spec_from_file_location("check_release_package", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load check_release_package module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text("", encoding="utf-8")
            aios_audit = root / ".aios" / "audit"
            aios_audit.mkdir(parents=True)
            (aios_audit / "gate-events.jsonl").write_text("", encoding="utf-8")
            quality_run = root / ".quality-runner" / "runs" / "local"
            quality_run.mkdir(parents=True)
            (quality_run / "audit.json").write_text("{}", encoding="utf-8")
            output_path = Path(tmp) / "tmcp.tar.gz"

            module.create_package(root, output_path)

            with tarfile.open(output_path, "r:gz") as archive:
                names = archive.getnames()

        self.assertIn("tmcp/README.md", names)
        self.assertNotIn("tmcp/.aios/audit/gate-events.jsonl", names)
        self.assertNotIn("tmcp/.codex/config.toml", names)
        self.assertNotIn("tmcp/.quality-runner/runs/local/audit.json", names)
