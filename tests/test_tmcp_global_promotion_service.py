from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from typing import Any

import tmcp_runtime.services.global_promotion as global_promotion_service
from tmcp_runtime.services.artifact_plans import ArtifactPlan
from tmcp_runtime.services.global_promotion import (
    GlobalPromotionArtifactService,
    GlobalPromotionContext,
)


class GlobalPromotionArtifactServiceTests(unittest.TestCase):
    def test_build_redacts_graph_summary_and_optional_pack_before_plan(self) -> None:
        redaction_calls: list[dict[str, Any]] = []
        plan_inputs: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]] = []

        def redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
            redaction_calls.append(value)
            safe_value = {**value, "safe": True}
            if "secret" in safe_value:
                safe_value["secret"] = "[REDACTED]"
            return safe_value

        def build_plan(
            summary: dict[str, Any],
            graph: dict[str, Any],
            adaptive_pack: dict[str, Any] | None,
        ) -> ArtifactPlan:
            plan_inputs.append((summary, graph, adaptive_pack))
            return ArtifactPlan(
                json_artifacts={"summary.json": summary, "graph.json": graph},
                text_artifacts={},
                path_aliases={"summary": "summary.json", "graph": "graph.json"},
            )

        service = GlobalPromotionArtifactService(
            GlobalPromotionContext(
                normalize_graph=lambda result, created_at: {
                    "created_at": created_at,
                    "secret": result["secret"],
                },
                redact_mapping=redact_mapping,
                build_artifact_plan=build_plan,
                now_iso=lambda: "2026-07-13T12:00:00Z",
            )
        )

        plan = service.build(
            {
                "secret": "untrusted-source",
                "promoted_workflow_ids": ["release_readiness_workflow", 2],
                "promoted_scoped_packet_seed_ids": None,
                "adaptive_workflow_pack": {"secret": "untrusted-pack"},
            },
            "release",
        )

        self.assertIsInstance(plan, ArtifactPlan)
        self.assertEqual(len(redaction_calls), 3)
        self.assertEqual(plan_inputs[0][0]["promotion_name"], "release")
        self.assertEqual(
            plan_inputs[0][0]["promoted_workflow_ids"],
            ["release_readiness_workflow", "2"],
        )
        self.assertEqual(plan_inputs[0][1]["created_at"], "2026-07-13T12:00:00Z")
        self.assertTrue(plan_inputs[0][2]["safe"])
        self.assertNotIn("untrusted-source", repr(plan_inputs[0][1]))
        self.assertNotIn("untrusted-pack", repr(plan_inputs[0][2]))

    def test_missing_optional_pack_is_not_injected(self) -> None:
        captured: list[dict[str, Any] | None] = []
        service = GlobalPromotionArtifactService(
            GlobalPromotionContext(
                normalize_graph=lambda _result, _created_at: {},
                redact_mapping=lambda value: value,
                build_artifact_plan=lambda _summary, _graph, adaptive_pack: (
                    captured.append(adaptive_pack)
                    or ArtifactPlan({}, {}, {})
                ),
                now_iso=lambda: "now",
            )
        )

        service.build({"adaptive_workflow_pack": "not-an-object"}, "release")

        self.assertEqual(captured, [None])

    def test_service_has_no_storage_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(global_promotion_service))
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
