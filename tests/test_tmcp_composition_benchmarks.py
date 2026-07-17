from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import tmcp_runtime.domain.composition_benchmarks as composition_benchmarks
import tmcp_runtime.domain.composition_benchmark_contracts as benchmark_contracts
import tmcp_runtime.domain.composition_benchmark_evaluator as benchmark_evaluator
import tmcp_runtime.domain.composition_benchmark_manifests as benchmark_manifests
import tmcp_runtime.domain.composition_benchmark_sources as benchmark_sources
from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.domain.composition_benchmarks import (
    score_behavioral_benchmark,
    score_composition_benchmark,
    score_routing_benchmark,
)
from tmcp_runtime.domain.composition_benchmark_receipt_projection import (
    build_benchmark_receipt_provenance,
)
from tmcp_runtime.domain.composition_benchmark_sources import (
    graph_digest_for_observation,
)
from tmcp_runtime.domain.composition_benchmark_manifests import (
    behavioral_input_digest,
    evidence_record_digest,
    execution_record_digest,
    execution_result_digest,
    required_behavioral_variants,
    routing_input_digest,
    variant_quality_score,
    variant_skill_order,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import content_digest_for
from scripts.run_composition_benchmark import run_benchmark


FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
ROUTING_GOLDEN = FIXTURES / "composition_routing_golden_v0_6.json"
BEHAVIORAL_FIXTURES = FIXTURES / "composition_behavioral_fixtures_v0_6.json"


def _payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class CompositionBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.golden_cases = _payload(ROUTING_GOLDEN)["cases"]
        cls.fixture_definitions = _payload(BEHAVIORAL_FIXTURES)["fixtures"]

    def _routing_results(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for case in self.golden_cases:
            selected = list(case["expected_skill_ids"])
            result = {
                "case_id": case["case_id"],
                "selected_skill_ids": selected,
            }
            execution, evidence = self._execution_evidence(
                subject_id=case["case_id"],
                variant_id="routing",
                input_digest=routing_input_digest(case),
                artifact=json.dumps(result, sort_keys=True),
                result_digest=stable_digest({"selected_skill_ids": selected}),
            )
            result["execution_manifest"] = [execution]
            result["evidence_manifest"] = [evidence]
            results.append(result)
        results[0]["selected_skill_ids"].append("unrelated-skill")
        results[0]["execution_manifest"], results[0]["evidence_manifest"] = (
            self._routing_manifests(self.golden_cases[0], results[0])
        )
        return results

    def _routing_manifests(
        self,
        case: dict[str, Any],
        result: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        execution, evidence = self._execution_evidence(
            subject_id=case["case_id"],
            variant_id="routing",
            input_digest=routing_input_digest(case),
            artifact=json.dumps(
                {
                    "case_id": result["case_id"],
                    "selected_skill_ids": result["selected_skill_ids"],
                },
                sort_keys=True,
            ),
            result_digest=stable_digest(
                {"selected_skill_ids": result["selected_skill_ids"]}
            ),
        )
        return [execution], [evidence]

    @staticmethod
    def _context_accounting(
        *,
        fixture_id: str,
        active_stages: list[dict[str, Any]],
        compiled_tokens: int = 700,
        naive_tokens: int = 1000,
    ) -> dict[str, Any]:
        def capsule_record(payload: dict[str, Any], tokens: int) -> dict[str, Any]:
            return {
                "capsule": payload,
                "canonical_json": json.dumps(payload, sort_keys=True),
                "capsule_digest": stable_digest(payload),
                "estimated_tokens": tokens,
            }

        phase_capsules = []
        for index, stage in enumerate(active_stages, start=1):
            skill_ids = list(stage["active_skill_ids"])
            capsule = capsule_record(
                {
                    "fixture_id": fixture_id,
                    "kind": "runtime_phase",
                    "stage_id": stage["stage_id"],
                    "skills": skill_ids,
                },
                compiled_tokens,
            )
            phase_capsules.append(
                {
                    "stage_id": str(stage["stage_id"]),
                    "stage_order": index,
                    "phase": f"phase-{index}",
                    "source_ids": skill_ids,
                    "source_skill_ids": skill_ids,
                    "source_slice_ids": [
                        "slice-" + stable_digest([fixture_id, skill_id], 20)
                        for skill_id in skill_ids
                    ],
                    "source_slice_digests": [
                        stable_digest([fixture_id, skill_id, "content"])
                        for skill_id in skill_ids
                    ],
                    "source_digests": [
                        stable_digest([fixture_id, skill_id, "source"])
                        for skill_id in skill_ids
                    ],
                    "content_digests": [
                        stable_digest([fixture_id, skill_id, "content"])
                        for skill_id in skill_ids
                    ],
                    "incoming_handoff_digests": [],
                    **capsule,
                }
            )
        preflight_capsule = capsule_record(
            {"fixture_id": fixture_id, "kind": "preflight_discovery"}, 100
        )
        naive_union_capsule = capsule_record(
            {"fixture_id": fixture_id, "kind": "naive_union"}, naive_tokens
        )
        accounting: dict[str, Any] = {
            "schema": "tmcp-composition-context-accounting-v0.1",
            "policy": "phase_capsule_runtime_peak_vs_naive_union",
            "runtime_envelope": {"fixture_id": fixture_id},
            "preflight_capsule": preflight_capsule,
            "preflight_capsule_digest": preflight_capsule["capsule_digest"],
            "preflight_discovery_tokens": preflight_capsule["estimated_tokens"],
            "phase_capsules": phase_capsules,
            "naive_union_capsule": naive_union_capsule,
            "naive_union_capsule_digest": naive_union_capsule["capsule_digest"],
            "runtime_peak_context_tokens": compiled_tokens,
            "naive_union_context_tokens": naive_tokens,
            "context_ratio": compiled_tokens / naive_tokens,
            "same_host_transcript_tokens": compiled_tokens * len(phase_capsules),
            "compiled_context_tokens": compiled_tokens,
            "naive_context_tokens": naive_tokens,
        }
        accounting["context_accounting_digest"] = stable_digest(accounting)
        accounting["context_digest"] = accounting["context_accounting_digest"]
        return accounting

    @staticmethod
    def _projected_execution_context(
        accounting: dict[str, Any],
        *,
        mode: str = "isolated_phase_capsule",
    ) -> dict[str, Any]:
        return {
            "context_execution_mode": mode,
            "context_accounting_digest": accounting["context_accounting_digest"],
            "preflight_capsule_digest": accounting["preflight_capsule_digest"],
            "phase_capsule_trace": [
                {
                    "stage_id": capsule["stage_id"],
                    "capsule_digest": capsule["capsule_digest"],
                    "incoming_handoff_digests": capsule[
                        "incoming_handoff_digests"
                    ],
                }
                for capsule in accounting["phase_capsules"]
            ],
        }

    @staticmethod
    def _refresh_benchmark_receipt_provenance(
        receipt: dict[str, Any],
        *,
        fixture_id: str,
    ) -> None:
        """Attach self-consistent safe benchmark provenance to fixture evidence."""

        composition_plan_digest = stable_digest(
            {
                "composition_plan_id": receipt["recipe_id"],
                "graph_digest": receipt["graph_digest"],
                "phase_capsule_trace": receipt["phase_capsule_trace"],
            }
        )
        receipt.update(
            {
                "composition_plan_digest": composition_plan_digest,
                "phase_capsule_binding_digest": stable_digest(
                    {
                        "composition_plan_digest": composition_plan_digest,
                        "context_accounting_digest": receipt[
                            "context_accounting_digest"
                        ],
                        "preflight_capsule_digest": receipt[
                            "preflight_capsule_digest"
                        ],
                        "phase_capsule_trace": receipt["phase_capsule_trace"],
                    }
                ),
                "composition_fixture_id": fixture_id,
                "benchmark_control_input_digest": stable_digest(
                    {"fixture_id": fixture_id, "kind": "control-input"}
                ),
                "benchmark_execution_recipe_digest": stable_digest(
                    {"fixture_id": fixture_id, "kind": "execution-recipe"}
                ),
            }
        )
        receipt.pop("benchmark_receipt_provenance", None)
        receipt["benchmark_receipt_provenance"] = build_benchmark_receipt_provenance(
            receipt,
            fixture_digest=stable_digest({"fixture_id": fixture_id}),
            control_plan_id="benchmark-control-" + stable_digest(fixture_id)[:20],
            control_plan_digest=stable_digest(
                {"fixture_id": fixture_id, "kind": "control-plan"}
            ),
            host_artifact_digest=stable_digest(
                {"fixture_id": fixture_id, "kind": "host-artifact"}
            ),
            host_receipt_digest=stable_digest(
                {"fixture_id": fixture_id, "kind": "host-receipt"}
            ),
        )

    @staticmethod
    def _execution_evidence(
        *,
        subject_id: str,
        variant_id: str,
        input_digest: str,
        artifact: str,
        result_digest: str,
        tmcp_run_receipt: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        artifact_digest = stable_digest(artifact)
        evidence: dict[str, Any] = {
            "execution_id": "pending",
            "media_type": "application/json",
            "content": f"Observed evidence for {subject_id} {variant_id}",
        }
        evidence["content_digest"] = stable_digest(evidence["content"])
        evidence["evidence_id"] = "evidence-" + evidence_record_digest(evidence)[:20]
        receipt: dict[str, Any] = {
            "run_id": f"run-{subject_id}-{variant_id}",
            "variant_id": variant_id,
            "outcome": "passed",
            "artifact_digest": artifact_digest,
        }
        if tmcp_run_receipt is not None:
            receipt["tmcp_run_receipt"] = tmcp_run_receipt
        execution: dict[str, Any] = {
            "variant_id": variant_id,
            "input_digest": input_digest,
            "artifact": artifact,
            "artifact_digest": artifact_digest,
            "result_digest": result_digest,
            "run_receipt": receipt,
            "receipt_digest": stable_digest(receipt),
            "evidence_ids": [evidence["evidence_id"]],
        }
        execution["execution_digest"] = execution_record_digest(execution)
        execution["execution_id"] = "execution-" + execution["execution_digest"][:20]
        evidence["execution_id"] = execution["execution_id"]
        return execution, evidence

    def _behavioral_results(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for fixture_index, fixture in enumerate(self.fixture_definitions, start=1):
            selected = list(fixture["expected_skill_ids"])
            source_slices = [
                self._source_slice(
                    fixture_index,
                    skill_index,
                    skill_id,
                    fixture,
                )
                for skill_index, skill_id in enumerate(selected, start=1)
            ]
            slices_by_skill = {
                item["skill_id"]: item["slice_id"] for item in source_slices
            }
            relationships = [
                {
                    **relationship,
                    "citations": [
                        slices_by_skill[relationship["source_id"]],
                        slices_by_skill[relationship["target_id"]],
                    ],
                }
                for relationship in fixture["expected_relationships"]
            ]
            variant_ids = required_behavioral_variants(selected)
            preflight_id = f"preflight-{fixture_index:020x}"
            composition_plan_id = f"composition-{fixture_index:020x}"
            graph_digest = graph_digest_for_observation(
                selected,
                relationships,
                source_node_by_skill={
                    item["skill_id"]: item["source_node_id"] for item in source_slices
                },
                slices_by_id={item["slice_id"]: item for item in source_slices},
            )
            task_identity = {
                "primary": fixture["domain"],
                "secondary": [fixture["fixture_id"]],
                "confidence": 1.0,
            }
            content_digests = sorted({item["content_digest"] for item in source_slices})
            source_node_ids = [item["source_node_id"] for item in source_slices]
            active_stages = [
                {
                    "stage_id": f"stage-{index}",
                    "active_skill_ids": [skill_id],
                }
                for index, skill_id in enumerate(selected, start=1)
            ]
            context_accounting = self._context_accounting(
                fixture_id=fixture["fixture_id"],
                active_stages=active_stages,
            )
            execution_context = self._projected_execution_context(context_accounting)
            quality_scores = {
                "no_skill": 0.50,
                "singletons": {
                    skill_id: 0.65 - (index * 0.01)
                    for index, skill_id in enumerate(selected)
                },
                "leave_one_out": {
                    skill_id: 0.73 - (index * 0.01)
                    for index, skill_id in enumerate(selected)
                },
                "naive_union": 0.72,
                "full_composition": 0.82,
                "wrong_order": 0.75,
            }
            variant_quality_scores = {
                "no_skill": quality_scores["no_skill"],
                "naive_union": quality_scores["naive_union"],
                "full_composition": quality_scores["full_composition"],
                "wrong_order": quality_scores["wrong_order"],
                **{
                    f"singleton:{skill_id}": quality_scores["singletons"][skill_id]
                    for skill_id in selected
                },
                **{
                    f"leave_one_out:{skill_id}": quality_scores["leave_one_out"][
                        skill_id
                    ]
                    for skill_id in selected
                },
            }
            dimension_ids = [
                item["dimension_id"] for item in fixture["quality_rubric"]["dimensions"]
            ]
            variant_dimension_scores = {
                variant_id: {
                    dimension_id: variant_quality_scores[variant_id]
                    for dimension_id in dimension_ids
                }
                for variant_id in sorted(variant_ids)
            }
            run_receipt = {
                "schema": "tmcp-run-receipt-v0.1",
                "created_at": "2026-07-17T00:00:00Z",
                "packet_id": f"packet-{fixture_index}",
                "recipe_id": composition_plan_id,
                "task_identity": task_identity,
                "graph_digest": graph_digest,
                "content_digests": content_digests,
                "selected_skill_ids": source_node_ids,
                "activated_atoms": list(selected),
                "ignored_atoms": [],
                "commands_run": ["synthetic unit evaluator"],
                "verification_results": ["synthetic evidence complete"],
                "phase_trace": [
                    {
                        "from_phase": "start",
                        "to_phase": "verification",
                        "status": "advanced",
                    }
                ],
                "gate_results": [
                    {
                        "gate_id": "composition-safety",
                        "category": "safety",
                        "status": "passed",
                    }
                ],
                "quality_metrics": {
                    "synergy_lift": 0.17,
                    "compiler_lift": 0.10,
                    "order_lift": 0.07,
                },
                "cost_metrics": {
                    "context_tokens": 700,
                    "context_ratio": 0.70,
                },
                **execution_context,
                "user_overrides": [],
                "outcome": "passed",
                "trust": "advisory_untrusted",
                "instruction_override_policy": (
                    "never_override_higher_priority_instructions"
                ),
            }
            self._refresh_benchmark_receipt_provenance(
                run_receipt,
                fixture_id=fixture["fixture_id"],
            )
            execution_manifest: list[dict[str, Any]] = []
            evidence_manifest: list[dict[str, Any]] = []
            variant_evidence: dict[str, list[str]] = {}
            for variant_id in sorted(variant_ids):
                artifact = json.dumps(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "variant_id": variant_id,
                        "skill_order": variant_skill_order(variant_id, selected),
                        "preflight_id": preflight_id,
                        "composition_plan_id": composition_plan_id,
                        "graph_digest": graph_digest,
                    },
                    sort_keys=True,
                )
                execution, evidence = self._execution_evidence(
                    subject_id=fixture["fixture_id"],
                    variant_id=variant_id,
                    input_digest=behavioral_input_digest(
                        fixture,
                        selected,
                        variant_id,
                    ),
                    artifact=artifact,
                    result_digest=execution_result_digest(
                        variant_id,
                        variant_quality_score(quality_scores, variant_id),
                        variant_dimension_scores[variant_id],
                    ),
                    tmcp_run_receipt=run_receipt
                    if variant_id == "full_composition"
                    else None,
                )
                execution_manifest.append(execution)
                evidence_manifest.append(evidence)
                variant_evidence[variant_id] = [evidence["evidence_id"]]
            variant_dimension_evidence = {
                variant_id: {
                    dimension["dimension_id"]: [
                        {
                            "requirement": requirement,
                            "evidence_ids": variant_evidence[variant_id],
                            "claim": (
                                "Synthetic unit evidence for "
                                f"{fixture['fixture_id']} {variant_id} "
                                f"{dimension['dimension_id']} {requirement}."
                            ),
                        }
                        for requirement in dimension["evidence_required"]
                    ]
                    for dimension in fixture["quality_rubric"]["dimensions"]
                }
                for variant_id in sorted(variant_ids)
            }
            results.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "preflight_id": preflight_id,
                    "composition_plan_id": composition_plan_id,
                    "graph_digest": graph_digest,
                    "task_identity": task_identity,
                    "selected_skill_ids": selected,
                    "source_slices": source_slices,
                    "ordered_skill_ids": list(fixture["expected_order"]),
                    "active_stages": active_stages,
                    "relationships": relationships,
                    "compiled_context_tokens": 700,
                    "naive_context_tokens": 1000,
                    "context_accounting": context_accounting,
                    "context_execution_mode": execution_context[
                        "context_execution_mode"
                    ],
                    "quality_scores": quality_scores,
                    "evaluation_provenance": {
                        "evaluator_id": "synthetic-unit-evaluator",
                        "evaluator_version": "0.1",
                        "evaluation_run_id": f"unit-{fixture['fixture_id']}",
                        "evaluated_at": "2026-07-17T00:00:00Z",
                        "method": "synthetic_unit_test",
                        "rubric_id": fixture["quality_rubric"]["rubric_id"],
                        "rubric_version": fixture["quality_rubric"]["version"],
                        "rubric_digest": stable_digest(fixture["quality_rubric"]),
                        "variant_evidence": variant_evidence,
                        "variant_dimension_scores": variant_dimension_scores,
                        "variant_dimension_evidence": variant_dimension_evidence,
                    },
                    "execution_manifest": execution_manifest,
                    "evidence_manifest": evidence_manifest,
                    "run_receipt": run_receipt,
                }
            )
        return results

    def _refresh_behavioral_integrity(
        self,
        fixture: dict[str, Any],
        observation: dict[str, Any],
    ) -> None:
        selected = observation["selected_skill_ids"]
        source_slices = observation["source_slices"]
        graph_digest = graph_digest_for_observation(
            selected,
            observation["relationships"],
            source_node_by_skill={
                item["skill_id"]: item["source_node_id"] for item in source_slices
            },
            slices_by_id={item["slice_id"]: item for item in source_slices},
        )
        observation["graph_digest"] = graph_digest
        run_receipt = observation["run_receipt"]
        run_receipt["graph_digest"] = graph_digest
        run_receipt["selected_skill_ids"] = [
            next(
                item["source_node_id"]
                for item in source_slices
                if item["skill_id"] == skill_id
            )
            for skill_id in selected
        ]
        run_receipt["content_digests"] = sorted(
            {item["content_digest"] for item in source_slices}
        )
        quality_scores = observation["quality_scores"]
        full_quality = quality_scores["full_composition"]
        run_receipt["quality_metrics"] = {
            "synergy_lift": round(
                full_quality - max(quality_scores["singletons"].values()), 4
            ),
            "compiler_lift": round(full_quality - quality_scores["naive_union"], 4),
            "order_lift": round(full_quality - quality_scores["wrong_order"], 4),
        }
        run_receipt["cost_metrics"] = {
            "context_tokens": observation["compiled_context_tokens"],
            "context_ratio": round(
                observation["compiled_context_tokens"]
                / observation["naive_context_tokens"],
                4,
            ),
        }
        accounting = self._context_accounting(
            fixture_id=fixture["fixture_id"],
            active_stages=observation["active_stages"],
            compiled_tokens=observation["compiled_context_tokens"],
            naive_tokens=observation["naive_context_tokens"],
        )
        execution_context = self._projected_execution_context(
            accounting,
            mode=run_receipt.get(
                "context_execution_mode", "isolated_phase_capsule"
            ),
        )
        observation["context_accounting"] = accounting
        observation["context_execution_mode"] = execution_context[
            "context_execution_mode"
        ]
        run_receipt.update(execution_context)
        self._refresh_benchmark_receipt_provenance(
            run_receipt,
            fixture_id=fixture["fixture_id"],
        )
        variant_dimension_scores = observation["evaluation_provenance"][
            "variant_dimension_scores"
        ]
        execution_manifest: list[dict[str, Any]] = []
        evidence_manifest: list[dict[str, Any]] = []
        variant_evidence: dict[str, list[str]] = {}
        for variant_id in sorted(required_behavioral_variants(selected)):
            artifact = json.dumps(
                {
                    "fixture_id": fixture["fixture_id"],
                    "variant_id": variant_id,
                    "skill_order": variant_skill_order(variant_id, selected),
                    "preflight_id": observation["preflight_id"],
                    "composition_plan_id": observation["composition_plan_id"],
                    "graph_digest": graph_digest,
                },
                sort_keys=True,
            )
            execution, evidence = self._execution_evidence(
                subject_id=fixture["fixture_id"],
                variant_id=variant_id,
                input_digest=behavioral_input_digest(fixture, selected, variant_id),
                artifact=artifact,
                result_digest=execution_result_digest(
                    variant_id,
                    variant_quality_score(quality_scores, variant_id),
                    variant_dimension_scores[variant_id],
                ),
                tmcp_run_receipt=run_receipt
                if variant_id == "full_composition"
                else None,
            )
            execution_manifest.append(execution)
            evidence_manifest.append(evidence)
            variant_evidence[variant_id] = [evidence["evidence_id"]]
        observation["execution_manifest"] = execution_manifest
        observation["evidence_manifest"] = evidence_manifest
        observation["evaluation_provenance"]["variant_evidence"] = variant_evidence
        observation["evaluation_provenance"]["variant_dimension_evidence"] = {
            variant_id: {
                dimension["dimension_id"]: [
                    {
                        "requirement": requirement,
                        "evidence_ids": variant_evidence[variant_id],
                        "claim": (
                            "Synthetic unit evidence for "
                            f"{fixture['fixture_id']} {variant_id} "
                            f"{dimension['dimension_id']} {requirement}."
                        ),
                    }
                    for requirement in dimension["evidence_required"]
                ]
                for dimension in fixture["quality_rubric"]["dimensions"]
            }
            for variant_id in sorted(required_behavioral_variants(selected))
        }

    @staticmethod
    def _source_slice(
        _fixture_index: int,
        _skill_index: int,
        skill_id: str,
        fixture: dict[str, Any],
    ) -> dict[str, Any]:
        source = next(
            item for item in fixture["skill_sources"] if item["skill_id"] == skill_id
        )
        content = source["content"]
        source_digest = content_digest_for(content)
        source_path = f"/benchmark/{fixture['fixture_id']}/{source['relative_path']}"
        source_node_id = hashlib.sha256(
            f"{source_path}:{source_digest}".encode()
        ).hexdigest()[:12]
        slice_digest = stable_digest(content)
        slice_id = "slice-" + stable_digest(
            [source_digest, slice_digest, 0, len(content), source_node_id],
            20,
        )
        return {
            "skill_id": skill_id,
            "source_node_id": source_node_id,
            "relative_path": source["relative_path"],
            "source_path": source_path,
            "content": content,
            "char_start": 0,
            "char_end": len(content),
            "slice_id": slice_id,
            "source_digest": source_digest,
            "slice_digest": slice_digest,
            "content_digest": source_digest,
        }

    def test_assets_cover_twenty_prompts_and_five_behavioral_domains(self) -> None:
        self.assertGreaterEqual(len(self.golden_cases), 20)
        self.assertEqual(len(self.fixture_definitions), 5)
        expected_domains = {
            "ui_product",
            "migration_data",
            "agent_workflow",
            "research_writing_review",
            "diagnose_fix_regression",
        }
        self.assertEqual(
            {case["domain"] for case in self.golden_cases},
            expected_domains,
        )
        self.assertEqual(
            {fixture["domain"] for fixture in self.fixture_definitions},
            expected_domains,
        )
        for case in self.golden_cases:
            self.assertGreaterEqual(len(case["expected_skill_ids"]), 3)
        for fixture in self.fixture_definitions:
            self.assertEqual(
                fixture["expected_skill_ids"],
                fixture["expected_order"],
            )
            self.assertNotIn("quality_scores", fixture)
            self.assertNotIn("compiled_context_tokens", fixture)
            self.assertNotIn("naive_context_tokens", fixture)

    def test_routing_metrics_calculate_recall_and_precision(self) -> None:
        results = self._routing_results()
        expected_skill_count = sum(
            len(case["expected_skill_ids"]) for case in self.golden_cases
        )

        metrics = score_routing_benchmark(self.golden_cases, results)

        self.assertEqual(metrics["expected_skill_recall"], 1.0)
        self.assertEqual(
            metrics["selected_skill_precision"],
            round(expected_skill_count / (expected_skill_count + 1), 4),
        )
        self.assertEqual(
            metrics["cases"][0]["unexpected_skill_ids"],
            ["unrelated-skill"],
        )

    def test_behavioral_metrics_use_observed_quality_and_context_results(self) -> None:
        observed = self._behavioral_results()
        original = copy.deepcopy(observed)

        metrics = score_behavioral_benchmark(
            self.fixture_definitions,
            observed,
        )

        self.assertEqual(observed, original)
        self.assertEqual(metrics["active_conflict_violation_count"], 0)
        self.assertEqual(metrics["provenance_relationship_coverage"], 1.0)
        self.assertEqual(metrics["expected_relationship_coverage"], 1.0)
        self.assertEqual(metrics["context_ratio"], 0.7)
        self.assertEqual(metrics["maximum_fixture_context_ratio"], 0.7)
        self.assertEqual(metrics["quality_metrics"]["synergy_lift"], 0.17)
        self.assertEqual(metrics["quality_metrics"]["compiler_lift"], 0.10)
        self.assertEqual(metrics["quality_metrics"]["order_lift"], 0.07)
        self.assertEqual(metrics["order_match_rate"], 1.0)

    def test_combined_acceptance_reports_conflicts_provenance_and_context_failures(
        self,
    ) -> None:
        observed = self._behavioral_results()
        first_fixture = self.fixture_definitions[0]
        first = observed[0]
        conflict_source, conflict_target = first["selected_skill_ids"][:2]
        slices = {item["skill_id"]: item["slice_id"] for item in first["source_slices"]}
        first["relationships"].append(
            {
                "source_id": conflict_source,
                "target_id": conflict_target,
                "relation": "conflicts_with",
                "citations": [slices[conflict_source], slices[conflict_target]],
            }
        )
        missing_target = first_fixture["expected_skill_ids"][-1]
        first["relationships"] = [
            relationship
            for relationship in first["relationships"]
            if relationship["target_id"] != missing_target
        ]
        first["compiled_context_tokens"] = 900
        self._refresh_behavioral_integrity(first_fixture, first)

        summary = score_composition_benchmark(
            golden_cases=self.golden_cases,
            fixture_definitions=self.fixture_definitions,
            routing_results=self._routing_results(),
            behavioral_results=observed,
        )

        behavioral = summary["behavioral_metrics"]
        self.assertFalse(summary["eligible"])
        self.assertEqual(behavioral["active_conflict_violation_count"], 1)
        self.assertIn(
            {"fixture_id": first_fixture["fixture_id"], "skill_id": missing_target},
            behavioral["missing_incoming_relationships"],
        )
        self.assertEqual(behavioral["maximum_fixture_context_ratio"], 0.9)
        self.assertIn("active_conflict_violations", summary["failed_checks"])
        self.assertIn("incoming_provenance_relationships", summary["failed_checks"])
        self.assertIn("context_ratio", summary["failed_checks"])

    def test_expected_relationships_and_order_are_hard_acceptance_gates(self) -> None:
        observed = self._behavioral_results()
        observed[0]["relationships"][0]["relation"] = "complements"
        self._refresh_behavioral_integrity(self.fixture_definitions[0], observed[0])
        observed[1]["ordered_skill_ids"] = list(
            reversed(observed[1]["ordered_skill_ids"])
        )
        observed[1]["active_stages"] = list(reversed(observed[1]["active_stages"]))

        summary = score_composition_benchmark(
            golden_cases=self.golden_cases,
            fixture_definitions=self.fixture_definitions,
            routing_results=self._routing_results(),
            behavioral_results=observed,
        )

        self.assertFalse(summary["eligible"])
        self.assertIn("incoming_provenance_relationships", summary["failed_checks"])
        self.assertIn("expected_order", summary["failed_checks"])

    def test_complete_observed_results_meet_acceptance_thresholds(self) -> None:
        summary = score_composition_benchmark(
            golden_cases=self.golden_cases,
            fixture_definitions=self.fixture_definitions,
            routing_results=self._routing_results(),
            behavioral_results=self._behavioral_results(),
        )

        self.assertTrue(summary["eligible"])
        self.assertEqual(summary["failed_checks"], [])
        self.assertTrue(all(summary["acceptance_checks"].values()))

    def test_scorer_requires_run_supplied_quality_scores(self) -> None:
        observed = self._behavioral_results()
        del observed[0]["quality_scores"]

        with self.assertRaisesRegex(ValueError, "must be supplied by the run"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_routing_scorer_rejects_missing_case_as_malformed(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Routing observations must match golden case ids exactly",
        ):
            score_routing_benchmark(
                self.golden_cases,
                self._routing_results()[1:],
            )

    def test_routing_execution_manifest_binds_selected_skills(self) -> None:
        observed = self._routing_results()
        observed[0]["selected_skill_ids"].append("post-run-tamper")

        with self.assertRaisesRegex(ValueError, "result_digest"):
            score_routing_benchmark(self.golden_cases, observed)

    def test_active_stages_must_cover_ordered_skills_exactly(self) -> None:
        observed = self._behavioral_results()
        observed[0]["active_stages"] = [
            {"stage_id": "declared-but-empty", "active_skill_ids": []}
        ]

        with self.assertRaisesRegex(ValueError, "cover ordered skills exactly once"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_graph_identity_is_recomputed_from_materialized_sources(self) -> None:
        observed = self._behavioral_results()
        observed[0]["graph_digest"] = "f" * 32
        observed[0]["run_receipt"]["graph_digest"] = "f" * 32

        with self.assertRaisesRegex(ValueError, "source content and relationships"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_evaluator_evidence_must_resolve_to_hash_bound_content(self) -> None:
        observed = self._behavioral_results()
        evidence = observed[0]["evidence_manifest"][0]
        evidence["content"] = "made-up-reference"

        with self.assertRaisesRegex(
            ValueError, "content_digest does not match content"
        ):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_acceptance_uses_unrounded_threshold_values(self) -> None:
        observed = self._behavioral_results()
        for fixture, item in zip(self.fixture_definitions, observed, strict=True):
            quality = item["quality_scores"]
            quality["full_composition"] = 0.79996
            quality["naive_union"] = 0.75
            quality["wrong_order"] = 0.75
            quality["singletons"] = {
                skill_id: 0.69997 for skill_id in item["selected_skill_ids"]
            }
            scores = item["evaluation_provenance"]["variant_dimension_scores"]
            for variant_id, dimensions in scores.items():
                value = variant_quality_score(quality, variant_id)
                for dimension_id in dimensions:
                    dimensions[dimension_id] = value
            item["compiled_context_tokens"] = 75004
            item["naive_context_tokens"] = 100000
            self._refresh_behavioral_integrity(fixture, item)

        summary = score_composition_benchmark(
            golden_cases=self.golden_cases,
            fixture_definitions=self.fixture_definitions,
            routing_results=self._routing_results(),
            behavioral_results=observed,
        )

        self.assertFalse(summary["eligible"])
        self.assertEqual(
            {
                "context_ratio",
                "synergy_lift",
                "compiler_lift",
                "order_lift",
            },
            set(summary["failed_checks"]),
        )
        self.assertEqual(summary["behavioral_metrics"]["context_ratio"], 0.75)
        self.assertEqual(
            summary["behavioral_metrics"]["quality_metrics"],
            {"synergy_lift": 0.1, "compiler_lift": 0.05, "order_lift": 0.05},
        )

    def test_relationship_citations_must_cover_bound_endpoint_slices(self) -> None:
        observed = self._behavioral_results()
        observed[0]["relationships"][0]["citations"] = [
            observed[0]["source_slices"][0]["slice_id"]
        ]

        with self.assertRaisesRegex(ValueError, "cover both endpoint skills"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_relationship_rejects_unknown_harvested_slice(self) -> None:
        observed = self._behavioral_results()
        observed[0]["relationships"][0]["citations"].append(
            "slice-ffffffffffffffffffff"
        )

        with self.assertRaisesRegex(ValueError, "unknown harvested slices"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_receipt_selection_uses_bound_source_node_ids(self) -> None:
        observed = self._behavioral_results()
        observed[0]["run_receipt"]["selected_skill_ids"][0] = observed[0][
            "selected_skill_ids"
        ][0]

        with self.assertRaisesRegex(ValueError, "bound source_node_id values"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_evaluator_dimension_scores_must_reproduce_quality(self) -> None:
        observed = self._behavioral_results()
        scores = observed[0]["evaluation_provenance"]["variant_dimension_scores"]
        dimension_id = next(iter(scores["full_composition"]))
        scores["full_composition"][dimension_id] = 0.10

        with self.assertRaisesRegex(ValueError, "rubric-weighted dimension score"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_evaluator_dimension_evidence_must_bind_its_own_variant(self) -> None:
        observed = self._behavioral_results()
        provenance = observed[0]["evaluation_provenance"]
        full_bindings = provenance["variant_dimension_evidence"]["full_composition"]
        first_dimension = next(iter(full_bindings))
        full_bindings[first_dimension][0]["evidence_ids"] = provenance[
            "variant_evidence"
        ]["no_skill"]

        with self.assertRaisesRegex(ValueError, "bind this variant's evidence"):
            score_behavioral_benchmark(self.fixture_definitions, observed)

    def test_acceptance_runner_consumes_explicit_observations_file(self) -> None:
        observations = {
            "schema": "tmcp-composition-benchmark-observations-v0.1",
            "routing_results": self._routing_results(),
            "behavioral_results": self._behavioral_results(),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            path.write_text(json.dumps(observations), encoding="utf-8")
            observations_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

            summary = run_benchmark(
                routing_golden_path=ROUTING_GOLDEN,
                behavioral_fixtures_path=BEHAVIORAL_FIXTURES,
                observations_path=path,
                allow_synthetic=True,
            )

        self.assertTrue(summary["eligible"])
        self.assertEqual(summary["failed_checks"], [])
        self.assertEqual(summary["observations_sha256"], observations_sha256)
        assert_matches_schema(
            observations,
            SCHEMAS / "tmcp-composition-benchmark-observations-v0.1.schema.json",
        )
        assert_matches_schema(
            {"ok": True, **summary},
            SCHEMAS / "tmcp-composition-benchmark-summary-v0.1.schema.json",
        )

    def test_scorer_is_pure_and_has_no_io_or_runtime_imports(self) -> None:
        for module in (
            composition_benchmarks,
            benchmark_contracts,
            benchmark_evaluator,
            benchmark_manifests,
            benchmark_sources,
        ):
            source_path = Path(inspect.getfile(module))
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imports = {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            imports.update(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            forbidden = (
                "json",
                "os",
                "pathlib",
                "subprocess",
                "tmcp_runtime.services",
            )
            self.assertTrue(
                all(
                    not imported.startswith(prefix)
                    for imported in imports
                    for prefix in forbidden
                )
            )


if __name__ == "__main__":
    unittest.main()
