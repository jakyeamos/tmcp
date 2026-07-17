"""Compiler-only replay and control derivation for composition benchmarks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .composition_benchmark_protocol import (
    BENCHMARK_RUN_PLAN_SCHEMA,
    fixture_source_nodes,
    fixture_workspace_relative_path,
    prepare_fixture_preflight,
    validate_benchmark_run_plan,
)
from .composition_benchmark_recipes import (
    EXECUTION_RECIPE_SCHEMA,
    _ablation_obligations,
    _compiled_context_accounting,
    _execution_recipe,
    _logical_compiled_plan,
    _recipe_with_identity,
    _variant_controls,
)
from .composition_benchmark_replay_support import (
    SEMANTIC_PROPOSAL_BUNDLE_SCHEMA,
    _fixture_index,
    _logical_handoff,
    _mapping_list,
    _nonempty,
    _ordered_variant_ids,
    _packet_plan,
    _proposal_index,
    _replay_packet,
    _request_index,
    _role_projection,
    _skill_by_node,
    _validate_proposal_bundle,
)
from .composition_preflight import stable_digest
from .composition_validation import ordering_pair
from .harvest_nodes import estimate_tokens
from ..services.compose import compose_packet_from_source_nodes


BENCHMARK_CONTROL_PLAN_SCHEMA = "tmcp-composition-benchmark-control-plan-v0.1"


def _replay_record(
    *,
    preflight: Mapping[str, Any],
    proposal: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    plan = packet.get("composition_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("Replay packet does not have a composition plan.")
    return {
        "preflight": dict(preflight),
        "preflight_digest": stable_digest(dict(preflight)),
        "semantic_proposal": dict(proposal),
        "semantic_proposal_digest": stable_digest(dict(proposal)),
        "packet": dict(packet),
        "packet_digest": stable_digest(dict(packet)),
        "composition_plan_digest": stable_digest(dict(plan)),
    }


def _control_plan_identity(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key not in {"control_plan_id", "control_plan_digest"}
    }


def build_benchmark_control_plan(
    *,
    run_plan: Mapping[str, Any],
    semantic_proposals: Mapping[str, Any],
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay compiler outputs and derive host controls without executing them."""

    if run_plan.get("schema") != BENCHMARK_RUN_PLAN_SCHEMA:
        raise ValueError(f"run_plan.schema must be {BENCHMARK_RUN_PLAN_SCHEMA}.")
    validate_benchmark_run_plan(
        run_plan,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    routing_proposals, behavioral_proposals = _validate_proposal_bundle(
        semantic_proposals,
        run_plan,
    )
    fixtures = _fixture_index(behavioral_fixtures)
    routing_requests = _request_index(
        run_plan,
        field="routing_requests",
        subject_field="case_id",
    )
    behavioral_requests = _request_index(
        run_plan,
        field="behavioral_requests",
        subject_field="fixture_id",
    )

    routing_controls: list[dict[str, Any]] = []
    for case_id, request in routing_requests.items():
        fixture_id = _nonempty(request.get("fixture_id"), field=f"{case_id}.fixture_id")
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            raise ValueError(f"{case_id} references unknown fixture {fixture_id}.")
        preflight, packet = _replay_packet(
            fixture=fixture,
            request=request,
            proposal=routing_proposals[case_id],
        )
        _bindings, selected_skill_ids, _edges = _role_projection(
            fixture, packet, preflight
        )
        routing_controls.append(
            {
                "case_id": case_id,
                "request_id": request["request_id"],
                "input_digest": request["input_digest"],
                "selected_skill_ids": selected_skill_ids,
                "replay": _replay_record(
                    preflight=preflight,
                    proposal=routing_proposals[case_id],
                    packet=packet,
                ),
            }
        )

    behavioral_controls: list[dict[str, Any]] = []
    for fixture_id, request in behavioral_requests.items():
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            raise ValueError(f"Unknown behavioral fixture {fixture_id}.")
        preflight, packet = _replay_packet(
            fixture=fixture,
            request=request,
            proposal=behavioral_proposals[fixture_id],
        )
        source_bindings, selected_skill_ids, ordering_edges = _role_projection(
            fixture,
            packet,
            preflight,
        )
        behavioral_controls.append(
            {
                "fixture_id": fixture_id,
                "request_id": request["request_id"],
                "selected_skill_ids": selected_skill_ids,
                "ordered_skill_ids": list(selected_skill_ids),
                "source_bindings": source_bindings,
                "ordering_edges": [
                    {"source_skill_id": source, "target_skill_id": target}
                    for source, target in sorted(ordering_edges)
                ],
                "variants": _variant_controls(
                    fixture_id=fixture_id,
                    request_id=str(request["request_id"]),
                    source_bindings=source_bindings,
                    preflight=preflight,
                    packet=packet,
                ),
                "replay": _replay_record(
                    preflight=preflight,
                    proposal=behavioral_proposals[fixture_id],
                    packet=packet,
                ),
            }
        )

    control_plan: dict[str, Any] = {
        "schema": BENCHMARK_CONTROL_PLAN_SCHEMA,
        "run_manifest_id": run_plan["run_manifest_id"],
        "run_manifest_digest": run_plan["run_manifest_digest"],
        "semantic_proposals_digest": stable_digest(dict(semantic_proposals)),
        "routing_controls": routing_controls,
        "behavioral_controls": behavioral_controls,
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
    }
    identity = _control_plan_identity(control_plan)
    control_plan["control_plan_digest"] = stable_digest(identity)
    control_plan["control_plan_id"] = "benchmark-control-" + stable_digest(
        identity,
        20,
    )
    return control_plan


def validate_benchmark_control_plan(
    control_plan: Mapping[str, Any],
    *,
    run_plan: Mapping[str, Any],
    semantic_proposals: Mapping[str, Any],
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
) -> None:
    """Reject controls that were not deterministically derived from compiler replay."""

    if control_plan.get("schema") != BENCHMARK_CONTROL_PLAN_SCHEMA:
        raise ValueError(
            f"control_plan.schema must be {BENCHMARK_CONTROL_PLAN_SCHEMA}."
        )
    expected = build_benchmark_control_plan(
        run_plan=run_plan,
        semantic_proposals=semantic_proposals,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    if dict(control_plan) != expected:
        raise ValueError(
            "Benchmark control plan does not match the replayed compiler outputs."
        )
