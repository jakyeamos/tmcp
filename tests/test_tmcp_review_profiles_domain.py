from __future__ import annotations

import unittest

from tmcp_runtime.domain import review_profiles


class ReviewProfilesDomainTests(unittest.TestCase):
    def test_selection_preserves_profile_precedence(self) -> None:
        cases = (
            (
                "Audit a UI privacy dashboard",
                {"task_id": "audit", "selected_nodes": [], "behavior_atoms": []},
                "visual_polish",
            ),
            (
                "Review government legal calculation readiness",
                {"task_id": "audit", "selected_nodes": [], "behavior_atoms": []},
                "public_sector_readiness",
            ),
            (
                "Inspect permission boundaries and privacy retention",
                {"task_id": "audit", "selected_nodes": [], "behavior_atoms": []},
                "security_privacy",
            ),
            (
                "Improve developer onboarding CLI commands",
                {"task_id": "audit", "selected_nodes": [], "behavior_atoms": []},
                "developer_experience",
            ),
            (
                "Review the release evidence",
                {"task_id": "audit", "selected_nodes": [], "behavior_atoms": []},
                "general_review",
            ),
        )

        for objective, packet, expected in cases:
            with self.subTest(objective=objective):
                self.assertEqual(
                    review_profiles.select_review_profile(objective, packet), expected
                )

    def test_catalog_preserves_dimension_and_coverage_contracts(self) -> None:
        self.assertEqual(
            [item["id"] for item in review_profiles.profile_dimensions("general_review")],
            [
                "source_grounding",
                "risk_priority",
                "verification_readiness",
                "scope_control",
            ],
        )
        self.assertEqual(
            review_profiles.profile_dimensions("unknown"),
            review_profiles.profile_dimensions("general_review"),
        )
        self.assertEqual(
            review_profiles.PROFILE_COVERAGE_REQUIREMENTS["visual_polish"][0]["id"],
            "visual_product_quality",
        )


if __name__ == "__main__":
    unittest.main()
