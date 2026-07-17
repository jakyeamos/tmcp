"""Hash-bound execution and evidence contracts for composition benchmarks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .composition_preflight import stable_digest


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _nonempty_strings(value: object, *, field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of strings.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain nonempty strings.")
        result.append(item.strip())
    if not result or len(set(result)) != len(result):
        raise ValueError(f"{field} must contain unique nonempty strings.")
    return result


def routing_input_digest(case: Mapping[str, Any]) -> str:
    """Bind one routing execution to the prompt presented to the host."""

    return stable_digest(
        {
            "case_id": str(case.get("case_id") or ""),
            "domain": str(case.get("domain") or ""),
            "objective": str(case.get("objective") or ""),
        }
    )


def required_behavioral_variants(selected_skill_ids: Sequence[str]) -> set[str]:
    return {
        "no_skill",
        "naive_union",
        "full_composition",
        "wrong_order",
        *(f"singleton:{skill_id}" for skill_id in selected_skill_ids),
        *(f"leave_one_out:{skill_id}" for skill_id in selected_skill_ids),
    }


def variant_skill_order(
    variant_id: str,
    selected_skill_ids: Sequence[str],
) -> list[str]:
    selected = list(selected_skill_ids)
    if variant_id == "no_skill":
        return []
    if variant_id in {"naive_union", "full_composition"}:
        return selected
    if variant_id == "wrong_order":
        return list(reversed(selected))
    prefix, separator, skill_id = variant_id.partition(":")
    if separator and prefix == "singleton" and skill_id in selected:
        return [skill_id]
    if separator and prefix == "leave_one_out" and skill_id in selected:
        return [item for item in selected if item != skill_id]
    raise ValueError(f"Unknown behavioral benchmark variant: {variant_id}")


def behavioral_input_digest(
    fixture: Mapping[str, Any],
    selected_skill_ids: Sequence[str],
    variant_id: str,
) -> str:
    """Bind a control execution to its fixture, sources, and skill ordering."""

    sources = fixture.get("skill_sources")
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        raise ValueError("Behavioral fixture skill_sources must be a sequence.")
    source_digests = sorted(
        stable_digest(str(source.get("content") or ""))
        for source in sources
        if isinstance(source, Mapping)
    )
    rubric = fixture.get("quality_rubric")
    return stable_digest(
        {
            "fixture_id": str(fixture.get("fixture_id") or ""),
            "domain": str(fixture.get("domain") or ""),
            "objective": str(fixture.get("objective") or ""),
            "variant_id": variant_id,
            "skill_order": variant_skill_order(variant_id, selected_skill_ids),
            "source_digests": source_digests,
            "rubric_digest": stable_digest(dict(rubric))
            if isinstance(rubric, Mapping)
            else "",
        }
    )


def variant_quality_score(
    quality_scores: Mapping[str, Any],
    variant_id: str,
) -> object:
    if variant_id in {"no_skill", "naive_union", "full_composition", "wrong_order"}:
        return quality_scores.get(variant_id)
    prefix, separator, skill_id = variant_id.partition(":")
    if not separator:
        return None
    collection_name = "singletons" if prefix == "singleton" else "leave_one_out"
    collection = quality_scores.get(collection_name)
    return collection.get(skill_id) if isinstance(collection, Mapping) else None


def execution_result_digest(
    variant_id: str,
    quality_score: object,
    dimension_scores: Mapping[str, Any],
) -> str:
    return stable_digest(
        {
            "variant_id": variant_id,
            "quality_score": quality_score,
            "dimension_scores": dict(dimension_scores),
        }
    )


def execution_record_digest(record: Mapping[str, Any]) -> str:
    return stable_digest(
        {
            key: value
            for key, value in record.items()
            if key not in {"execution_id", "execution_digest"}
        }
    )


def evidence_record_digest(record: Mapping[str, Any]) -> str:
    return stable_digest(
        {
            key: value
            for key, value in record.items()
            if key not in {"evidence_id", "content_digest", "execution_id"}
        }
    )


def _validate_evidence_manifest(
    *,
    field: str,
    execution_ids: set[str],
    raw_manifest: object,
) -> dict[str, Mapping[str, Any]]:
    evidence: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(
        _mapping_list(raw_manifest, field=field),
        start=1,
    ):
        record_field = f"{field}[{index}]"
        evidence_id = str(record.get("evidence_id") or "").strip()
        execution_id = str(record.get("execution_id") or "").strip()
        content = record.get("content")
        content_digest = str(record.get("content_digest") or "").strip()
        media_type = str(record.get("media_type") or "").strip()
        if (
            not evidence_id
            or not execution_id
            or not isinstance(content, str)
            or not content
        ):
            raise ValueError(
                f"{record_field} requires evidence_id, execution_id, and content."
            )
        if not media_type:
            raise ValueError(f"{record_field}.media_type is required.")
        if execution_id not in execution_ids:
            raise ValueError(f"{record_field} references an unknown execution.")
        expected_content_digest = stable_digest(content)
        if content_digest != expected_content_digest:
            raise ValueError(f"{record_field}.content_digest does not match content.")
        expected_evidence_id = "evidence-" + evidence_record_digest(record)[:20]
        if evidence_id != expected_evidence_id:
            raise ValueError(f"{record_field}.evidence_id is not content-derived.")
        if evidence_id in evidence:
            raise ValueError(f"{field} contains duplicate evidence_id {evidence_id}.")
        evidence[evidence_id] = record
    if not evidence:
        raise ValueError(f"{field} must not be empty.")
    return evidence


def _validate_execution_records(
    *,
    field: str,
    raw_manifest: object,
    required_variants: set[str],
) -> dict[str, Mapping[str, Any]]:
    records: dict[str, Mapping[str, Any]] = {}
    variants: set[str] = set()
    for index, record in enumerate(
        _mapping_list(raw_manifest, field=field),
        start=1,
    ):
        record_field = f"{field}[{index}]"
        execution_id = str(record.get("execution_id") or "").strip()
        variant_id = str(record.get("variant_id") or "").strip()
        artifact = record.get("artifact")
        artifact_digest = str(record.get("artifact_digest") or "").strip()
        receipt = record.get("run_receipt")
        receipt_digest = str(record.get("receipt_digest") or "").strip()
        execution_digest = str(record.get("execution_digest") or "").strip()
        if (
            not execution_id
            or not variant_id
            or not isinstance(artifact, str)
            or not artifact
        ):
            raise ValueError(
                f"{record_field} requires execution_id, variant_id, and artifact."
            )
        if not isinstance(receipt, Mapping):
            raise ValueError(f"{record_field}.run_receipt must be an object.")
        if artifact_digest != stable_digest(artifact):
            raise ValueError(f"{record_field}.artifact_digest does not match artifact.")
        if receipt_digest != stable_digest(dict(receipt)):
            raise ValueError(
                f"{record_field}.receipt_digest does not match run_receipt."
            )
        expected_execution_digest = execution_record_digest(record)
        if execution_digest != expected_execution_digest:
            raise ValueError(f"{record_field}.execution_digest is invalid.")
        if execution_id != "execution-" + expected_execution_digest[:20]:
            raise ValueError(f"{record_field}.execution_id is not content-derived.")
        if execution_id in records or variant_id in variants:
            raise ValueError(
                f"{field} contains duplicate execution or variant identity."
            )
        _nonempty_strings(
            record.get("evidence_ids"), field=f"{record_field}.evidence_ids"
        )
        records[execution_id] = record
        variants.add(variant_id)
    if variants != required_variants:
        raise ValueError(
            f"{field} must cover every execution variant exactly; "
            f"missing={sorted(required_variants - variants)}, "
            f"unexpected={sorted(variants - required_variants)}."
        )
    return records


def _validate_execution_evidence_links(
    *,
    field: str,
    executions: Mapping[str, Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
) -> None:
    referenced: set[str] = set()
    for execution_id, record in executions.items():
        evidence_ids = _nonempty_strings(
            record.get("evidence_ids"),
            field=f"{field}.{execution_id}.evidence_ids",
        )
        for evidence_id in evidence_ids:
            evidence_record = evidence.get(evidence_id)
            if evidence_record is None:
                raise ValueError(f"{field} references unknown evidence {evidence_id}.")
            if str(evidence_record.get("execution_id") or "") != execution_id:
                raise ValueError(f"{field} evidence is bound to a different execution.")
        referenced.update(evidence_ids)
    unexpected = sorted(set(evidence).difference(referenced))
    if unexpected:
        raise ValueError(f"{field} contains unreferenced evidence: {unexpected}.")


def validate_routing_manifests(
    case: Mapping[str, Any],
    observation: Mapping[str, Any],
    selected_skill_ids: Sequence[str],
) -> None:
    field = f"{case.get('case_id')}.execution_manifest"
    executions = _validate_execution_records(
        field=field,
        raw_manifest=observation.get("execution_manifest"),
        required_variants={"routing"},
    )
    record = next(iter(executions.values()))
    if str(record.get("input_digest") or "") != routing_input_digest(case):
        raise ValueError(f"{field} input_digest does not match the golden prompt.")
    expected_result_digest = stable_digest(
        {"selected_skill_ids": list(selected_skill_ids)}
    )
    if str(record.get("result_digest") or "") != expected_result_digest:
        raise ValueError(f"{field} result_digest does not match routing selection.")
    receipt = record["run_receipt"]
    if not isinstance(receipt, Mapping) or receipt.get("outcome") != "passed":
        raise ValueError(f"{field} requires a passing execution receipt.")
    if receipt.get("variant_id") != "routing":
        raise ValueError(f"{field} receipt variant does not match routing.")
    if receipt.get("artifact_digest") != record.get("artifact_digest"):
        raise ValueError(f"{field} receipt does not bind the execution artifact.")
    evidence = _validate_evidence_manifest(
        field=f"{case.get('case_id')}.evidence_manifest",
        execution_ids=set(executions),
        raw_manifest=observation.get("evidence_manifest"),
    )
    _validate_execution_evidence_links(
        field=field, executions=executions, evidence=evidence
    )


def validate_behavioral_manifests(
    fixture: Mapping[str, Any],
    observation: Mapping[str, Any],
    selected_skill_ids: Sequence[str],
) -> None:
    fixture_id = str(fixture.get("fixture_id") or "")
    required_variants = required_behavioral_variants(selected_skill_ids)
    field = f"{fixture_id}.execution_manifest"
    executions = _validate_execution_records(
        field=field,
        raw_manifest=observation.get("execution_manifest"),
        required_variants=required_variants,
    )
    by_variant = {str(record["variant_id"]): record for record in executions.values()}
    quality_scores = observation.get("quality_scores")
    provenance = observation.get("evaluation_provenance")
    if not isinstance(quality_scores, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError(f"{fixture_id} quality and evaluator provenance are required.")
    dimension_scores = provenance.get("variant_dimension_scores")
    variant_evidence = provenance.get("variant_evidence")
    if not isinstance(dimension_scores, Mapping) or not isinstance(
        variant_evidence, Mapping
    ):
        raise ValueError(f"{fixture_id} evaluator variant provenance is required.")
    for variant_id, record in by_variant.items():
        if str(record.get("input_digest") or "") != behavioral_input_digest(
            fixture,
            selected_skill_ids,
            variant_id,
        ):
            raise ValueError(f"{field}.{variant_id} input_digest is invalid.")
        scores = dimension_scores.get(variant_id)
        if not isinstance(scores, Mapping):
            raise ValueError(f"{field}.{variant_id} dimension scores are missing.")
        expected_result_digest = execution_result_digest(
            variant_id,
            variant_quality_score(quality_scores, variant_id),
            scores,
        )
        if str(record.get("result_digest") or "") != expected_result_digest:
            raise ValueError(f"{field}.{variant_id} result_digest is invalid.")
        receipt = record["run_receipt"]
        if not isinstance(receipt, Mapping) or receipt.get("outcome") != "passed":
            raise ValueError(f"{field}.{variant_id} requires a passing receipt.")
        if receipt.get("variant_id") != variant_id:
            raise ValueError(f"{field}.{variant_id} receipt variant is invalid.")
        if receipt.get("artifact_digest") != record.get("artifact_digest"):
            raise ValueError(
                f"{field}.{variant_id} receipt does not bind its artifact."
            )
        if variant_id == "full_composition":
            if receipt.get("tmcp_run_receipt") != observation.get("run_receipt"):
                raise ValueError(
                    f"{field}.full_composition must bind the TMCP run receipt."
                )
        expected_evidence_ids = variant_evidence.get(variant_id)
        if record.get("evidence_ids") != expected_evidence_ids:
            raise ValueError(
                f"{field}.{variant_id} evidence must match evaluator provenance."
            )
    evidence = _validate_evidence_manifest(
        field=f"{fixture_id}.evidence_manifest",
        execution_ids=set(executions),
        raw_manifest=observation.get("evidence_manifest"),
    )
    _validate_execution_evidence_links(
        field=field, executions=executions, evidence=evidence
    )
