from __future__ import annotations

import unittest

from tmcp_runtime.domain import review_evidence, review_results
from tmcp_runtime.domain.standalone_packets import TMCP_PACKET_SCHEMA


class ReviewPolicyDomainTests(unittest.TestCase):
    def _packet(self) -> dict[str, object]:
        return {
            "schema": TMCP_PACKET_SCHEMA,
            "task_id": "audit",
            "selected_nodes": ["@task:audit"],
            "behavior_atoms": ["evidence-backed-claims"],
            "skipped_nodes": [],
            "substance_check": {
                "has_domain_playbook": True,
                "issues": [],
                "level": "source_backed_playbook",
            },
        }

    def test_parse_evidence_accepts_supported_shapes(self) -> None:
        item = {
            "dimension_id": "risk_priority",
            "severity": "warning",
            "summary": "A warning.",
            "evidence": ["tests: passed"],
        }

        self.assertEqual(review_evidence.parse_evidence(None), [])
        self.assertEqual(review_evidence.parse_evidence(item), [item])
        self.assertEqual(review_evidence.parse_evidence([item]), [item])
        with self.assertRaisesRegex(ValueError, "JSON object or array"):
            review_evidence.parse_evidence('["not an object"]')

    def test_evidence_to_remediation_pipeline_preserves_contracts(self) -> None:
        rubric = review_evidence.synthesize_rubric(
            self._packet(),
            "run-review",
            "Use the TMCP expert UI rubric on the product dashboard.",
        )

        self.assertEqual(rubric["profile"], "visual_polish")
        self.assertEqual(rubric["selected_nodes"], ["@task:audit"])
        self.assertEqual(
            review_evidence.evidence_contract(rubric)["starter_template"][0][
                "dimension_id"
            ],
            "surface_hierarchy",
        )

        invalid_diagnostics = review_evidence.evidence_diagnostics(
            rubric, [{"kind": "checks", "pytest": "passed"}]
        )
        self.assertFalse(invalid_diagnostics["actionable"])
        self.assertEqual(
            review_evidence.evidence_remediation_contract(rubric, invalid_diagnostics)[
                "status"
            ],
            "invalid_evidence_json",
        )

        evidence_items = [
            {
                "dimension_id": "surface_hierarchy",
                "severity": "warning",
                "summary": "Typography and layout hierarchy obscure the primary workflow.",
                "evidence": ["src/app/dashboard.tsx"],
                "recommended_fix": "Give the primary workflow a clear visual hierarchy.",
            },
            {
                "dimension_id": "product_evidence",
                "severity": "blocker",
                "summary": "The product decision workflow remains hidden behind a loading state.",
                "evidence": ["Browser inspection: loading state after 12 seconds."],
                "recommended_fix": "Resolve the state to useful product evidence or an error.",
            },
        ]
        diagnostics = review_evidence.evidence_diagnostics(rubric, evidence_items)
        actionable = review_evidence.actionable_evidence_items(rubric, evidence_items)
        audit = review_evidence.build_audit_report(rubric, actionable, "run-review")
        plan = review_results.build_remediation_plan(audit, "run-review")
        handoff = review_results.build_implementation_handoff(
            plan, "run-review", "slice-2"
        )
        validations = {
            item["validation_key"]: item
            for item in review_results.review_validations(
                self._packet(), rubric, audit, plan, diagnostics
            )
        }

        self.assertTrue(diagnostics["actionable"])
        self.assertEqual(audit["findings"][0]["severity"], "blocker")
        self.assertEqual(audit["findings"][0]["dimension_id"], "product_evidence")
        self.assertTrue(audit["coverage_gaps"])
        self.assertEqual(
            plan["slices"][0]["source_findings"], ["finding-product_evidence-2"]
        )
        self.assertEqual(handoff["selected_slice_id"], "slice-2")
        self.assertTrue(validations["evidence_json_actionable"]["passed"])
        self.assertFalse(validations["profile_evidence_coverage"]["passed"])
        self.assertIn("# Expert Rubric:", review_results.render_rubric_markdown(rubric))
        self.assertIn("## Findings", review_results.render_audit_markdown(audit))
        self.assertTrue(
            review_results.render_remediation_plan_markdown(plan).endswith("\n")
        )


if __name__ == "__main__":
    unittest.main()
