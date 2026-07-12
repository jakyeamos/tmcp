from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tmcp_runtime.services.review import build_review_plan


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = PLUGIN_ROOT / "tmcp_runtime" / "services" / "review.py"


def _build(evidence_items: list[dict[str, object]]) -> dict[str, object]:
    return build_review_plan(
        objective="Review release evidence.",
        project_path="/tmp/project",
        run_id="review-fixed",
        evidence_items=evidence_items,
        harvested_nodes=[],
        harvest_warnings=[],
        selected_slice_id=None,
    )


class ReviewServiceTests(unittest.TestCase):
    def test_empty_evidence_returns_a_deterministic_evidence_request(self) -> None:
        result = _build([])

        self.assertTrue(result["ok"])
        self.assertEqual(result["run_id"], "review-fixed")
        self.assertEqual(result["status"], "needs_evidence")
        self.assertTrue(result["evidence_remediation_contract"])
        self.assertEqual(result["artifact_paths"], {})

    def test_invalid_evidence_fails_the_contract_without_persistence(self) -> None:
        result = _build([{"kind": "checks"}])

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed_evidence_contract")
        self.assertTrue(result["evidence_diagnostics"]["item_issues"])
        self.assertEqual(result["artifact_paths"], {})

    def test_dimension_mapped_evidence_is_actionable(self) -> None:
        empty_result = _build([])
        dimension_id = empty_result["evidence_contract"]["dimension_ids"][0]

        result = _build(
            [
                {
                    "dimension_id": dimension_id,
                    "severity": "warning",
                    "summary": "Release evidence is incomplete.",
                    "evidence": ["docs/release.md"],
                }
            ]
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["evidence_diagnostics"]["item_issues"])

    def test_service_has_no_adapter_or_persistence_import(self) -> None:
        module = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
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
                or "redaction" in module_name
                for module_name in imported_modules
            )
        )


if __name__ == "__main__":
    unittest.main()
