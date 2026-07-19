"""Validate and score repeated cell-level composition-lift evidence."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from tmcp_runtime.domain.composition_lift_campaign import (
    validate_composition_lift_campaign,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.safety.redaction import redact_sensitive_text


HOST_RESULTS_SCHEMA = "tmcp-composition-lift-host-results-v0.1"
EVALUATOR_ARTIFACTS_SCHEMA = "tmcp-composition-lift-evaluator-artifacts-v0.1"
SUMMARY_SCHEMA = "tmcp-composition-lift-summary-v0.1"
DISPATCH_BUNDLE_SCHEMA = "tmcp-composition-lift-dispatch-bundle-v0.1"
MAX_ARTIFACT_CHARS = 16_000
MAX_EVIDENCE_CHARS = 8_000
MAX_METADATA_CHARS = 512
_VARIANT_PREFIXES = ("singleton:", "leave_one_out:")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


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


def _text(value: object, *, field: str, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string.")
    result = value.strip()
    if maximum is not None and len(result) > maximum:
        raise ValueError(f"{field} exceeds the {maximum}-character boundary.")
    return result


def _digest(value: object, *, field: str) -> str:
    result = _text(value, field=field)
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest.")
    return result


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric.")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite.")
    return result


def _score(value: object, *, field: str) -> float:
    result = _number(value, field=field)
    if not 0 <= result <= 1:
        raise ValueError(f"{field} must be between zero and one.")
    return result


def _slot(value: object, *, field: str) -> int:
    if isinstance(value, bool) or value not in (1, 2, 3):
        raise ValueError(f"{field} must be configuration slot 1, 2, or 3.")
    return int(value)


def _replicate(value: object, *, field: str) -> int:
    if isinstance(value, bool) or value not in (1, 2):
        raise ValueError(f"{field} must be replicate 1 or 2.")
    return int(value)


def _assert_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] = set(),
    field: str,
) -> None:
    observed = set(value)
    if not required.issubset(observed) or not observed.issubset(required | optional):
        raise ValueError(f"{field} has an unexpected or missing field.")


def _source_control_plan(campaign: Mapping[str, Any]) -> dict[str, str]:
    source = dict(
        _mapping(
            campaign.get("source_control_plan"), field="campaign.source_control_plan"
        )
    )
    expected = {
        "control_plan_id",
        "control_plan_digest",
        "run_manifest_id",
        "run_manifest_digest",
    }
    if set(source) != expected:
        raise ValueError("campaign source_control_plan must be exact.")
    for key in ("control_plan_id", "run_manifest_id"):
        _text(source.get(key), field=f"campaign.source_control_plan.{key}")
    for key in ("control_plan_digest", "run_manifest_digest"):
        _digest(source.get(key), field=f"campaign.source_control_plan.{key}")
    return {key: str(value) for key, value in source.items()}


def _header(
    payload: Mapping[str, Any],
    *,
    schema: str,
    campaign: Mapping[str, Any],
    field: str,
) -> None:
    if payload.get("schema") != schema:
        raise ValueError(f"{field}.schema must be {schema}.")
    if payload.get("campaign_id") != campaign.get("campaign_id"):
        raise ValueError(f"{field}.campaign_id must match the campaign.")
    if _digest(
        payload.get("campaign_digest"), field=f"{field}.campaign_digest"
    ) != campaign.get("campaign_digest"):
        raise ValueError(f"{field}.campaign_digest must match the campaign.")
    if dict(
        _mapping(
            payload.get("source_control_plan"), field=f"{field}.source_control_plan"
        )
    ) != _source_control_plan(campaign):
        raise ValueError(f"{field}.source_control_plan must match the campaign.")


def _safe_text(
    value: object, *, field: str, maximum: int, allowed: Sequence[str]
) -> str:
    result = _text(value, field=field, maximum=maximum)
    protected = result
    for index, literal in enumerate(
        sorted({item for item in allowed if item}, key=len, reverse=True)
    ):
        protected = protected.replace(literal, f"TMCP_SAFE_{index}")
    _redacted, redactions = redact_sensitive_text(protected, enabled=True)
    if redactions:
        raise ValueError(f"{field} contains sensitive or high-entropy text.")
    return result


def _evidence(
    value: object,
    *,
    field: str,
    require_ids: bool,
    allowed: Sequence[str] = (),
) -> dict[str, Mapping[str, Any]]:
    records = _mappings(value, field=field)
    if not records or len(records) > 16:
        raise ValueError(f"{field} must contain one to sixteen records.")
    result: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        prefix = f"{field}[{index}]"
        required = {"media_type", "content"}
        if require_ids:
            required.add("evidence_id")
        _assert_keys(record, required=required, field=prefix)
        evidence_id = (
            _text(
                record.get("evidence_id"),
                field=f"{prefix}.evidence_id",
                maximum=MAX_METADATA_CHARS,
            )
            if require_ids
            else f"evidence-{index}"
        )
        if evidence_id in result:
            raise ValueError(f"{field} contains duplicate evidence ids.")
        _safe_text(
            record.get("media_type"),
            field=f"{prefix}.media_type",
            maximum=MAX_METADATA_CHARS,
            allowed=(),
        )
        _safe_text(
            record.get("content"),
            field=f"{prefix}.content",
            maximum=MAX_EVIDENCE_CHARS,
            allowed=allowed,
        )
        result[evidence_id] = record
    return result


def _campaign_cells(campaign: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    validate_composition_lift_campaign(campaign)
    index: dict[str, dict[str, Any]] = {}
    for block in _mappings(campaign.get("blocks"), field="campaign.blocks"):
        rubric = _mapping(
            block.get("quality_rubric"), field="campaign.block.quality_rubric"
        )
        rubric_dimensions = _mappings(
            rubric.get("dimensions"), field="campaign.block.rubric.dimensions"
        )
        dimensions = {
            _text(
                item.get("dimension_id"), field="campaign.rubric.dimension_id"
            ): float(item["weight"])
            for item in rubric_dimensions
        }
        for cohort, field in (
            ("baseline", "baseline_cells"),
            ("causal", "causal_cells"),
        ):
            for cell in _mappings(block.get(field), field=f"campaign.block.{field}"):
                cell_id = _text(cell.get("cell_id"), field="campaign.cell.cell_id")
                if cell_id in index:
                    raise ValueError("campaign cell ids must be globally unique.")
                runner_dispatch = next(
                    item
                    for item in _mappings(
                        block.get("runner_dispatches"),
                        field="campaign.block.runner_dispatches",
                    )
                    if item.get("runner_cell_id") == cell.get("runner_cell_id")
                )
                judge_dispatch = next(
                    item
                    for item in _mappings(
                        block.get("blind_judge_dispatches"),
                        field="campaign.block.blind_judge_dispatches",
                    )
                    if item.get("blind_judge_cell_id")
                    == cell.get("blind_judge_cell_id")
                )
                index[cell_id] = {
                    "cell": cell,
                    "block_id": str(block["block_id"]),
                    "fixture_id": str(block["fixture_id"]),
                    "cohort": cohort,
                    "variant_id": str(
                        _mapping(cell.get("binding"), field="campaign.cell.binding")[
                            "variant_id"
                        ]
                    ),
                    "configuration_slot": int(cell["configuration_slot"]),
                    "replicate_index": int(cell["replicate_index"]),
                    "runner_dispatch": runner_dispatch,
                    "judge_dispatch": judge_dispatch,
                    "dimensions": dimensions,
                }
    if len(index) != 540:
        raise ValueError("campaign must expose exactly 540 unique cells.")
    return index


def build_campaign_dispatch_bundle(
    campaign: Mapping[str, Any], *, audience: str
) -> dict[str, Any]:
    """Expose only opaque runner or judge dispatches to the external audience."""

    expected = _campaign_cells(campaign)
    if audience not in {"runner", "judge"}:
        raise ValueError("dispatch bundle audience must be runner or judge.")
    dispatch_key = "runner_dispatch" if audience == "runner" else "judge_dispatch"
    dispatches = [dict(context[dispatch_key]) for context in expected.values()]
    dispatches.sort(
        key=lambda item: str(
            item.get("runner_cell_id") or item.get("blind_judge_cell_id") or ""
        )
    )
    return {
        "schema": DISPATCH_BUNDLE_SCHEMA,
        "audience": audience,
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": campaign["campaign_digest"],
        "source_control_plan": _source_control_plan(campaign),
        "dispatches": dispatches,
    }


def _block_results(
    payload: Mapping[str, Any],
    *,
    field: str,
    expected: Mapping[str, dict[str, Any]],
) -> list[tuple[str, Mapping[str, Any]]]:
    blocks = _mappings(payload.get("blocks"), field=f"{field}.blocks")
    expected_blocks = {item["block_id"] for item in expected.values()}
    observed_blocks = {str(item.get("block_id") or "") for item in blocks}
    if observed_blocks != expected_blocks or len(blocks) != 5:
        raise ValueError(f"{field}.blocks must cover the five campaign blocks exactly.")
    cells: list[tuple[str, Mapping[str, Any]]] = []
    for block in blocks:
        block_id = _text(block.get("block_id"), field=f"{field}.block_id")
        block_cells = _mappings(block.get("cells"), field=f"{field}.{block_id}.cells")
        expected_block_cells = [
            item for item in expected.values() if item["block_id"] == block_id
        ]
        if len(block_cells) != len(expected_block_cells):
            raise ValueError(f"{field}.{block_id}.cells must cover 108 cells.")
        if str(block.get("fixture_id") or "") != expected_block_cells[0]["fixture_id"]:
            raise ValueError(f"{field}.{block_id}.fixture_id is not campaign-bound.")
        cells.extend((block_id, cell) for cell in block_cells)
    if len(cells) != 540:
        raise ValueError(f"{field}.blocks must contain exactly 540 cells.")
    return cells


def validate_campaign_host_results(
    campaign: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    """Validate every host artifact against one opaque campaign dispatch."""

    expected = _campaign_cells(campaign)
    _header(
        payload, schema=HOST_RESULTS_SCHEMA, campaign=campaign, field="host_results"
    )
    evidence_class = _text(
        payload.get("evidence_class"), field="host_results.evidence_class"
    )
    if evidence_class not in {"host_executed", "synthetic_test"}:
        raise ValueError("host_results.evidence_class is invalid.")
    result: dict[str, Mapping[str, Any]] = {}
    for block_id, item in _block_results(
        payload, field="host_results", expected=expected
    ):
        cell_id = _text(item.get("cell_id"), field="host.cell_id")
        if cell_id in result or cell_id not in expected:
            raise ValueError(
                "host results contain an unknown or duplicate campaign cell."
            )
        context = expected[cell_id]
        if context["block_id"] != block_id:
            raise ValueError(f"host.{cell_id} is assigned to the wrong campaign block.")
        _assert_keys(
            item,
            required={
                "cell_id",
                "runner_cell_id",
                "blind_judge_cell_id",
                "execution_input_ref",
                "runner_dispatch_digest",
                "configuration_slot",
                "replicate_index",
                "run_id",
                "outcome",
                "artifact",
                "evidence",
            },
            field=f"host.{cell_id}",
        )
        for key in ("runner_cell_id", "blind_judge_cell_id"):
            if item.get(key) != context["cell"][key]:
                raise ValueError(f"host.{cell_id}.{key} is not campaign-bound.")
        if (
            item.get("execution_input_ref")
            != context["runner_dispatch"]["execution_input_ref"]
        ):
            raise ValueError(
                f"host.{cell_id}.execution_input_ref is not campaign-bound."
            )
        if _digest(
            item.get("runner_dispatch_digest"),
            field=f"host.{cell_id}.runner_dispatch_digest",
        ) != stable_digest(dict(context["runner_dispatch"])):
            raise ValueError(f"host.{cell_id}.runner_dispatch_digest is invalid.")
        if (
            _slot(
                item.get("configuration_slot"),
                field=f"host.{cell_id}.configuration_slot",
            )
            != context["configuration_slot"]
        ):
            raise ValueError(
                f"host.{cell_id}.configuration_slot is not campaign-bound."
            )
        if (
            _replicate(
                item.get("replicate_index"), field=f"host.{cell_id}.replicate_index"
            )
            != context["replicate_index"]
        ):
            raise ValueError(f"host.{cell_id}.replicate_index is not campaign-bound.")
        if item.get("outcome") != "passed":
            raise ValueError(f"host.{cell_id}.outcome must be passed.")
        allowed = [
            cell_id,
            str(context["cell"]["binding"]["input_packet_digest"]),
            str(context["cell"]["binding"]["execution_recipe_digest"]),
        ]
        artifact = _safe_text(
            item.get("artifact"),
            field=f"host.{cell_id}.artifact",
            maximum=MAX_ARTIFACT_CHARS,
            allowed=allowed,
        )
        _evidence(
            item.get("evidence"),
            field=f"host.{cell_id}.evidence",
            require_ids=False,
            allowed=allowed,
        )
        result[cell_id] = {
            **dict(item),
            "artifact": artifact,
            "artifact_digest": stable_digest(artifact),
            "evidence_class": evidence_class,
        }
    if set(result) != set(expected):
        raise ValueError("host results must cover every campaign cell exactly once.")
    return result


def validate_campaign_evaluator_artifacts(
    campaign: Mapping[str, Any],
    payload: Mapping[str, Any],
    host_cells: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    """Validate blind-judge scores and bind them to host artifact digests."""

    expected = _campaign_cells(campaign)
    _header(
        payload,
        schema=EVALUATOR_ARTIFACTS_SCHEMA,
        campaign=campaign,
        field="evaluator_artifacts",
    )
    execution = _mapping(
        payload.get("evaluator_execution"),
        field="evaluator_artifacts.evaluator_execution",
    )
    execution_class = _text(
        execution.get("execution_class"), field="evaluator.execution_class"
    )
    if execution_class not in {"trusted_evaluator_execution", "synthetic_test"}:
        raise ValueError("evaluator.execution_class is invalid.")
    for key in ("executor_id", "execution_id"):
        _text(execution.get(key), field=f"evaluator.{key}", maximum=MAX_METADATA_CHARS)
    _text(
        execution.get("executed_at"),
        field="evaluator.executed_at",
        maximum=MAX_METADATA_CHARS,
    )
    if not _UTC_TIMESTAMP.fullmatch(str(execution["executed_at"])):
        raise ValueError("evaluator.executed_at must be a UTC timestamp.")
    result: dict[str, Mapping[str, Any]] = {}
    for block_id, item in _block_results(
        payload, field="evaluator_artifacts", expected=expected
    ):
        cell_id = _text(item.get("cell_id"), field="evaluator.cell_id")
        if cell_id in result or cell_id not in expected:
            raise ValueError(
                "evaluator artifacts contain an unknown or duplicate campaign cell."
            )
        context = expected[cell_id]
        if context["block_id"] != block_id:
            raise ValueError(
                f"evaluator.{cell_id} is assigned to the wrong campaign block."
            )
        _assert_keys(
            item,
            required={
                "cell_id",
                "blind_judge_cell_id",
                "artifact_slot_id",
                "blind_judge_dispatch_digest",
                "configuration_slot",
                "replicate_index",
                "execution_artifact_digest",
                "dimension_scores",
                "evidence",
                "dimension_evidence",
            },
            field=f"evaluator.{cell_id}",
        )
        if item.get("blind_judge_cell_id") != context["cell"]["blind_judge_cell_id"]:
            raise ValueError(
                f"evaluator.{cell_id}.blind_judge_cell_id is not campaign-bound."
            )
        if (
            item.get("artifact_slot_id")
            != context["judge_dispatch"]["artifact_slot_id"]
        ):
            raise ValueError(
                f"evaluator.{cell_id}.artifact_slot_id is not campaign-bound."
            )
        if _digest(
            item.get("blind_judge_dispatch_digest"),
            field=f"evaluator.{cell_id}.blind_judge_dispatch_digest",
        ) != stable_digest(dict(context["judge_dispatch"])):
            raise ValueError(
                f"evaluator.{cell_id}.blind_judge_dispatch_digest is invalid."
            )
        if (
            _slot(
                item.get("configuration_slot"),
                field=f"evaluator.{cell_id}.configuration_slot",
            )
            != context["configuration_slot"]
        ):
            raise ValueError(
                f"evaluator.{cell_id}.configuration_slot is not campaign-bound."
            )
        if (
            _replicate(
                item.get("replicate_index"),
                field=f"evaluator.{cell_id}.replicate_index",
            )
            != context["replicate_index"]
        ):
            raise ValueError(
                f"evaluator.{cell_id}.replicate_index is not campaign-bound."
            )
        host = host_cells.get(cell_id)
        if host is None or item.get("execution_artifact_digest") != host.get(
            "artifact_digest"
        ):
            raise ValueError(
                f"evaluator.{cell_id}.execution_artifact_digest does not match host output."
            )
        scores = _mapping(
            item.get("dimension_scores"), field=f"evaluator.{cell_id}.dimension_scores"
        )
        if set(scores) != set(context["dimensions"]):
            raise ValueError(
                f"evaluator.{cell_id}.dimension_scores must match the fixture rubric."
            )
        normalized_scores = {
            str(key): _score(value, field=f"evaluator.{cell_id}.dimension_scores.{key}")
            for key, value in scores.items()
        }
        allowed = [
            cell_id,
            str(context["cell"]["binding"]["input_packet_digest"]),
            str(context["cell"]["binding"]["execution_recipe_digest"]),
            str(host_cells[cell_id]["artifact_digest"]),
        ]
        evidence = _evidence(
            item.get("evidence"),
            field=f"evaluator.{cell_id}.evidence",
            require_ids=True,
            allowed=allowed,
        )
        dimension_evidence = _mappings(
            [
                {"dimension_id": key, "bindings": value}
                for key, value in _mapping(
                    item.get("dimension_evidence"),
                    field=f"evaluator.{cell_id}.dimension_evidence",
                ).items()
            ],
            field=f"evaluator.{cell_id}.dimension_evidence",
        )
        if {str(item["dimension_id"]) for item in dimension_evidence} != set(
            context["dimensions"]
        ):
            raise ValueError(
                f"evaluator.{cell_id}.dimension_evidence must cover the rubric."
            )
        for binding in dimension_evidence:
            bindings = _mappings(
                binding["bindings"],
                field=f"evaluator.{cell_id}.dimension_evidence.{binding['dimension_id']}",
            )
            if not bindings:
                raise ValueError(f"evaluator.{cell_id}.dimension_evidence is empty.")
            for entry in bindings:
                _assert_keys(
                    entry,
                    required={"requirement", "evidence_ids", "claim"},
                    field="dimension_evidence",
                )
                _safe_text(
                    entry.get("requirement"),
                    field="dimension_evidence.requirement",
                    maximum=MAX_EVIDENCE_CHARS,
                    allowed=allowed,
                )
                _safe_text(
                    entry.get("claim"),
                    field="dimension_evidence.claim",
                    maximum=MAX_EVIDENCE_CHARS,
                    allowed=allowed,
                )
                evidence_ids = entry.get("evidence_ids")
                if (
                    isinstance(evidence_ids, (str, bytes))
                    or not isinstance(evidence_ids, Sequence)
                    or not evidence_ids
                ):
                    raise ValueError(
                        "dimension_evidence.evidence_ids must be a nonempty sequence."
                    )
                if any(
                    str(evidence_id) not in evidence for evidence_id in evidence_ids
                ):
                    raise ValueError(
                        f"evaluator.{cell_id}.dimension_evidence references unknown evidence."
                    )
        quality_score = sum(
            context["dimensions"][key] * normalized_scores[key]
            for key in context["dimensions"]
        )
        result[cell_id] = {
            **dict(item),
            "dimension_scores": normalized_scores,
            "quality_score": round(quality_score, 4),
            "evaluator_execution_class": execution_class,
        }
    if set(result) != set(expected):
        raise ValueError(
            "evaluator artifacts must cover every campaign cell exactly once."
        )
    return result


def _variant_medians(
    cells: Sequence[Mapping[str, Any]], scores: Mapping[str, Mapping[str, Any]]
) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for cell in cells:
        variant_id = str(
            _mapping(cell["binding"], field="campaign.cell.binding")["variant_id"]
        )
        grouped.setdefault(variant_id, []).append(
            float(scores[str(cell["cell_id"])]["quality_score"])
        )
    return {
        variant: round(median(values), 4) for variant, values in sorted(grouped.items())
    }
