from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.artifact_plans as artifact_plans
from tmcp_runtime.services.artifact_plans import (
    ArtifactPlan,
    build_evaluation_artifact_plan,
    build_global_promotion_artifact_plan,
    build_promotion_artifact_plan,
    build_review_artifact_plan,
    build_workflow_recommendation_artifact_plan,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = PLUGIN_ROOT / "scripts" / "tmcp_mcp_server.py"


class ArtifactPlanServiceTests(unittest.TestCase):
    def test_evaluation_plan_has_expected_manifests_and_renderer_boundary(self) -> None:
        evaluation_plan: dict[str, object] = {"schema": "plan"}
        evaluation_report: dict[str, object] = {
            "schema": "report",
            "guidebook_entries": [{"title": "Example"}],
        }

        artifact_plan = build_evaluation_artifact_plan(
            plan=evaluation_plan,
            report=evaluation_report,
            guidebook_markdown=lambda entries: f"guidebook:{len(entries)}",
            pattern_catalog=lambda entries: {"patterns": entries},
        )

        self.assertEqual(
            set(artifact_plan.json_artifacts),
            {
                "tmcp-skill-evaluation-plan.json",
                "tmcp-skill-evaluation-report.json",
                "skill-pattern-catalog.json",
            },
        )
        self.assertEqual(
            artifact_plan.text_artifacts,
            {"skill-writing-guidebook.md": "guidebook:1"},
        )
        self.assertEqual(
            artifact_plan.path_aliases,
            {
                "evaluation_plan": "tmcp-skill-evaluation-plan.json",
                "evaluation_report": "tmcp-skill-evaluation-report.json",
                "pattern_catalog": "skill-pattern-catalog.json",
                "guidebook": "skill-writing-guidebook.md",
            },
        )

    def test_evaluation_plan_rejects_malformed_guidebook_entries(self) -> None:
        with self.assertRaises(ValueError):
            build_evaluation_artifact_plan(
                plan=None,
                report={"guidebook_entries": ["not-an-object"]},
                guidebook_markdown=lambda entries: "",
                pattern_catalog=lambda entries: {},
            )

    def test_review_plan_has_exact_manifests_aliases_and_no_input_mutation(self) -> None:
        expertise_packet: dict[str, object] = {"packet_id": "packet-123"}
        rubric: dict[str, object] = {
            "objective": "Review the artifact boundary.",
            "profile": "architecture",
            "dimensions": [],
        }
        audit_report: dict[str, object] = {
            "run_id": "review-123",
            "scores": [],
            "findings": [],
        }
        remediation_plan: dict[str, object] = {
            "run_id": "review-123",
            "slices": [],
        }
        implementation_handoff: dict[str, object] = {"handoff_id": "handoff-123"}
        original_inputs = copy.deepcopy(
            {
                "expertise_packet": expertise_packet,
                "rubric": rubric,
                "audit_report": audit_report,
                "remediation_plan": remediation_plan,
                "implementation_handoff": implementation_handoff,
            }
        )

        plan = build_review_artifact_plan(
            expertise_packet=expertise_packet,
            rubric=rubric,
            audit_report=audit_report,
            remediation_plan=remediation_plan,
            implementation_handoff=implementation_handoff,
        )

        self.assertIsInstance(plan, ArtifactPlan)
        self.assertEqual(
            set(plan.json_artifacts),
            {
                "expertise-packet.json",
                "rubric.json",
                "audit-report.json",
                "remediation-plan.json",
                "implementation-handoff.json",
            },
        )
        self.assertEqual(
            set(plan.text_artifacts),
            {"rubric.md", "audit-report.md", "remediation-plan.md"},
        )
        self.assertEqual(
            plan.path_aliases,
            {
                "expertise_packet": "expertise-packet.json",
                "rubric_json": "rubric.json",
                "rubric_markdown": "rubric.md",
                "audit_report_json": "audit-report.json",
                "audit_report_markdown": "audit-report.md",
                "remediation_plan_json": "remediation-plan.json",
                "remediation_plan_markdown": "remediation-plan.md",
                "implementation_handoff_json": "implementation-handoff.json",
            },
        )
        self.assertIn("# Expert Rubric: Review the artifact boundary.", plan.text_artifacts["rubric.md"])
        self.assertEqual(
            {
                "expertise_packet": expertise_packet,
                "rubric": rubric,
                "audit_report": audit_report,
                "remediation_plan": remediation_plan,
                "implementation_handoff": implementation_handoff,
            },
            original_inputs,
        )

    def test_recommendation_and_promotion_plans_add_optional_artifacts(self) -> None:
        recommendation: dict[str, object] = {
            "priority_profile": {"primary_signals": ["release"]},
            "recommended_workflows": [],
            "recommended_scoped_packet_seeds": [],
            "custom_workflow_ideas": [],
            "not_recommended": [],
            "adaptive_workflow_pack": {"schema": "tmcp-adaptive-workflow-pack-v0.1"},
        }
        promotion: dict[str, object] = {
            "promotion_name": "release",
            "status": "promoted",
            "source_harvest": {"source_count": 1},
            "promoted_workflow_ids": ["release_readiness_workflow"],
            "promoted_scoped_packet_seed_ids": [],
            "promotion_graph": {
                "source_nodes": [],
                "scoped_packet_seed_nodes": [],
                "behavior_atoms": [],
                "edges": [],
            },
            "promotion_policy": [],
            "adaptive_workflow_pack": {"schema": "tmcp-adaptive-workflow-pack-v0.1"},
        }
        original_recommendation = copy.deepcopy(recommendation)
        original_promotion = copy.deepcopy(promotion)

        recommendation_plan = build_workflow_recommendation_artifact_plan(
            recommendation
        )
        promotion_plan = build_promotion_artifact_plan(promotion)

        self.assertEqual(
            set(recommendation_plan.json_artifacts),
            {
                "workflow-recommendations.json",
                "priority-profile.json",
                "adaptive-workflow-pack.json",
            },
        )
        self.assertEqual(
            recommendation_plan.path_aliases["priority_profile_json"],
            "priority-profile.json",
        )
        self.assertEqual(
            recommendation_plan.path_aliases["adaptive_pack_json"],
            "adaptive-workflow-pack.json",
        )
        self.assertIn(
            "# TMCP Workflow Recommendations",
            recommendation_plan.text_artifacts["workflow-recommendations.md"],
        )
        self.assertEqual(
            set(promotion_plan.json_artifacts),
            {
                "promoted-harvest.json",
                "promotion-graph.json",
                "adaptive-workflow-pack.json",
            },
        )
        self.assertEqual(
            promotion_plan.path_aliases["promotion_graph_json"],
            "promotion-graph.json",
        )
        self.assertEqual(
            promotion_plan.path_aliases["adaptive_pack_json"],
            "adaptive-workflow-pack.json",
        )
        self.assertIn(
            "# TMCP Harvest Promotion: release",
            promotion_plan.text_artifacts["promoted-harvest.md"],
        )
        self.assertEqual(recommendation, original_recommendation)
        self.assertEqual(promotion, original_promotion)

    def test_global_promotion_plan_only_adds_the_optional_pack_when_present(self) -> None:
        summary: dict[str, object] = {"promotion_name": "release"}
        graph: dict[str, object] = {"schema": "tmcp-promoted-harvest-graph-v0.1"}

        without_pack = build_global_promotion_artifact_plan(
            promotion_summary=summary,
            promotion_graph=graph,
            adaptive_workflow_pack=None,
        )
        with_pack = build_global_promotion_artifact_plan(
            promotion_summary=summary,
            promotion_graph=graph,
            adaptive_workflow_pack={"schema": "tmcp-adaptive-workflow-pack-v0.1"},
        )

        self.assertEqual(
            without_pack.path_aliases,
            {
                "promotion_json": "promoted-harvest.json",
                "promotion_graph_json": "promotion-graph.json",
            },
        )
        self.assertNotIn("adaptive-workflow-pack.json", without_pack.json_artifacts)
        self.assertEqual(
            with_pack.path_aliases["adaptive_pack_json"],
            "adaptive-workflow-pack.json",
        )

    def test_artifact_plan_service_has_no_adapter_storage_or_io_imports(self) -> None:
        source_path = Path(inspect.getfile(artifact_plans))
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
            "hashlib",
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

    def test_adapter_keeps_markdown_rendering_in_the_pure_plan_service(self) -> None:
        tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        forbidden_modules = {
            "tmcp_runtime.domain.review_results",
            "tmcp_runtime.domain.workflow_adaptive",
            "tmcp_runtime.domain.workflow_promotion",
        }

        self.assertTrue(forbidden_modules.isdisjoint(imported_modules))


if __name__ == "__main__":
    unittest.main()
