"""Pure, no-call preregistration planner for composition-lift pilots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .composition_benchmark_manifests import (
    required_behavioral_variants,
    variant_skill_order,
)
from .composition_lift_campaign_support import (
    BASELINE_CONFIGURATION_SLOTS,
    REPLICATE_INDICES,
    build_block,
    validate_factorial_block,
)
from .composition_preflight import stable_digest


COMPOSITION_LIFT_CAMPAIGN_SCHEMA = "tmcp-composition-lift-campaign-v0.1"
CONTROL_PLAN_SCHEMA = "tmcp-composition-benchmark-control-plan-v0.1"
MAX_BLOCKS = 5
MAX_SKILLS_PER_BLOCK = 4
MAX_VARIANTS_PER_BLOCK = 12
_DIGEST_CHARS = frozenset("0123456789abcdef")
_FORBIDDEN_CONTROL_KEYS = (
    "two_arm",
    "source_bundle",
    "live_execution",
    "live_model_call",
    "host_results",
    "execution_result",
    "receipt_written",
    "receipt_persisted",
)
__all__ = (
    "BASELINE_CONFIGURATION_SLOTS",
    "REPLICATE_INDICES",
    "build_composition_lift_campaign",
    "validate_composition_lift_campaign",
)


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _mappings(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [
        _mapping(item, field=f"{field}[{index}]") for index, item in enumerate(value)
    ]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _text(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required.")
    return result


def _digest(value: object, *, field: str, length: int = 64) -> str:
    result = _text(value, field=field)
    if len(result) != length or any(
        character not in _DIGEST_CHARS for character in result
    ):
        raise ValueError(f"{field} must be a {length}-character lowercase digest.")
    return result


def _ids(value: object, *, field: str, expected_length: int | None = None) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of skill ids.")
    result = [
        _text(item, field=f"{field}[{index}]") for index, item in enumerate(value)
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must contain unique skill ids.")
    if expected_length is not None and len(result) != expected_length:
        raise ValueError(f"{field} must contain exactly {expected_length} skill ids.")
    return result


def _identity(payload: Mapping[str, Any], *excluded: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in set(excluded)}


def _normalized_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_")


def _reject_unsupported_claims(value: object, *, field: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = _normalized_key(key)
            if any(marker in normalized for marker in _FORBIDDEN_CONTROL_KEYS):
                raise ValueError(f"{field}.{key} is not allowed in a no-call campaign.")
            if normalized == "model_calls_authorized" and nested is not False:
                raise ValueError(f"{field}.{key} must be false when present.")
            _reject_unsupported_claims(nested, field=f"{field}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _reject_unsupported_claims(nested, field=f"{field}[{index}]")


def _validate_rubric(value: object, *, field: str) -> dict[str, Any]:
    rubric = dict(_mapping(value, field=field))
    expected = {"rubric_id", "version", "aggregation", "score_scale", "dimensions"}
    if set(rubric) != expected:
        raise ValueError(f"{field} must carry the exact published rubric fields.")
    _text(rubric.get("rubric_id"), field=f"{field}.rubric_id")
    _text(rubric.get("version"), field=f"{field}.version")
    if rubric.get("aggregation") != "weighted_mean":
        raise ValueError(f"{field}.aggregation must be weighted_mean.")
    score_scale = _mapping(rubric.get("score_scale"), field=f"{field}.score_scale")
    if dict(score_scale) != {"minimum": 0, "maximum": 1, "higher_is_better": True}:
        raise ValueError(
            f"{field}.score_scale must be the published zero-to-one scale."
        )
    dimensions = _mappings(rubric.get("dimensions"), field=f"{field}.dimensions")
    if len(dimensions) < 3 or len(dimensions) > 16:
        raise ValueError(f"{field}.dimensions must contain three to sixteen entries.")
    dimension_ids: set[str] = set()
    total_weight = 0.0
    for index, dimension in enumerate(dimensions):
        prefix = f"{field}.dimensions[{index}]"
        if set(dimension) != {
            "dimension_id",
            "weight",
            "criterion",
            "evidence_required",
        }:
            raise ValueError(
                f"{prefix} must carry the exact published dimension fields."
            )
        dimension_id = _text(
            dimension.get("dimension_id"), field=f"{prefix}.dimension_id"
        )
        if dimension_id in dimension_ids:
            raise ValueError(f"{field} has duplicate dimension {dimension_id}.")
        dimension_ids.add(dimension_id)
        weight = dimension.get("weight")
        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not 0 <= weight <= 1
        ):
            raise ValueError(f"{prefix}.weight must be a zero-to-one number.")
        total_weight += float(weight)
        _text(dimension.get("criterion"), field=f"{prefix}.criterion")
        _ids(dimension.get("evidence_required"), field=f"{prefix}.evidence_required")
    if abs(total_weight - 1.0) > 1e-9:
        raise ValueError(f"{field} dimension weights must sum to one.")
    return rubric


def _source_bindings(
    value: object,
    *,
    field: str,
    expected_skill_ids: list[str],
) -> list[dict[str, Any]]:
    bindings = [dict(item) for item in _mappings(value, field=field)]
    if len(bindings) != len(expected_skill_ids):
        raise ValueError(f"{field} must bind exactly the expected skills.")
    observed = [
        _text(item.get("skill_id"), field=f"{field}.skill_id") for item in bindings
    ]
    if observed != expected_skill_ids:
        raise ValueError(f"{field} does not preserve the compiler skill order.")
    nodes = [
        _text(item.get("source_node_id"), field=f"{field}.source_node_id")
        for item in bindings
    ]
    if len(nodes) != len(set(nodes)):
        raise ValueError(f"{field} has duplicate source nodes.")
    for item in bindings:
        _text(item.get("relative_path"), field=f"{field}.relative_path")
        _digest(item.get("content_digest"), field=f"{field}.content_digest")
    return bindings


def _variant_ids(selected_skill_ids: list[str]) -> list[str]:
    return [
        "no_skill",
        "naive_union",
        *(f"singleton:{skill_id}" for skill_id in selected_skill_ids),
        "full_composition",
        *(f"leave_one_out:{skill_id}" for skill_id in selected_skill_ids),
        "wrong_order",
    ]


def _execution_mode(variant_id: str) -> str:
    if variant_id == "full_composition":
        return "compiled_composition"
    if variant_id == "wrong_order":
        return "counterfactual_wrong_order"
    if variant_id.startswith("leave_one_out:"):
        return "counterfactual_ablation"
    if variant_id == "no_skill":
        return "no_skill_baseline"
    if variant_id == "naive_union":
        return "naive_union_baseline"
    if variant_id.startswith("singleton:"):
        return "singleton_baseline"
    raise ValueError(f"Unsupported benchmark variant {variant_id}.")


def _replay_binding(
    control: Mapping[str, Any], *, field: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], str, str]:
    replay = _mapping(control.get("replay"), field=f"{field}.replay")
    packet = _mapping(replay.get("packet"), field=f"{field}.replay.packet")
    plan = _mapping(packet.get("composition_plan"), field=f"{field}.replay.packet.plan")
    plan_digest = stable_digest(dict(plan))
    if _digest(
        replay.get("packet_digest"), field=f"{field}.replay.packet_digest"
    ) != stable_digest(dict(packet)):
        raise ValueError(f"{field}.replay packet digest drifted.")
    if (
        _digest(
            replay.get("composition_plan_digest"), field=f"{field}.replay.plan_digest"
        )
        != plan_digest
    ):
        raise ValueError(f"{field}.replay composition plan digest drifted.")
    plan_id = _text(
        plan.get("composition_plan_id"), field=f"{field}.composition_plan_id"
    )
    graph_digest = _digest(
        _mapping(plan.get("provenance"), field=f"{field}.plan.provenance").get(
            "graph_digest"
        ),
        field=f"{field}.plan.graph_digest",
        length=32,
    )
    return replay, packet, plan_id, graph_digest


def _validate_variant(
    variant: Mapping[str, Any],
    *,
    field: str,
    fixture_id: str,
    request_id: str,
    task_context_digest: str,
    selected_skill_ids: list[str],
    source_bindings: list[dict[str, Any]],
    packet: Mapping[str, Any],
    plan_id: str,
    plan_digest: str,
    graph_digest: str,
) -> dict[str, Any]:
    variant_id = _text(variant.get("variant_id"), field=f"{field}.variant_id")
    expected_order = variant_skill_order(variant_id, selected_skill_ids)
    if (
        _ids(variant.get("ordered_skill_ids"), field=f"{field}.ordered_skill_ids")
        != expected_order
    ):
        raise ValueError(f"{field} ordered skills drifted from the compiler control.")
    expected_omitted = [
        skill_id for skill_id in selected_skill_ids if skill_id not in expected_order
    ]
    if (
        _ids(variant.get("omitted_skill_ids"), field=f"{field}.omitted_skill_ids")
        != expected_omitted
    ):
        raise ValueError(f"{field} omitted skills drifted from the compiler control.")
    bindings_by_skill_id = {
        str(binding["skill_id"]): binding for binding in source_bindings
    }
    expected_bindings = [bindings_by_skill_id[skill_id] for skill_id in expected_order]
    if list(variant.get("source_bindings") or []) != expected_bindings:
        raise ValueError(f"{field} source bindings drifted from the compiler control.")
    if (
        variant.get("fixture_id") != fixture_id
        or variant.get("request_id") != request_id
    ):
        raise ValueError(f"{field} is bound to a different fixture request.")
    if variant.get("task_context_digest") != task_context_digest:
        raise ValueError(f"{field}.task_context_digest drifted from its fixture input.")
    if variant.get("cache_policy") != "none":
        raise ValueError(f"{field}.cache_policy must be none.")
    if variant.get("composition_enabled") is not (variant_id == "full_composition"):
        raise ValueError(
            f"{field}.composition_enabled drifted from the compiler control."
        )
    if variant.get("replay_packet_id") != packet.get("packet_id"):
        raise ValueError(f"{field}.replay_packet_id drifted from its replay packet.")
    if _digest(
        variant.get("replay_packet_digest"), field=f"{field}.replay_packet_digest"
    ) != stable_digest(dict(packet)):
        raise ValueError(
            f"{field}.replay_packet_digest drifted from its replay packet."
        )
    recipe = _mapping(
        variant.get("execution_recipe"), field=f"{field}.execution_recipe"
    )
    if _digest(
        recipe.get("recipe_digest"), field=f"{field}.recipe.recipe_digest"
    ) != stable_digest(_identity(recipe, "recipe_digest")):
        raise ValueError(f"{field} execution recipe digest drifted.")
    if _digest(
        variant.get("execution_recipe_digest"), field=f"{field}.execution_recipe_digest"
    ) != recipe.get("recipe_digest"):
        raise ValueError(f"{field} execution recipe binding drifted.")
    required_recipe = {
        "fixture_id": fixture_id,
        "request_id": request_id,
        "variant_id": variant_id,
        "task_context_digest": task_context_digest,
        "cache_policy": "none",
        "execution_mode": _execution_mode(variant_id),
        "source_composition_plan_id": plan_id,
        "source_composition_plan_digest": plan_digest,
        "graph_digest": graph_digest,
        "ordered_skill_ids": expected_order,
        "source_bindings": expected_bindings,
    }
    if any(recipe.get(key) != expected for key, expected in required_recipe.items()):
        raise ValueError(f"{field} execution recipe drifted from its compiler replay.")
    if _digest(
        variant.get("input_packet_digest"), field=f"{field}.input_packet_digest"
    ) != stable_digest(_identity(variant, "input_packet_digest")):
        raise ValueError(f"{field} input packet digest drifted.")
    return {"variant_id": variant_id, "variant": dict(variant)}


def _validated_control(control: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    field = f"behavioral_controls[{index}]"
    fixture_id = _text(control.get("fixture_id"), field=f"{field}.fixture_id")
    request_id = _text(control.get("request_id"), field=f"{field}.request_id")
    selected = _ids(
        control.get("selected_skill_ids"),
        field=f"{field}.selected_skill_ids",
        expected_length=MAX_SKILLS_PER_BLOCK,
    )
    if (
        _ids(
            control.get("ordered_skill_ids"),
            field=f"{field}.ordered_skill_ids",
            expected_length=MAX_SKILLS_PER_BLOCK,
        )
        != selected
    ):
        raise ValueError(f"{field} selected skills were reordered.")
    rubric = _validate_rubric(
        control.get("quality_rubric"), field=f"{field}.quality_rubric"
    )
    rubric_digest = _digest(
        control.get("quality_rubric_digest"), field=f"{field}.quality_rubric_digest"
    )
    if rubric_digest != stable_digest(rubric):
        raise ValueError(f"{field} rubric digest drifted.")
    source_bindings = _source_bindings(
        control.get("source_bindings"),
        field=f"{field}.source_bindings",
        expected_skill_ids=selected,
    )
    task_context_digest = _digest(
        control.get("task_context_digest"),
        field=f"{field}.task_context_digest",
    )
    _replay, packet, plan_id, graph_digest = _replay_binding(control, field=field)
    plan_digest = stable_digest(
        dict(_mapping(packet.get("composition_plan"), field=f"{field}.packet.plan"))
    )
    variants = _mappings(control.get("variants"), field=f"{field}.variants")
    expected_variant_ids = _variant_ids(selected)
    if (
        len(variants) != MAX_VARIANTS_PER_BLOCK
        or [item.get("variant_id") for item in variants] != expected_variant_ids
    ):
        raise ValueError(f"{field} must contain the complete canonical variant order.")
    if set(expected_variant_ids) != required_behavioral_variants(selected):
        raise ValueError(
            f"{field} variant catalog does not match the benchmark matrix."
        )
    by_variant: dict[str, dict[str, Any]] = {}
    for variant in variants:
        projected = _validate_variant(
            variant,
            field=f"{field}.variants[{variant.get('variant_id')} ]",
            fixture_id=fixture_id,
            request_id=request_id,
            task_context_digest=task_context_digest,
            selected_skill_ids=selected,
            source_bindings=source_bindings,
            packet=packet,
            plan_id=plan_id,
            plan_digest=plan_digest,
            graph_digest=graph_digest,
        )
        by_variant[projected["variant_id"]] = projected["variant"]
    return {
        "fixture_id": fixture_id,
        "request_id": request_id,
        "task_context_digest": task_context_digest,
        "selected_skill_ids": selected,
        "quality_rubric": rubric,
        "quality_rubric_digest": rubric_digest,
        "graph_digest": graph_digest,
        "source_composition_plan_digest": plan_digest,
        "variants": by_variant,
    }


def _validate_control_plan(control_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    if control_plan.get("schema") != CONTROL_PLAN_SCHEMA:
        raise ValueError(f"control_plan.schema must be {CONTROL_PLAN_SCHEMA}.")
    if control_plan.get("automatic_tool_execution") is not False:
        raise ValueError("control_plan must prohibit automatic tool execution.")
    if control_plan.get("receipt_persistence") != "not_performed":
        raise ValueError("control_plan must not persist receipts.")
    _reject_unsupported_claims(control_plan, field="control_plan")
    identity = _identity(control_plan, "control_plan_id", "control_plan_digest")
    digest = _digest(
        control_plan.get("control_plan_digest"),
        field="control_plan.control_plan_digest",
    )
    if digest != stable_digest(identity):
        raise ValueError("control_plan digest drifted from its content.")
    if _text(
        control_plan.get("control_plan_id"), field="control_plan.control_plan_id"
    ) != "benchmark-control-" + stable_digest(identity, 20):
        raise ValueError("control_plan id drifted from its content.")
    _text(control_plan.get("run_manifest_id"), field="control_plan.run_manifest_id")
    _digest(
        control_plan.get("run_manifest_digest"),
        field="control_plan.run_manifest_digest",
    )
    controls = _mappings(
        control_plan.get("behavioral_controls"),
        field="control_plan.behavioral_controls",
    )
    if len(controls) != MAX_BLOCKS:
        raise ValueError(
            "composition-lift campaign requires exactly five fixture blocks."
        )
    validated = [
        _validated_control(control, index=index)
        for index, control in enumerate(controls)
    ]
    fixture_ids = [control["fixture_id"] for control in validated]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("composition-lift campaign cannot duplicate fixture blocks.")
    return validated


def validate_composition_lift_campaign(campaign: Mapping[str, Any]) -> None:
    """Validate a generated pilot artifact without executing or persisting anything."""

    if campaign.get("schema") != COMPOSITION_LIFT_CAMPAIGN_SCHEMA:
        raise ValueError(f"campaign.schema must be {COMPOSITION_LIFT_CAMPAIGN_SCHEMA}.")
    if (
        campaign.get("campaign_mode") != "pilot_only"
        or campaign.get("model_calls_authorized") is not False
    ):
        raise ValueError("composition-lift campaign must remain a no-call pilot.")
    if (
        campaign.get("automatic_tool_execution") is not False
        or campaign.get("receipt_persistence") != "not_performed"
    ):
        raise ValueError(
            "composition-lift campaign cannot execute tools or persist receipts."
        )
    if campaign.get("causal_claim_status") != "not_evaluated":
        raise ValueError("composition-lift campaign cannot make a causal claim.")
    _reject_unsupported_claims(campaign, field="campaign")
    source_control_plan = dict(
        _mapping(
            campaign.get("source_control_plan"),
            field="campaign.source_control_plan",
        )
    )
    expected_source_keys = {
        "control_plan_id",
        "control_plan_digest",
        "run_manifest_id",
        "run_manifest_digest",
    }
    if set(source_control_plan) != expected_source_keys:
        raise ValueError(
            "campaign.source_control_plan must be an exact provenance binding."
        )
    for key, prefix in (
        ("control_plan_id", "benchmark-control-"),
        ("run_manifest_id", "benchmark-run-"),
    ):
        if not _text(
            source_control_plan.get(key), field=f"campaign.source.{key}"
        ).startswith(prefix):
            raise ValueError(f"campaign.source.{key} has an invalid provenance id.")
    for key in ("control_plan_digest", "run_manifest_digest"):
        _digest(source_control_plan.get(key), field=f"campaign.source.{key}")
    blocks = _mappings(campaign.get("blocks"), field="campaign.blocks")
    if len(blocks) != MAX_BLOCKS:
        raise ValueError("composition-lift campaign must contain five blocks.")
    baseline_count = causal_count = 0
    fixture_ids: set[str] = set()
    for index, block in enumerate(blocks):
        fixture_id = _text(
            block.get("fixture_id"), field=f"campaign.blocks[{index}].fixture_id"
        )
        if fixture_id in fixture_ids:
            raise ValueError(
                "composition-lift campaign contains duplicate fixture ids."
            )
        fixture_ids.add(fixture_id)
        rubric = _validate_rubric(
            block.get("quality_rubric"),
            field=f"campaign.blocks[{index}].quality_rubric",
        )
        rubric_digest = _digest(
            block.get("quality_rubric_digest"),
            field=f"campaign.blocks[{index}].quality_rubric_digest",
        )
        if rubric_digest != stable_digest(rubric):
            raise ValueError("composition-lift campaign block rubric drifted.")
        validate_factorial_block(
            block,
            source_control_plan=source_control_plan,
            rubric=rubric,
            rubric_digest=rubric_digest,
        )
        baseline = _mappings(
            block.get("baseline_cells"), field="campaign.block.baseline"
        )
        causal = _mappings(block.get("causal_cells"), field="campaign.block.causal")
        baseline_count += len(baseline)
        causal_count += len(causal)
    expected_counts = {
        "block_count": 5,
        "baseline_cell_count": baseline_count,
        "causal_cell_count": causal_count,
        "baseline_runner_cell_count": baseline_count,
        "baseline_blind_judge_cell_count": baseline_count,
        "causal_runner_cell_count": causal_count,
        "causal_blind_judge_cell_count": causal_count,
    }
    if campaign.get("counts") != expected_counts:
        raise ValueError("campaign counts do not match its cells.")
    identity = _identity(campaign, "campaign_id", "campaign_digest")
    if _digest(
        campaign.get("campaign_digest"), field="campaign.campaign_digest"
    ) != stable_digest(identity):
        raise ValueError("campaign digest drifted from its content.")
    if campaign.get("campaign_id") != "composition-lift-campaign-" + stable_digest(
        identity, 20
    ):
        raise ValueError("campaign id drifted from its content.")


def build_composition_lift_campaign(control_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Derive a fixed 5-block, 180-baseline, 360-causal no-call campaign."""

    controls = _validate_control_plan(control_plan)
    source_control_plan = {
        "control_plan_id": control_plan["control_plan_id"],
        "control_plan_digest": control_plan["control_plan_digest"],
        "run_manifest_id": control_plan["run_manifest_id"],
        "run_manifest_digest": control_plan["run_manifest_digest"],
    }
    blocks = [
        build_block(control, source_control_plan=source_control_plan)
        for control in controls
    ]
    campaign: dict[str, Any] = {
        "schema": COMPOSITION_LIFT_CAMPAIGN_SCHEMA,
        "campaign_mode": "pilot_only",
        "model_calls_authorized": False,
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
        "causal_claim_status": "not_evaluated",
        "source_control_plan": source_control_plan,
        "blocks": blocks,
        "counts": {
            "block_count": 5,
            "baseline_cell_count": 180,
            "causal_cell_count": 360,
            "baseline_runner_cell_count": 180,
            "baseline_blind_judge_cell_count": 180,
            "causal_runner_cell_count": 360,
            "causal_blind_judge_cell_count": 360,
        },
    }
    identity = _identity(campaign, "campaign_id", "campaign_digest")
    campaign["campaign_digest"] = stable_digest(identity)
    campaign["campaign_id"] = "composition-lift-campaign-" + stable_digest(identity, 20)
    validate_composition_lift_campaign(campaign)
    return campaign
