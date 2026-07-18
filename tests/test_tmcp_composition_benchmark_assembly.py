from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.assemble_composition_benchmark import assemble_observations
from scripts.run_composition_benchmark import run_benchmark
from scripts.schema_contract_support import SchemaAssertionError, assert_matches_schema
from tests.test_tmcp_composition_benchmark_protocol import _semantic_proposal_bundle
from tmcp_runtime.domain.composition_benchmark_assembly import (
    EVALUATOR_ARTIFACTS_SCHEMA,
    HOST_RESULTS_SCHEMA,
    MAX_BENCHMARK_ARTIFACT_BYTES,
    assemble_benchmark_observations,
    validate_assembled_benchmark_observations,
)
from tmcp_runtime.domain.composition_benchmark_protocol import (
    build_benchmark_preparation,
)
from tmcp_runtime.domain.composition_benchmark_replay import (
    build_benchmark_control_plan,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.domain.composition_runtime_evidence import (
    composition_gate_catalog,
    composition_handoff_catalog,
)
from tmcp_runtime.domain.composition_benchmarks import score_composition_benchmark
from tmcp_runtime.domain.receipts import build_benchmark_host_receipt


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMAS = ROOT / "schemas"
ROUTING_PATH = FIXTURES / "composition_routing_golden_v0_6.json"
BEHAVIORAL_PATH = FIXTURES / "composition_behavioral_fixtures_v0_6.json"


def _payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain an object")
    return payload


def _variant_score(variant_id: str, selected_skill_ids: list[str]) -> float:
    if variant_id == "no_skill":
        return 0.50
    if variant_id == "naive_union":
        return 0.72
    if variant_id == "full_composition":
        return 0.82
    if variant_id == "wrong_order":
        return 0.75
    prefix, _separator, skill_id = variant_id.partition(":")
    index = selected_skill_ids.index(skill_id)
    if prefix == "singleton":
        return 0.65 - (index * 0.01)
    if prefix == "leave_one_out":
        return 0.73 - (index * 0.01)
    raise AssertionError(f"Unknown test variant {variant_id}")


def _receipt(
    control: dict[str, object],
    *,
    fixture_id: str,
    quality_metrics: dict[str, float],
    artifact_digest: str,
) -> dict[str, object]:
    full = next(
        item for item in control["variants"] if item["variant_id"] == "full_composition"
    )
    packet = control["replay"]["packet"]
    plan = packet["composition_plan"]
    recipe = full["execution_recipe"]
    accounting = recipe["context_accounting"]
    stages = plan["ordered_stages"]
    final_phase = stages[-1]["phase"]
    final_packet_id = "packet-" + stable_digest(
        {
            "objective": packet["objective"],
            "phase": final_phase,
            "composition_plan_id": plan["composition_plan_id"],
            "graph_digest": plan["provenance"]["graph_digest"],
        }
    )[:12]
    source_bindings = list(control["source_bindings"])
    runtime_plan = plan
    runtime: dict[str, object] | None = None
    for stage in stages[1:]:
        gate_results = [
            {"gate_id": gate["gate_id"], "status": "passed"}
            for gate in composition_gate_catalog(runtime_plan)
        ]
        handoff_results = [
            {
                "handoff_id": contract["handoff_id"],
                "producer_node_id": contract["producer_node_id"],
                "consumer_node_id": contract["consumer_node_id"],
                "status": "available",
                "consumed_inputs": contract["required_inputs"],
                "produced_outputs": contract["produced_outputs"],
                "evidence_refs": [f"artifact:{artifact_digest}"],
            }
            for contract in composition_handoff_catalog(runtime_plan)
        ]
        runtime = advance_composition_runtime(
            runtime_plan,
            {
                "requested_phase": stage["phase"],
                "gate_results": gate_results,
                "handoff_results": handoff_results,
            },
        )
        runtime_plan = runtime["composition_plan"]
    if runtime is None:
        raise AssertionError("benchmark plan requires at least two stages")
    context_instance_id = f"host-context-{fixture_id}"
    execution_context = {
        "schema": "tmcp-composition-benchmark-execution-context-v0.1",
        "execution_context_mode": "same_host_transcript",
        "context_accounting_digest": accounting["context_accounting_digest"],
        "preflight_capsule_digest": accounting["preflight_capsule_digest"],
        "preflight_context_instance_id": context_instance_id,
        "phase_capsule_trace": [
            {
                "stage_id": capsule["stage_id"],
                "capsule_digest": capsule["capsule_digest"],
                "context_instance_id": context_instance_id,
                "incoming_handoff_digests": capsule["incoming_handoff_digests"],
            }
            for capsule in accounting["phase_capsules"]
        ],
    }
    return build_benchmark_host_receipt(
        {
        "packet_id": final_packet_id,
        "recipe_id": plan["composition_plan_id"],
        "task_identity": packet["task_identity"],
        "graph_digest": plan["provenance"]["graph_digest"],
        "content_digests": sorted({item["content_digest"] for item in source_bindings}),
        "selected_skill_ids": [item["source_node_id"] for item in source_bindings],
        "activated_atoms": packet["receipt_template"]["activated_atoms"],
        "ignored_atoms": [],
        "commands_run": ["benchmark host execution"],
        "verification_results": [],
        "phase_trace": runtime["phase_trace"],
        "gate_results": runtime["gate_evaluation"]["evaluated_gates"],
        "handoff_results": runtime["handoff_evaluation"]["evaluated_handoffs"],
        "quality_metrics": quality_metrics,
        "cost_metrics": {
            "context_tokens": accounting["compiled_context_tokens"],
            "context_ratio": round(
                accounting["compiled_context_tokens"]
                / accounting["naive_context_tokens"],
                4,
            ),
        },
        "user_overrides": [],
        "composition_fixture_id": fixture_id,
        "benchmark_control_input_digest": full["input_packet_digest"],
        "benchmark_execution_recipe_digest": full["execution_recipe_digest"],
        "execution_context": execution_context,
        "outcome": "passed",
        },
        created_at="2026-07-17T00:00:00Z",
    )


def _host_and_evaluator(
    controls: dict[str, object],
    behavioral: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    fixture_by_id = {
        str(fixture["fixture_id"]): fixture for fixture in behavioral["fixtures"]
    }
    host: dict[str, object] = {
        "schema": HOST_RESULTS_SCHEMA,
        "run_manifest_id": controls["run_manifest_id"],
        "run_manifest_digest": controls["run_manifest_digest"],
        "control_plan_id": controls["control_plan_id"],
        "control_plan_digest": controls["control_plan_digest"],
        "evidence_class": "synthetic_test",
        "routing_runs": [],
        "behavioral_runs": [],
    }
    for control in controls["routing_controls"]:
        case_id = str(control["case_id"])
        host["routing_runs"].append(
            {
                "case_id": case_id,
                "request_id": control["request_id"],
                "input_digest": control["input_digest"],
                "selected_skill_ids": control["selected_skill_ids"],
                "run_id": f"host-routing-{case_id}",
                "outcome": "passed",
                "artifact": json.dumps(
                    {
                        "case_id": case_id,
                        "selected_skill_ids": control["selected_skill_ids"],
                    },
                    sort_keys=True,
                ),
                "evidence": [
                    {
                        "media_type": "text/plain",
                        "content": f"Host routing evidence for {case_id}.",
                    }
                ],
            }
        )
    evaluator: dict[str, object] = {
        "schema": EVALUATOR_ARTIFACTS_SCHEMA,
        "run_manifest_id": controls["run_manifest_id"],
        "run_manifest_digest": controls["run_manifest_digest"],
        "control_plan_id": controls["control_plan_id"],
        "control_plan_digest": controls["control_plan_digest"],
        "evaluator_execution": {
            "execution_class": "synthetic_test",
            "executor_id": "benchmark-test-evaluator",
            "execution_id": "synthetic-benchmark-assembly",
            "executed_at": "2026-07-17T00:00:00Z",
        },
        "fixture_evaluations": [],
    }
    for control in controls["behavioral_controls"]:
        fixture_id = str(control["fixture_id"])
        fixture = fixture_by_id[fixture_id]
        selected = list(control["selected_skill_ids"])
        quality_metrics = {
            "synergy_lift": round(
                0.82
                - max(
                    _variant_score(f"singleton:{skill_id}", selected)
                    for skill_id in selected
                ),
                4,
            ),
            "compiler_lift": 0.10,
            "order_lift": 0.07,
        }
        host_variants: list[dict[str, object]] = []
        evaluator_variants: list[dict[str, object]] = []
        for variant in control["variants"]:
            variant_id = str(variant["variant_id"])
            artifact = json.dumps(
                {
                    "fixture_id": fixture_id,
                    "variant_id": variant_id,
                    "input_packet_digest": variant["input_packet_digest"],
                },
                sort_keys=True,
            )
            host_variant: dict[str, object] = {
                "variant_id": variant_id,
                "input_packet_digest": variant["input_packet_digest"],
                "execution_recipe_digest": variant["execution_recipe_digest"],
                "run_id": f"host-{fixture_id}-{variant_id}",
                "outcome": "passed",
                "artifact": artifact,
            }
            if variant_id == "full_composition":
                host_variant["tmcp_run_receipt"] = _receipt(
                    control,
                    fixture_id=fixture_id,
                    quality_metrics=quality_metrics,
                    artifact_digest=stable_digest(artifact),
                )
            host_variants.append(host_variant)
            score = _variant_score(variant_id, selected)
            evaluator_variants.append(
                {
                    "variant_id": variant_id,
                    "input_packet_digest": variant["input_packet_digest"],
                    "execution_recipe_digest": variant["execution_recipe_digest"],
                    "execution_artifact_digest": stable_digest(artifact),
                    "dimension_scores": {
                        dimension["dimension_id"]: score
                        for dimension in fixture["quality_rubric"]["dimensions"]
                    },
                    "evidence": [
                        {
                            "evidence_id": f"eval-{fixture_id}-{variant_id}",
                            "media_type": "text/plain",
                            "content": (
                                f"Evaluator evidence for {fixture_id} {variant_id}."
                            ),
                        }
                    ],
                    "dimension_evidence": {
                        dimension["dimension_id"]: [
                            {
                                "requirement": requirement,
                                "evidence_ids": [
                                    f"eval-{fixture_id}-{variant_id}"
                                ],
                                "claim": (
                                    f"Evaluator claim for {fixture_id} {variant_id} "
                                    f"{dimension['dimension_id']} {requirement}."
                                ),
                            }
                            for requirement in dimension["evidence_required"]
                        ]
                        for dimension in fixture["quality_rubric"]["dimensions"]
                    },
                }
            )
        host["behavioral_runs"].append(
            {
                "fixture_id": fixture_id,
                "request_id": control["request_id"],
                "variants": host_variants,
            }
        )
        rubric = fixture["quality_rubric"]
        evaluator["fixture_evaluations"].append(
            {
                "fixture_id": fixture_id,
                "evaluator_id": "benchmark-test-evaluator",
                "evaluator_version": "0.1",
                "evaluation_run_id": f"eval-{fixture_id}",
                "evaluated_at": "2026-07-17T00:00:00Z",
                "method": "deterministic-test-rubric",
                "rubric_id": rubric["rubric_id"],
                "rubric_version": rubric["version"],
                "rubric_digest": stable_digest(rubric),
                "variants": evaluator_variants,
            }
        )
    return host, evaluator


def _mark_release_evidence_admissible(
    host: dict[str, object], evaluator: dict[str, object]
) -> None:
    host["evidence_class"] = "host_executed"
    evaluator["evaluator_execution"] = {
        "execution_class": "trusted_evaluator_execution",
        "executor_id": "independent-rubric-evaluator",
        "execution_id": "reviewed-benchmark-run",
        "executed_at": "2026-07-17T00:00:00Z",
    }
    for evaluation in evaluator["fixture_evaluations"]:
        evaluation["method"] = "independent_rubric_review"


class CompositionBenchmarkAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routing = _payload(ROUTING_PATH)
        cls.behavioral = _payload(BEHAVIORAL_PATH)
        cls.run_plan, _artifacts = build_benchmark_preparation(
            routing_golden=cls.routing,
            behavioral_fixtures=cls.behavioral,
        )
        cls.proposals = _semantic_proposal_bundle(
            cls.run_plan,
            cls.routing,
            cls.behavioral,
        )
        cls.controls = build_benchmark_control_plan(
            run_plan=cls.run_plan,
            semantic_proposals=cls.proposals,
            routing_golden=cls.routing,
            behavioral_fixtures=cls.behavioral,
        )

    def _assemble(
        self,
        *,
        release_admissible: bool = False,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        host, evaluator = _host_and_evaluator(self.controls, self.behavioral)
        if release_admissible:
            _mark_release_evidence_admissible(host, evaluator)
        observations = assemble_benchmark_observations(
            run_plan=self.run_plan,
            semantic_proposals=self.proposals,
            control_plan=self.controls,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
            host_results=host,
            evaluator_artifacts=evaluator,
        )
        return observations, host, evaluator

    def test_assembly_derives_compiler_bound_observations(self) -> None:
        observations, host, evaluator = self._assemble()

        assert_matches_schema(
            host,
            SCHEMAS / "tmcp-composition-benchmark-host-results-v0.1.schema.json",
        )
        assert_matches_schema(
            evaluator,
            SCHEMAS / "tmcp-composition-benchmark-evaluator-artifacts-v0.1.schema.json",
        )
        assert_matches_schema(
            observations,
            SCHEMAS / "tmcp-composition-benchmark-observations-v0.1.schema.json",
        )
        validate_assembled_benchmark_observations(
            observations,
            run_plan=self.run_plan,
            semantic_proposals=self.proposals,
            control_plan=self.controls,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
            host_results=host,
            evaluator_artifacts=evaluator,
        )
        binding = observations["benchmark_binding"]
        self.assertEqual(binding["control_plan_id"], self.controls["control_plan_id"])
        self.assertEqual(len(observations["routing_results"]), 25)
        self.assertEqual(len(observations["behavioral_results"]), 5)
        first_observation = observations["behavioral_results"][0]
        first_control = self.controls["behavioral_controls"][0]
        self.assertEqual(
            first_observation["graph_digest"],
            first_control["replay"]["packet"]["composition_plan"]["provenance"][
                "graph_digest"
            ],
        )
        plan = first_control["replay"]["packet"]["composition_plan"]
        full_variant = next(
            item
            for item in first_control["variants"]
            if item["variant_id"] == "full_composition"
        )
        accounting = full_variant["execution_recipe"]["context_accounting"]
        binding = plan["phase_capsule_binding"]
        self.assertEqual(
            binding["context_accounting_digest"],
            accounting["context_accounting_digest"],
        )
        self.assertEqual(
            binding["preflight_capsule_digest"],
            accounting["preflight_capsule_digest"],
        )
        self.assertEqual(
            binding["phase_capsule_trace"],
            [
                {
                    "stage_id": capsule["stage_id"],
                    "capsule_digest": capsule["capsule_digest"],
                    "incoming_handoff_digests": capsule[
                        "incoming_handoff_digests"
                    ],
                }
                for capsule in accounting["phase_capsules"]
            ],
        )

    def test_schema_rejects_full_composition_without_host_receipt(self) -> None:
        _observations, host, _evaluator = self._assemble()
        full_variant = next(
            item
            for item in host["behavioral_runs"][0]["variants"]
            if item["variant_id"] == "full_composition"
        )
        full_variant.pop("tmcp_run_receipt")

        with self.assertRaisesRegex(SchemaAssertionError, "missing required"):
            assert_matches_schema(
                host,
                SCHEMAS / "tmcp-composition-benchmark-host-results-v0.1.schema.json",
            )

    def test_run_receipt_schema_rejects_unqualified_context_claim(self) -> None:
        receipt = {
            "schema": "tmcp-run-receipt-v0.1",
            "created_at": "2026-07-17T00:00:00Z",
            "packet_id": "packet-1",
            "activated_atoms": [],
            "ignored_atoms": [],
            "commands_run": [],
            "verification_results": [],
            "user_overrides": [],
            "outcome": "passed",
            "trust": "advisory_untrusted",
            "instruction_override_policy": "receipt policy",
            "context_execution_mode": "isolated_phase_capsule",
        }

        with self.assertRaisesRegex(SchemaAssertionError, "forbidden schema"):
            assert_matches_schema(
                receipt,
                SCHEMAS / "tmcp-run-receipt-v0.1.schema.json",
            )

    def test_assembly_rejects_forged_control_input_and_evaluator_artifact(self) -> None:
        _observations, host, evaluator = self._assemble()
        forged_host = copy.deepcopy(host)
        forged_host["behavioral_runs"][0]["variants"][0]["input_packet_digest"] = (
            "0" * 64
        )
        with self.assertRaisesRegex(ValueError, "input_packet_digest"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=forged_host,
                evaluator_artifacts=evaluator,
            )
        forged_evaluator = copy.deepcopy(evaluator)
        forged_evaluator["fixture_evaluations"][0]["variants"][0][
            "execution_artifact_digest"
        ] = "f" * 64
        with self.assertRaisesRegex(ValueError, "execution_artifact_digest"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=host,
                evaluator_artifacts=forged_evaluator,
            )

    def test_assembly_rejects_forged_full_receipt_and_stale_control(self) -> None:
        _observations, host, evaluator = self._assemble()
        forged_host = copy.deepcopy(host)
        full_variant = next(
            item
            for item in forged_host["behavioral_runs"][0]["variants"]
            if item["variant_id"] == "full_composition"
        )
        full_variant["tmcp_run_receipt"]["graph_digest"] = "f" * 32
        with self.assertRaisesRegex(ValueError, "graph_digest"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=forged_host,
                evaluator_artifacts=evaluator,
            )
        forged_phases = copy.deepcopy(host)
        phase_trace = next(
            item["tmcp_run_receipt"]["phase_trace"]
            for item in forged_phases["behavioral_runs"][0]["variants"]
            if item["variant_id"] == "full_composition"
        )
        phase_trace[0]["from_phase"] = "fabricated-phase"
        with self.assertRaisesRegex(ValueError, "phases do not match compiler stages"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=forged_phases,
                evaluator_artifacts=evaluator,
            )
        forged_obligations = copy.deepcopy(host)
        obligation_trace = next(
            item["tmcp_run_receipt"]["phase_trace"]
            for item in forged_obligations["behavioral_runs"][0]["variants"]
            if item["variant_id"] == "full_composition"
        )
        obligation_trace[0]["required_gate_ids"] = []
        obligation_trace[0]["required_handoff_ids"] = []
        with self.assertRaisesRegex(ValueError, "required gates do not match"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=forged_obligations,
                evaluator_artifacts=evaluator,
            )
        forged_context = copy.deepcopy(host)
        execution_context = next(
            item["tmcp_run_receipt"]["execution_context"]
            for item in forged_context["behavioral_runs"][0]["variants"]
            if item["variant_id"] == "full_composition"
        )
        execution_context["phase_capsule_trace"][0]["capsule_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "phase capsule digest"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=forged_context,
                evaluator_artifacts=evaluator,
            )

    def test_isolated_phase_context_qualifies_without_persisting_instance_ids(self) -> None:
        host, evaluator = _host_and_evaluator(self.controls, self.behavioral)
        for behavioral_run in host["behavioral_runs"]:
            full = next(
                item
                for item in behavioral_run["variants"]
                if item["variant_id"] == "full_composition"
            )
            context = full["tmcp_run_receipt"]["execution_context"]
            context["execution_context_mode"] = "isolated_phase_capsule"
            fixture_id = behavioral_run["fixture_id"]
            context["preflight_context_instance_id"] = f"{fixture_id}-preflight"
            for item in context["phase_capsule_trace"]:
                item["context_instance_id"] = f"{fixture_id}-{item['stage_id']}"
        observations = assemble_benchmark_observations(
            run_plan=self.run_plan,
            semantic_proposals=self.proposals,
            control_plan=self.controls,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
            host_results=host,
            evaluator_artifacts=evaluator,
        )
        summary = score_composition_benchmark(
            golden_cases=self.routing["cases"],
            fixture_definitions=self.behavioral["fixtures"],
            routing_results=observations["routing_results"],
            behavioral_results=observations["behavioral_results"],
        )
        self.assertTrue(summary["eligible"])
        self.assertEqual(
            summary["behavioral_metrics"]["qualified_context_execution_count"], 5
        )
        safe_receipt = observations["behavioral_results"][0]["run_receipt"]
        self.assertNotIn("execution_context", safe_receipt)
        self.assertNotIn("context_instance_id", json.dumps(safe_receipt))

    def test_domain_validator_reassembles_the_raw_evidence_bundles(self) -> None:
        observations, host, evaluator = self._assemble()
        forged = copy.deepcopy(observations)
        forged["benchmark_binding"]["host_results_digest"] = "0" * 64
        forged["benchmark_binding"]["binding_digest"] = stable_digest(
            {
                key: value
                for key, value in forged["benchmark_binding"].items()
                if key != "binding_digest"
            }
        )
        with self.assertRaisesRegex(ValueError, "exactly match"):
            validate_assembled_benchmark_observations(
                forged,
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=host,
                evaluator_artifacts=evaluator,
            )

    def test_assembly_rejects_unsafe_evidence_and_projects_raw_receipts(self) -> None:
        host, evaluator = _host_and_evaluator(self.controls, self.behavioral)
        secret = "sk-" + "A1b2C3d4E5f6G7h8I9j0" * 2
        unsafe_host = copy.deepcopy(host)
        unsafe_host["routing_runs"][0]["artifact"] = secret
        with self.assertRaisesRegex(ValueError, "sensitive or high-entropy"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=unsafe_host,
                evaluator_artifacts=evaluator,
            )
        unsafe_evaluator = copy.deepcopy(evaluator)
        unsafe_evaluator["fixture_evaluations"][0]["variants"][0]["evidence"][0][
            "content"
        ] = secret
        with self.assertRaisesRegex(ValueError, "sensitive or high-entropy"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=host,
                evaluator_artifacts=unsafe_evaluator,
            )
        raw_receipt_host = copy.deepcopy(host)
        full_receipt = next(
            variant["tmcp_run_receipt"]
            for variant in raw_receipt_host["behavioral_runs"][0]["variants"]
            if variant["variant_id"] == "full_composition"
        )
        full_receipt["commands_run"] = [secret]
        observations = assemble_benchmark_observations(
            run_plan=self.run_plan,
            semantic_proposals=self.proposals,
            control_plan=self.controls,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
            host_results=raw_receipt_host,
            evaluator_artifacts=evaluator,
        )
        self.assertNotIn(secret, json.dumps(observations, sort_keys=True))

    def test_assembly_requires_dimension_and_handoff_artifact_evidence(self) -> None:
        host, evaluator = _host_and_evaluator(self.controls, self.behavioral)
        incomplete_evaluator = copy.deepcopy(evaluator)
        dimension_bindings = incomplete_evaluator["fixture_evaluations"][0][
            "variants"
        ][0]["dimension_evidence"]
        first_dimension = next(iter(dimension_bindings))
        dimension_bindings[first_dimension] = dimension_bindings[first_dimension][1:]
        with self.assertRaisesRegex(ValueError, "bind every required evidence"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=host,
                evaluator_artifacts=incomplete_evaluator,
            )
        unbound_handoff_host = copy.deepcopy(host)
        full_receipt = next(
            variant["tmcp_run_receipt"]
            for variant in unbound_handoff_host["behavioral_runs"][0]["variants"]
            if variant["variant_id"] == "full_composition"
        )
        full_receipt["handoff_results"][0]["evidence_refs"] = ["host-claim"]
        with self.assertRaisesRegex(ValueError, "must bind the host artifact"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=unbound_handoff_host,
                evaluator_artifacts=evaluator,
            )
        stale = copy.deepcopy(self.controls)
        stale["behavioral_controls"][0]["variants"][1]["ordered_skill_ids"] = []
        with self.assertRaisesRegex(ValueError, "does not match the replayed"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=stale,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=host,
                evaluator_artifacts=evaluator,
            )

    def test_assembly_caps_direct_mapping_inputs_before_projection(self) -> None:
        host, evaluator = _host_and_evaluator(self.controls, self.behavioral)
        oversized_host = copy.deepcopy(host)
        full_receipt = next(
            variant["tmcp_run_receipt"]
            for variant in oversized_host["behavioral_runs"][0]["variants"]
            if variant["variant_id"] == "full_composition"
        )
        full_receipt["commands_run"] = [
            "x" * (MAX_BENCHMARK_ARTIFACT_BYTES + 1)
        ]
        with self.assertRaisesRegex(ValueError, "host results exceeds"):
            assemble_benchmark_observations(
                run_plan=self.run_plan,
                semantic_proposals=self.proposals,
                control_plan=self.controls,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
                host_results=oversized_host,
                evaluator_artifacts=evaluator,
            )

    def test_runner_requires_bound_artifacts_and_accepts_assembled_output(self) -> None:
        observations, host, evaluator = self._assemble(release_admissible=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "observations": root / "observations.json",
                "run_plan": root / "run-plan.json",
                "semantic_proposals": root / "semantic-proposals.json",
                "control_plan": root / "control-plan.json",
                "host_results": root / "host-results.json",
                "evaluator_artifacts": root / "evaluator-artifacts.json",
            }
            payloads = {
                "observations": observations,
                "run_plan": self.run_plan,
                "semantic_proposals": self.proposals,
                "control_plan": self.controls,
                "host_results": host,
                "evaluator_artifacts": evaluator,
            }
            for key, path in paths.items():
                path.write_text(json.dumps(payloads[key]), encoding="utf-8")
            assembly = assemble_observations(
                run_plan_path=paths["run_plan"],
                semantic_proposals_path=paths["semantic_proposals"],
                control_plan_path=paths["control_plan"],
                host_results_path=paths["host_results"],
                evaluator_artifacts_path=paths["evaluator_artifacts"],
                routing_golden_path=ROUTING_PATH,
                behavioral_fixtures_path=BEHAVIORAL_PATH,
                output_dir=root / "assembled",
            )
            generated_observations = Path(assembly["observations_path"])
            self.assertEqual(
                json.loads(generated_observations.read_text(encoding="utf-8")),
                observations,
            )
            with self.assertRaisesRegex(ValueError, "requires run_plan"):
                run_benchmark(
                    routing_golden_path=ROUTING_PATH,
                    behavioral_fixtures_path=BEHAVIORAL_PATH,
                    observations_path=generated_observations,
                )
            summary = run_benchmark(
                routing_golden_path=ROUTING_PATH,
                behavioral_fixtures_path=BEHAVIORAL_PATH,
                observations_path=generated_observations,
                run_plan_path=paths["run_plan"],
                semantic_proposals_path=paths["semantic_proposals"],
                control_plan_path=paths["control_plan"],
                host_results_path=paths["host_results"],
                evaluator_artifacts_path=paths["evaluator_artifacts"],
            )

        self.assertFalse(summary["eligible"])
        self.assertEqual(summary["failed_checks"], ["context_execution_mode"])
        self.assertTrue(summary["acceptance_checks"]["context_ratio"])

    def test_release_runner_rejects_the_synthetic_six_artifact_bundle(self) -> None:
        observations, host, evaluator = self._assemble()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "observations": root / "observations.json",
                "run_plan": root / "run-plan.json",
                "semantic_proposals": root / "semantic-proposals.json",
                "control_plan": root / "control-plan.json",
                "host_results": root / "host-results.json",
                "evaluator_artifacts": root / "evaluator-artifacts.json",
            }
            payloads = {
                "observations": observations,
                "run_plan": self.run_plan,
                "semantic_proposals": self.proposals,
                "control_plan": self.controls,
                "host_results": host,
                "evaluator_artifacts": evaluator,
            }
            for key, path in paths.items():
                path.write_text(json.dumps(payloads[key]), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "host_results.evidence_class must be host_executed",
            ):
                run_benchmark(
                    routing_golden_path=ROUTING_PATH,
                    behavioral_fixtures_path=BEHAVIORAL_PATH,
                    observations_path=paths["observations"],
                    run_plan_path=paths["run_plan"],
                    semantic_proposals_path=paths["semantic_proposals"],
                    control_plan_path=paths["control_plan"],
                    host_results_path=paths["host_results"],
                    evaluator_artifacts_path=paths["evaluator_artifacts"],
                )

    def test_release_runner_requires_trusted_evaluator_metadata_and_method(
        self,
    ) -> None:
        observations, host, evaluator = self._assemble(release_admissible=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "observations": root / "observations.json",
                "run_plan": root / "run-plan.json",
                "semantic_proposals": root / "semantic-proposals.json",
                "control_plan": root / "control-plan.json",
                "host_results": root / "host-results.json",
                "evaluator_artifacts": root / "evaluator-artifacts.json",
            }
            payloads = {
                "observations": observations,
                "run_plan": self.run_plan,
                "semantic_proposals": self.proposals,
                "control_plan": self.controls,
                "host_results": host,
                "evaluator_artifacts": evaluator,
            }
            for key, path in paths.items():
                path.write_text(json.dumps(payloads[key]), encoding="utf-8")

            evaluator_execution = evaluator["evaluator_execution"]
            evaluator_execution["execution_class"] = "synthetic_test"
            paths["evaluator_artifacts"].write_text(
                json.dumps(evaluator), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ValueError,
                "execution_class must be trusted_evaluator_execution",
            ):
                run_benchmark(
                    routing_golden_path=ROUTING_PATH,
                    behavioral_fixtures_path=BEHAVIORAL_PATH,
                    observations_path=paths["observations"],
                    run_plan_path=paths["run_plan"],
                    semantic_proposals_path=paths["semantic_proposals"],
                    control_plan_path=paths["control_plan"],
                    host_results_path=paths["host_results"],
                    evaluator_artifacts_path=paths["evaluator_artifacts"],
                )

            evaluator_execution["execution_class"] = "trusted_evaluator_execution"
            for evaluation in evaluator["fixture_evaluations"]:
                evaluation["method"] = "deterministic-test-rubric"
            paths["evaluator_artifacts"].write_text(
                json.dumps(evaluator), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ValueError,
                "evaluator method is test-only",
            ):
                run_benchmark(
                    routing_golden_path=ROUTING_PATH,
                    behavioral_fixtures_path=BEHAVIORAL_PATH,
                    observations_path=paths["observations"],
                    run_plan_path=paths["run_plan"],
                    semantic_proposals_path=paths["semantic_proposals"],
                    control_plan_path=paths["control_plan"],
                    host_results_path=paths["host_results"],
                    evaluator_artifacts_path=paths["evaluator_artifacts"],
                )

            for evaluation in evaluator["fixture_evaluations"]:
                evaluation["method"] = "independent_rubric_review"
            evaluator_execution["execution_id"] = "different-reviewed-benchmark-run"
            paths["evaluator_artifacts"].write_text(
                json.dumps(evaluator), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ValueError,
                "observations do not exactly match compiler-bound host/evaluator assembly",
            ):
                run_benchmark(
                    routing_golden_path=ROUTING_PATH,
                    behavioral_fixtures_path=BEHAVIORAL_PATH,
                    observations_path=paths["observations"],
                    run_plan_path=paths["run_plan"],
                    semantic_proposals_path=paths["semantic_proposals"],
                    control_plan_path=paths["control_plan"],
                    host_results_path=paths["host_results"],
                    evaluator_artifacts_path=paths["evaluator_artifacts"],
                )


if __name__ == "__main__":
    unittest.main()
