"""Pure construction and validation support for composition-lift campaigns."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .composition_benchmark_manifests import variant_skill_order
from .composition_preflight import stable_digest


BASELINE_CONFIGURATION_SLOTS = (1, 2, 3)
REPLICATE_INDICES = (1, 2)
MAX_SKILLS_PER_BLOCK = 4
RUNNER_DISPATCH_SCHEMA = "tmcp-composition-lift-runner-dispatch-v0.1"
BLIND_JUDGE_DISPATCH_SCHEMA = "tmcp-composition-lift-blind-judge-dispatch-v0.1"
RUNNER_INSTRUCTION = (
    "Complete the supplied isolated task using only its supplied execution input and "
    "recipe reference. Treat task_context evidence as fixture-supplied preconditions, "
    "not as host-executed evidence; keep any host-run verification separate and label "
    "missing checks blocked or unverified. Return one bounded artifact and concrete "
    "verification evidence. Do not add unstated materials or persist a receipt."
)
BLIND_JUDGE_INSTRUCTION = (
    "Score only the presented artifact against the supplied rubric. Cite artifact "
    "evidence for every dimension, report uncertainty, and do not infer unprovided "
    "task setup or execution history."
)
_BLIND_LABELS = frozenset(
    {
        "variant",
        "hypothesis",
        "baseline",
        "causal",
        "full_composition",
        "no_skill",
        "naive_union",
        "wrong_order",
        "singleton",
        "leave_one_out",
    }
)
_HEX_CHARS = frozenset("0123456789abcdef")


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _mappings(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    return [
        _mapping(item, field=f"{field}[{index}]") for index, item in enumerate(value)
    ]


def _text(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required.")
    return result


def _digest(value: object, *, field: str, length: int = 64) -> str:
    result = _text(value, field=field)
    if len(result) != length or any(
        character not in _HEX_CHARS for character in result
    ):
        raise ValueError(f"{field} must be a {length}-character lowercase digest.")
    return result


def _skill_ids(
    value: object, *, field: str, expected_length: int | None = None
) -> list[str]:
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


def all_variant_ids(selected_skill_ids: Sequence[str]) -> list[str]:
    """Return the fixed twelve-arm benchmark matrix in compiler order."""

    return [
        "no_skill",
        "naive_union",
        *(f"singleton:{skill_id}" for skill_id in selected_skill_ids),
        "full_composition",
        *(f"leave_one_out:{skill_id}" for skill_id in selected_skill_ids),
        "wrong_order",
    ]


def baseline_variant_ids(selected_skill_ids: Sequence[str]) -> list[str]:
    """Return the no-skill, naive-union, and singleton baseline arms."""

    return [
        "no_skill",
        "naive_union",
        *(f"singleton:{skill_id}" for skill_id in selected_skill_ids),
    ]


def _binding(
    control: Mapping[str, Any],
    variant: Mapping[str, Any],
    source_control_plan: Mapping[str, Any],
) -> dict[str, Any]:
    recipe = _mapping(variant.get("execution_recipe"), field="variant.execution_recipe")
    binding = {
        "fixture_id": control["fixture_id"],
        "request_id": control["request_id"],
        "task_context_digest": control["task_context_digest"],
        "variant_id": variant["variant_id"],
        "input_packet_digest": variant["input_packet_digest"],
        "execution_recipe_digest": variant["execution_recipe_digest"],
        "source_composition_plan_digest": recipe["source_composition_plan_digest"],
        "graph_digest": control["graph_digest"],
        "selected_skill_ids": list(control["selected_skill_ids"]),
        "ordered_skill_ids": list(variant["ordered_skill_ids"]),
        "quality_rubric_digest": control["quality_rubric_digest"],
        "source_control_plan_id": source_control_plan["control_plan_id"],
        "source_control_plan_digest": source_control_plan["control_plan_digest"],
        "source_run_manifest_id": source_control_plan["run_manifest_id"],
        "source_run_manifest_digest": source_control_plan["run_manifest_digest"],
    }
    return {**binding, "binding_digest": stable_digest(binding)}


def _cell_id(
    binding: Mapping[str, Any],
    *,
    cohort: str,
    configuration_slot: int,
    replicate_index: int,
) -> str:
    identity = {
        "cohort": cohort,
        "binding_digest": binding["binding_digest"],
        "configuration_slot": configuration_slot,
        "replicate_index": replicate_index,
    }
    return "composition-lift-cell-" + stable_digest(identity, 20)


def _runner_dispatch(
    *, runner_cell_id: str, binding: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema": RUNNER_DISPATCH_SCHEMA,
        "runner_cell_id": runner_cell_id,
        "execution_input_ref": "execution-input-"
        + stable_digest({"binding_digest": binding["binding_digest"]}, 20),
        "instruction": RUNNER_INSTRUCTION,
        "instruction_digest": stable_digest(RUNNER_INSTRUCTION),
    }


def _blind_judge_dispatch(
    *,
    blind_judge_cell_id: str,
    cell_id: str,
    rubric: Mapping[str, Any],
    rubric_digest: str,
) -> dict[str, Any]:
    return {
        "schema": BLIND_JUDGE_DISPATCH_SCHEMA,
        "blind_judge_cell_id": blind_judge_cell_id,
        "artifact_slot_id": "artifact-slot-" + stable_digest({"cell_id": cell_id}, 20),
        "quality_rubric": dict(rubric),
        "quality_rubric_digest": rubric_digest,
        "instruction": BLIND_JUDGE_INSTRUCTION,
        "instruction_digest": stable_digest(BLIND_JUDGE_INSTRUCTION),
    }


def _cell(
    binding: Mapping[str, Any],
    *,
    cohort: str,
    configuration_slot: int,
    replicate_index: int,
    rubric: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cell_id = _cell_id(
        binding,
        cohort=cohort,
        configuration_slot=configuration_slot,
        replicate_index=replicate_index,
    )
    runner_cell_id = "composition-lift-runner-" + stable_digest(
        {"cell_id": cell_id}, 20
    )
    blind_judge_cell_id = "composition-lift-judge-" + stable_digest(
        {"cell_id": cell_id}, 20
    )
    cell = {
        "cell_id": cell_id,
        "configuration_slot": configuration_slot,
        "replicate_index": replicate_index,
        "binding": dict(binding),
        "runner_cell_id": runner_cell_id,
        "blind_judge_cell_id": blind_judge_cell_id,
    }
    return (
        cell,
        _runner_dispatch(runner_cell_id=runner_cell_id, binding=binding),
        _blind_judge_dispatch(
            blind_judge_cell_id=blind_judge_cell_id,
            cell_id=cell_id,
            rubric=rubric,
            rubric_digest=str(binding["quality_rubric_digest"]),
        ),
    )


def _comparator_variant(variant_id: str) -> str:
    if variant_id in {"no_skill", "naive_union"} or variant_id.startswith("singleton:"):
        return variant_id
    return "naive_union" if variant_id == "full_composition" else "full_composition"


def build_block(
    control: Mapping[str, Any], *, source_control_plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Construct one fixed factorial block from an already-validated control."""

    selected_skill_ids = list(control["selected_skill_ids"])
    baseline_cells: list[dict[str, Any]] = []
    causal_cells: list[dict[str, Any]] = []
    runner_dispatches: list[dict[str, Any]] = []
    blind_judge_dispatches: list[dict[str, Any]] = []
    baseline_index: dict[tuple[str, int, int], str] = {}
    causal_index: dict[tuple[str, int, int], int] = {}
    for variant_id in baseline_variant_ids(selected_skill_ids):
        binding = _binding(
            control, control["variants"][variant_id], source_control_plan
        )
        for configuration_slot in BASELINE_CONFIGURATION_SLOTS:
            for replicate_index in REPLICATE_INDICES:
                cell, runner, judge = _cell(
                    binding,
                    cohort="baseline",
                    configuration_slot=configuration_slot,
                    replicate_index=replicate_index,
                    rubric=control["quality_rubric"],
                )
                baseline_cells.append(cell)
                runner_dispatches.append(runner)
                blind_judge_dispatches.append(judge)
                baseline_index[(variant_id, configuration_slot, replicate_index)] = (
                    cell["cell_id"]
                )
    for variant_id in all_variant_ids(selected_skill_ids):
        binding = _binding(
            control, control["variants"][variant_id], source_control_plan
        )
        for configuration_slot in BASELINE_CONFIGURATION_SLOTS:
            for replicate_index in REPLICATE_INDICES:
                causal_index[(variant_id, configuration_slot, replicate_index)] = len(
                    causal_cells
                )
                cell, runner, judge = _cell(
                    binding,
                    cohort="causal",
                    configuration_slot=configuration_slot,
                    replicate_index=replicate_index,
                    rubric=control["quality_rubric"],
                )
                causal_cells.append(cell)
                runner_dispatches.append(runner)
                blind_judge_dispatches.append(judge)
    for cell in causal_cells:
        key = (
            cell["binding"]["variant_id"],
            cell["configuration_slot"],
            cell["replicate_index"],
        )
        comparator_key = (_comparator_variant(key[0]), key[1], key[2])
        comparator_id = (
            baseline_index.get(comparator_key)
            if key[0] in baseline_variant_ids(selected_skill_ids)
            else None
        )
        if comparator_id is None:
            comparator_index = causal_index.get(comparator_key)
            if comparator_index is None:
                raise ValueError(
                    "Causal comparator is not represented in the campaign."
                )
            comparator_id = causal_cells[comparator_index]["cell_id"]
        cell["comparator_cell_id"] = comparator_id
    identity = {
        "fixture_id": control["fixture_id"],
        "request_id": control["request_id"],
        "quality_rubric_digest": control["quality_rubric_digest"],
        "graph_digest": control["graph_digest"],
    }
    return {
        "block_id": "composition-lift-block-" + stable_digest(identity, 20),
        "fixture_id": control["fixture_id"],
        "request_id": control["request_id"],
        "quality_rubric": control["quality_rubric"],
        "quality_rubric_digest": control["quality_rubric_digest"],
        "baseline_cells": baseline_cells,
        "causal_cells": causal_cells,
        "runner_dispatches": runner_dispatches,
        "blind_judge_dispatches": blind_judge_dispatches,
    }


def _label_tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    tokens = set(re.findall(r"[a-z0-9_]+", normalized))
    tokens.update(token for item in tuple(tokens) for token in item.split("_") if token)
    return tokens


def _assert_label_free(value: object, *, field: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _assert_label_free(str(key), field=f"{field}.key")
            _assert_label_free(nested, field=f"{field}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _assert_label_free(nested, field=f"{field}[{index}]")
        return
    if isinstance(value, str):
        labels = _BLIND_LABELS.intersection(_label_tokens(value))
        if labels:
            raise ValueError(f"{field} leaks condition labels: {sorted(labels)}.")


def _slot(value: object, *, field: str, allowed: tuple[int, ...]) -> int:
    if isinstance(value, bool) or value not in allowed:
        raise ValueError(f"{field} must be one of {allowed}.")
    return int(value)


def _validate_binding(
    binding: Mapping[str, Any],
    *,
    field: str,
    fixture_id: str,
    request_id: str,
    selected_skill_ids: list[str],
    rubric_digest: str,
    graph_digest: str,
    source_control_plan: Mapping[str, Any],
) -> str:
    if (
        binding.get("fixture_id") != fixture_id
        or binding.get("request_id") != request_id
    ):
        raise ValueError(f"{field} is bound to a different fixture request.")
    if (
        _skill_ids(
            binding.get("selected_skill_ids"),
            field=f"{field}.selected_skill_ids",
            expected_length=MAX_SKILLS_PER_BLOCK,
        )
        != selected_skill_ids
    ):
        raise ValueError(f"{field} selected skills drifted from the block control.")
    variant_id = _text(binding.get("variant_id"), field=f"{field}.variant_id")
    if _skill_ids(
        binding.get("ordered_skill_ids"), field=f"{field}.ordered_skill_ids"
    ) != variant_skill_order(variant_id, selected_skill_ids):
        raise ValueError(f"{field} ordered skills drifted from the canonical control.")
    for key, length in (
        ("task_context_digest", 64),
        ("input_packet_digest", 64),
        ("execution_recipe_digest", 64),
        ("source_composition_plan_digest", 64),
        ("graph_digest", 32),
        ("quality_rubric_digest", 64),
        ("source_control_plan_digest", 64),
        ("source_run_manifest_digest", 64),
    ):
        _digest(binding.get(key), field=f"{field}.{key}", length=length)
    if binding.get("graph_digest") != graph_digest:
        raise ValueError(f"{field} graph provenance drifted from the block control.")
    if binding.get("quality_rubric_digest") != rubric_digest:
        raise ValueError(f"{field} rubric provenance drifted from the block control.")
    expected_controller = {
        "source_control_plan_id": source_control_plan["control_plan_id"],
        "source_control_plan_digest": source_control_plan["control_plan_digest"],
        "source_run_manifest_id": source_control_plan["run_manifest_id"],
        "source_run_manifest_digest": source_control_plan["run_manifest_digest"],
    }
    if any(
        binding.get(key) != expected for key, expected in expected_controller.items()
    ):
        raise ValueError(
            f"{field} controller provenance drifted from source_control_plan."
        )
    if _digest(
        binding.get("binding_digest"), field=f"{field}.binding_digest"
    ) != stable_digest(
        {key: value for key, value in binding.items() if key != "binding_digest"}
    ):
        raise ValueError(f"{field} binding digest drifted.")
    return variant_id


def _validate_dispatches(
    *,
    block: Mapping[str, Any],
    cells: Sequence[Mapping[str, Any]],
    rubric: Mapping[str, Any],
    rubric_digest: str,
) -> None:
    runners = _mappings(
        block.get("runner_dispatches"), field="campaign.block.runner_dispatches"
    )
    judges = _mappings(
        block.get("blind_judge_dispatches"),
        field="campaign.block.blind_judge_dispatches",
    )
    if len(runners) != len(cells) or len(judges) != len(cells):
        raise ValueError(
            "campaign block dispatch coverage must match its controller cells."
        )
    runner_by_id = {
        _text(
            item.get("runner_cell_id"), field="campaign.runner_dispatch.runner_cell_id"
        ): item
        for item in runners
    }
    judge_by_id = {
        _text(
            item.get("blind_judge_cell_id"),
            field="campaign.judge_dispatch.blind_judge_cell_id",
        ): item
        for item in judges
    }
    controller_runner_ids = {str(cell["runner_cell_id"]) for cell in cells}
    controller_judge_ids = {str(cell["blind_judge_cell_id"]) for cell in cells}
    if len(runner_by_id) != len(cells) or set(runner_by_id) != controller_runner_ids:
        raise ValueError(
            "campaign runner dispatches must cover every controller cell once."
        )
    if len(judge_by_id) != len(cells) or set(judge_by_id) != controller_judge_ids:
        raise ValueError(
            "campaign judge dispatches must cover every controller cell once."
        )
    for cell in cells:
        binding = _mapping(cell.get("binding"), field="campaign.cell.binding")
        cell_id = _text(cell.get("cell_id"), field="campaign.cell.cell_id")
        runner_id = _text(
            cell.get("runner_cell_id"), field="campaign.cell.runner_cell_id"
        )
        judge_id = _text(
            cell.get("blind_judge_cell_id"), field="campaign.cell.blind_judge_cell_id"
        )
        expected_runner = _runner_dispatch(runner_cell_id=runner_id, binding=binding)
        expected_judge = _blind_judge_dispatch(
            blind_judge_cell_id=judge_id,
            cell_id=cell_id,
            rubric=rubric,
            rubric_digest=rubric_digest,
        )
        if dict(runner_by_id[runner_id]) != expected_runner:
            raise ValueError(
                "campaign runner dispatch is not a narrow host-facing view."
            )
        if dict(judge_by_id[judge_id]) != expected_judge:
            raise ValueError(
                "campaign judge dispatch is not a narrow host-facing view."
            )
    _assert_label_free(runners, field="campaign.block.runner_dispatches")
    _assert_label_free(judges, field="campaign.block.blind_judge_dispatches")


def validate_factorial_block(
    block: Mapping[str, Any],
    *,
    source_control_plan: Mapping[str, Any],
    rubric: Mapping[str, Any],
    rubric_digest: str,
) -> None:
    """Require exact factorial coverage, deterministic wiring, and blind dispatches."""

    baseline = _mappings(
        block.get("baseline_cells"), field="campaign.block.baseline_cells"
    )
    causal = _mappings(block.get("causal_cells"), field="campaign.block.causal_cells")
    if len(baseline) != 36 or len(causal) != 72:
        raise ValueError(
            "every campaign block requires 36 baseline and 72 causal cells."
        )
    fixture_id = _text(block.get("fixture_id"), field="campaign.block.fixture_id")
    request_id = _text(block.get("request_id"), field="campaign.block.request_id")
    first_binding = _mapping(baseline[0].get("binding"), field="campaign.block.binding")
    selected_skill_ids = _skill_ids(
        first_binding.get("selected_skill_ids"),
        field="campaign.block.selected_skill_ids",
        expected_length=MAX_SKILLS_PER_BLOCK,
    )
    graph_digest = _digest(
        first_binding.get("graph_digest"),
        field="campaign.block.graph_digest",
        length=32,
    )
    seen_cell_ids: set[str] = set()

    def signatures(
        cells: Sequence[Mapping[str, Any]], *, cohort: str
    ) -> dict[tuple[str, int, int], Mapping[str, Any]]:
        result: dict[tuple[str, int, int], Mapping[str, Any]] = {}
        for index, cell in enumerate(cells):
            field = f"campaign.block.{cohort}_cells[{index}]"
            binding = _mapping(cell.get("binding"), field=f"{field}.binding")
            variant_id = _validate_binding(
                binding,
                field=f"{field}.binding",
                fixture_id=fixture_id,
                request_id=request_id,
                selected_skill_ids=selected_skill_ids,
                rubric_digest=rubric_digest,
                graph_digest=graph_digest,
                source_control_plan=source_control_plan,
            )
            configuration_slot = _slot(
                cell.get("configuration_slot"),
                field=f"{field}.configuration_slot",
                allowed=BASELINE_CONFIGURATION_SLOTS,
            )
            replicate_index = _slot(
                cell.get("replicate_index"),
                field=f"{field}.replicate_index",
                allowed=REPLICATE_INDICES,
            )
            cell_id = _text(cell.get("cell_id"), field=f"{field}.cell_id")
            expected_cell_id = _cell_id(
                binding,
                cohort=cohort,
                configuration_slot=configuration_slot,
                replicate_index=replicate_index,
            )
            if cell_id != expected_cell_id:
                raise ValueError(
                    f"{field}.cell_id drifted from its controller binding."
                )
            expected_runner_id = "composition-lift-runner-" + stable_digest(
                {"cell_id": cell_id}, 20
            )
            expected_judge_id = "composition-lift-judge-" + stable_digest(
                {"cell_id": cell_id}, 20
            )
            if cell.get("runner_cell_id") != expected_runner_id:
                raise ValueError(
                    f"{field}.runner_cell_id drifted from its controller cell."
                )
            if cell.get("blind_judge_cell_id") != expected_judge_id:
                raise ValueError(
                    f"{field}.blind_judge_cell_id drifted from its controller cell."
                )
            signature = (variant_id, configuration_slot, replicate_index)
            if signature in result:
                raise ValueError("campaign block has duplicate factorial coordinates.")
            if cell_id in seen_cell_ids:
                raise ValueError("campaign cell ids must be unique and nonempty.")
            seen_cell_ids.add(cell_id)
            result[signature] = cell
        return result

    baseline_by_signature = signatures(baseline, cohort="baseline")
    causal_by_signature = signatures(causal, cohort="causal")
    expected_baseline = {
        (variant_id, slot, replicate)
        for variant_id in baseline_variant_ids(selected_skill_ids)
        for slot in BASELINE_CONFIGURATION_SLOTS
        for replicate in REPLICATE_INDICES
    }
    expected_causal = {
        (variant_id, slot, replicate)
        for variant_id in all_variant_ids(selected_skill_ids)
        for slot in BASELINE_CONFIGURATION_SLOTS
        for replicate in REPLICATE_INDICES
    }
    if set(baseline_by_signature) != expected_baseline:
        raise ValueError("campaign block baseline factorial coverage is incomplete.")
    if set(causal_by_signature) != expected_causal:
        raise ValueError("campaign block causal factorial coverage is incomplete.")
    for signature, cell in causal_by_signature.items():
        comparator_variant = _comparator_variant(signature[0])
        comparator = (
            baseline_by_signature.get((comparator_variant, *signature[1:]))
            if signature[0] in baseline_variant_ids(selected_skill_ids)
            else causal_by_signature.get((comparator_variant, *signature[1:]))
        )
        if comparator is None or cell.get("comparator_cell_id") != comparator.get(
            "cell_id"
        ):
            raise ValueError(
                "campaign causal comparator drifted from the factorial control."
            )
    block_identity = {
        "fixture_id": fixture_id,
        "request_id": request_id,
        "quality_rubric_digest": rubric_digest,
        "graph_digest": graph_digest,
    }
    if block.get("block_id") != "composition-lift-block-" + stable_digest(
        block_identity, 20
    ):
        raise ValueError("campaign block id drifted from its controller provenance.")
    _validate_dispatches(
        block=block,
        cells=[*baseline, *causal],
        rubric=rubric,
        rubric_digest=rubric_digest,
    )
