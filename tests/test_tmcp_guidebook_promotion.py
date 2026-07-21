from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.schema_contract_support import assert_matches_schema
from scripts.promote_guidebook_from_campaign import build_candidate_from_paths
from tests.test_tmcp_composition_lift_campaign_results import _campaign, _results
from tmcp_runtime.domain.composition_lift_campaign_results import (
    validate_campaign_host_results,
)
from tmcp_runtime.domain.composition_lift_campaign_scoring import (
    score_composition_lift_campaign,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.guidebook_promotion import (
    build_guidebook_promotion_candidate,
    score_rejudge,
    validate_independent_rejudge,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


def _trusted_inputs() -> tuple[
    dict[str, object], dict[str, object], dict[str, object], dict[str, object]
]:
    campaign = _campaign()
    host, evaluator = _results(campaign)
    host["evidence_class"] = "host_executed"
    evaluator["evaluator_execution"] = {
        "execution_class": "trusted_evaluator_execution",
        "executor_id": "primary-evaluator",
        "execution_id": "primary-execution",
        "executed_at": "2026-07-19T00:00:00Z",
    }
    rejudge = copy.deepcopy(evaluator)
    rejudge["evaluator_execution"] = {
        "execution_class": "trusted_evaluator_execution",
        "executor_id": "independent-evaluator",
        "execution_id": "rejudge-execution",
        "executed_at": "2026-07-20T00:00:00Z",
    }
    for block in rejudge["blocks"]:
        for cell in block["cells"]:
            evidence_id = f"rejudge-{cell['cell_id']}"
            cell["evidence"][0]["evidence_id"] = evidence_id
            cell["evidence"][0]["content"] = "independent judge evidence"
            for bindings in cell["dimension_evidence"].values():
                for binding in bindings:
                    binding["evidence_ids"] = [evidence_id]
    envelope = {
        "schema": "tmcp-composition-lift-rejudge-envelope-v0.1",
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": campaign["campaign_digest"],
        "primary_evaluator_digest": stable_digest(evaluator),
        "independence": {
            "mode": "independent_rejudge",
            "executor_id": "independent-evaluator",
            "execution_id": "rejudge-execution",
            "primary_execution_id": "primary-execution",
            "method": "Blind second pass over the same opaque artifact slots.",
        },
        "artifacts": rejudge,
    }
    return campaign, host, evaluator, envelope


class GuidebookPromotionTests(unittest.TestCase):
    def test_independent_rejudge_is_cell_bound_and_produces_manual_candidate(
        self,
    ) -> None:
        campaign, host, evaluator, envelope = _trusted_inputs()
        host_cells = validate_campaign_host_results(campaign, host)
        primary_summary = score_composition_lift_campaign(campaign, host, evaluator)
        rejudge_result = validate_independent_rejudge(
            campaign, host_cells, evaluator, envelope
        )
        rejudge_summary = score_rejudge(campaign, host, envelope["artifacts"])
        catalog = json.loads(
            (ROOT / "docs/SKILL_PATTERN_CATALOG.json").read_text(encoding="utf-8")
        )
        candidate = build_guidebook_promotion_candidate(
            campaign=campaign,
            summary=primary_summary,
            rejudge_summary=rejudge_summary,
            primary_evaluator=evaluator,
            rejudge_envelope=envelope,
            pattern_ids=["verification.concrete-command"],
            catalog=catalog,
            agreement=rejudge_result["agreement"],
        )

        assert_matches_schema(
            candidate, SCHEMAS / "tmcp-guidebook-promotion-candidate-v0.1.schema.json"
        )
        self.assertEqual(candidate["decision"], "eligible_for_manual_review")
        self.assertFalse(candidate["promotion_policy"]["auto_apply"])
        self.assertEqual(candidate["evidence"]["agreement"]["cell_count"], 540)

    def test_rejudge_must_use_a_distinct_executor_and_execution(self) -> None:
        campaign, host, evaluator, envelope = _trusted_inputs()
        envelope["independence"]["executor_id"] = "primary-evaluator"
        host_cells = validate_campaign_host_results(campaign, host)

        with self.assertRaisesRegex(ValueError, "executor_id"):
            validate_independent_rejudge(campaign, host_cells, evaluator, envelope)

    def test_promotion_candidate_rejects_ineligible_summary(self) -> None:
        campaign, host, evaluator, envelope = _trusted_inputs()
        host_cells = validate_campaign_host_results(campaign, host)
        rejudge_result = validate_independent_rejudge(
            campaign, host_cells, evaluator, envelope
        )
        summary = score_composition_lift_campaign(campaign, host, evaluator)
        summary["eligible"] = False
        rejudge_summary = score_rejudge(campaign, host, envelope["artifacts"])
        catalog = json.loads(
            (ROOT / "docs/SKILL_PATTERN_CATALOG.json").read_text(encoding="utf-8")
        )

        with self.assertRaisesRegex(ValueError, "primary composition summary"):
            build_guidebook_promotion_candidate(
                campaign=campaign,
                summary=summary,
                rejudge_summary=rejudge_summary,
                primary_evaluator=evaluator,
                rejudge_envelope=envelope,
                pattern_ids=["verification.concrete-command"],
                catalog=catalog,
                agreement=rejudge_result["agreement"],
            )

    def test_cli_builder_validates_raw_files_without_mutating_catalog(self) -> None:
        campaign, host, evaluator, envelope = _trusted_inputs()
        summary = score_composition_lift_campaign(campaign, host, evaluator)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {
                "campaign": root / "campaign.json",
                "host": root / "host.json",
                "evaluator": root / "evaluator.json",
                "summary": root / "summary.json",
                "rejudge": root / "rejudge.json",
            }
            payloads = {
                "campaign": campaign,
                "host": host,
                "evaluator": evaluator,
                "summary": summary,
                "rejudge": envelope,
            }
            for key, path in paths.items():
                path.write_text(json.dumps(payloads[key]), encoding="utf-8")
            candidate = build_candidate_from_paths(
                campaign_path=paths["campaign"],
                host_results_path=paths["host"],
                primary_evaluator_path=paths["evaluator"],
                summary_path=paths["summary"],
                rejudge_path=paths["rejudge"],
                catalog_path=ROOT / "docs/SKILL_PATTERN_CATALOG.json",
                pattern_ids=["verification.concrete-command"],
            )

        self.assertEqual(candidate["decision"], "eligible_for_manual_review")


if __name__ == "__main__":
    unittest.main()
