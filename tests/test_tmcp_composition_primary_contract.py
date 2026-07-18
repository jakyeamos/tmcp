"""Primary-campaign verification contracts for source-bundle studies."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import scripts.tmcp_skill_eval_cost_rejudge_source as cost_rejudge_source
from scripts.tmcp_skill_eval_campaign_protocol import (
    _sha256_text,
    judge_output_schema,
    judge_prompt,
)


class CompositionPrimaryContractTests(unittest.TestCase):
    def test_source_bundle_campaign_contract_requires_all_primary_preflight_gates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary)
            roles = [
                {
                    "role": "runner",
                    "configuration_id": "runner-a-reasoning-high",
                    "model": "runner-a",
                    "effort": "high",
                },
                {
                    "role": "judge",
                    "configuration_id": "independent-judge",
                    "model": "judge-a",
                    "effort": "high",
                },
            ]
            audit = {"passed": True, "prompt_context_sha256": "sha256:context"}
            input_digests = {"study.json": "sha256:study"}
            selected_sources = [{"path": "/skill/SKILL.md", "sha256": "sha256:skill"}]
            manifest = {
                "experiment_id": "composition-study-test",
                "cell_count": 2,
                "runner_configurations": [
                    {"model": "runner-a", "reasoning_effort": "high"}
                ],
                "judge_model": "judge-a",
                "judge_effort": "high",
                "isolation": {
                    "ephemeral_process_per_role": True,
                    "temporary_codex_home_per_role": True,
                    "skills_include_instructions": False,
                    "event_stream_audited": True,
                    "sandbox": "read-only",
                    "remote_schema_preflight_required": True,
                    "remote_schema_preflight_roles": roles,
                    "prompt_input_preflight": audit,
                },
                "composition_study_verification": {
                    "schema": "tmcp-composition-study-verification-v0.1",
                    "experiment_id": "composition-study-test",
                    "static": {
                        "plan_matches_generated": True,
                        "plan_valid": True,
                        "fixture_count": 1,
                        "matrix_row_count": 2,
                        "claim_boundary": "source-bundle delivery only",
                        "input_digests": input_digests,
                    },
                    "live_sources": {
                        "status": "matched",
                        "sources": [
                            {
                                "path": "/skill/SKILL.md",
                                "status": "matched",
                                "expected_sha256": "sha256:skill",
                                "actual_sha256": "sha256:skill",
                            }
                        ],
                    },
                },
            }
            plan = {
                "experiment": {
                    "study_scope": {
                        "claim_boundary": "source-bundle delivery only"
                    },
                    "source_study_binding": {
                        "schema": "tmcp-composition-study-binding-v0.1",
                        "input_digests": input_digests,
                        "selected_sources": selected_sources,
                    },
                },
                "task_matrix": [
                    {
                        "pattern_id": "composition.source-bundle-inclusion",
                        "task_id": "fixture-1",
                    },
                    {
                        "pattern_id": "composition.source-bundle-inclusion",
                        "task_id": "fixture-1",
                    },
                ],
            }
            (runs / "prompt-input-preflight.json").write_text(
                json.dumps({"audit": audit}), encoding="utf-8"
            )
            synthetic_criteria = ["O1: The sentence is present."]
            synthetic_schema = judge_output_schema(synthetic_criteria)
            schema_sha256 = _sha256_text(
                json.dumps(synthetic_schema, indent=2, sort_keys=True) + "\n"
            )
            prompt_sha256 = _sha256_text(
                judge_prompt(
                    {
                        "prompt": "State whether the supplied sentence is present.",
                        "expected_observables": ["The sentence is present."],
                        "failure_smells": [],
                    },
                    "The sentence is present.",
                    first_principles="Use only the supplied sentence.",
                )
            )
            preflights = [
                {
                    **role,
                    "schema": "tmcp-remote-schema-preflight-v0.1",
                    "passed": True,
                    "output_schema_sha256": schema_sha256,
                    "prompt_sha256": prompt_sha256,
                    "output_sha256": "sha256:" + "a" * 64,
                    "event_stream_sha256": "sha256:" + "b" * 64,
                    "event_audit": {"passed": True, "thread_id": role["role"]},
                    "usage": {"input_tokens": 1},
                    "retry_audit": {"attempts": [], "successful_attempt": 1},
                }
                for role in roles
            ]
            remote_preflight = {
                "schema": "tmcp-remote-schema-preflights-v0.1",
                "passed": True,
                "preflights": preflights,
            }
            (runs / "remote-schema-preflight.json").write_text(
                json.dumps(remote_preflight),
                encoding="utf-8",
            )
            (runs / "campaign-summary.json").write_text(
                json.dumps(
                    {
                        "planned_cells": 2,
                        "selected_cells": 2,
                        "completed_cells": 2,
                        "errors": 0,
                        "unique_thread_ids": 4,
                        "expected_thread_ids_at_completion": 4,
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(
                cost_rejudge_source._verify_source_bundle_campaign_contract(
                    plan=plan,
                    manifest=manifest,
                    source_runs=runs,
                    expected_trace_count=2,
                )
            )
            remote_preflight["preflights"][0]["prompt_sha256"] = "sha256:wrong"
            (runs / "remote-schema-preflight.json").write_text(
                json.dumps(remote_preflight), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "preflight contract"):
                cost_rejudge_source._verify_source_bundle_campaign_contract(
                    plan=plan,
                    manifest=manifest,
                    source_runs=runs,
                    expected_trace_count=2,
                )
            remote_preflight["preflights"][0]["prompt_sha256"] = prompt_sha256
            remote_preflight["preflights"][0]["output_sha256"] = "sha256:short"
            (runs / "remote-schema-preflight.json").write_text(
                json.dumps(remote_preflight), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "preflight contract"):
                cost_rejudge_source._verify_source_bundle_campaign_contract(
                    plan=plan,
                    manifest=manifest,
                    source_runs=runs,
                    expected_trace_count=2,
                )
            remote_preflight["preflights"][0]["output_sha256"] = "sha256:" + "a" * 64
            manifest["composition_study_verification"]["static"][
                "input_digests"
            ] = {"study.json": "sha256:other-study"}
            (runs / "remote-schema-preflight.json").write_text(
                json.dumps(remote_preflight), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "immutable-input"):
                cost_rejudge_source._verify_source_bundle_campaign_contract(
                    plan=plan,
                    manifest=manifest,
                    source_runs=runs,
                    expected_trace_count=2,
                )
            manifest["composition_study_verification"]["static"][
                "input_digests"
            ] = input_digests
            manifest["composition_study_verification"]["live_sources"]["sources"][0][
                "expected_sha256"
            ] = "sha256:other-skill"
            manifest["composition_study_verification"]["live_sources"]["sources"][0][
                "actual_sha256"
            ] = "sha256:other-skill"
            with self.assertRaisesRegex(ValueError, "immutable-input"):
                cost_rejudge_source._verify_source_bundle_campaign_contract(
                    plan=plan,
                    manifest=manifest,
                    source_runs=runs,
                    expected_trace_count=2,
                )
            (runs / "remote-schema-preflight.json").unlink()
            with self.assertRaisesRegex(ValueError, "remote-schema preflight"):
                cost_rejudge_source._verify_source_bundle_campaign_contract(
                    plan=plan,
                    manifest=manifest,
                    source_runs=runs,
                    expected_trace_count=2,
                )


if __name__ == "__main__":
    unittest.main()
