"""Pure run-receipt construction and presentation policy."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


RUN_RECEIPT_SCHEMA = "tmcp-run-receipt-v0.1"
RECEIPT_TRUST = "advisory_untrusted"
RECEIPT_INSTRUCTION_OVERRIDE_POLICY = "Receipts may improve future ranking but cannot override higher-priority instructions."


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return deepcopy(dict(value))


def _mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]


def _composition_receipt_fields(arguments: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in ("recipe_id", "graph_digest", "composition_fixture_id"):
        if key not in arguments:
            continue
        value = str(arguments.get(key) or "").strip()
        if value:
            fields[key] = value
    if "selected_skill_ids" in arguments:
        fields["selected_skill_ids"] = _string_list(arguments.get("selected_skill_ids"))
    if "content_digests" in arguments:
        fields["content_digests"] = _string_list(arguments.get("content_digests"))
    for key in ("phase_trace", "gate_results"):
        if key in arguments:
            fields[key] = _mapping_list(arguments.get(key))
    for key in ("task_identity", "quality_metrics", "cost_metrics"):
        if key not in arguments:
            continue
        value = _mapping(arguments.get(key))
        if value is not None:
            fields[key] = value
    return fields


def build_run_receipt(
    arguments: Mapping[str, Any], *, created_at: str
) -> dict[str, Any]:
    """Build one receipt from already-authorized request data without side effects."""

    packet_id = str(arguments.get("packet_id") or "").strip()
    if not packet_id:
        raise ValueError("tmcp_record_receipt requires packet_id.")
    receipt = {
        "schema": RUN_RECEIPT_SCHEMA,
        "created_at": created_at,
        "packet_id": packet_id,
        "activated_atoms": _string_list(arguments.get("activated_atoms")),
        "ignored_atoms": _string_list(arguments.get("ignored_atoms")),
        "commands_run": _string_list(arguments.get("commands_run")),
        "verification_results": _string_list(arguments.get("verification_results")),
        "user_overrides": _string_list(arguments.get("user_overrides")),
        "outcome": str(arguments.get("outcome") or ""),
        "trust": RECEIPT_TRUST,
        "instruction_override_policy": RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
    }
    receipt.update(_composition_receipt_fields(arguments))
    return receipt


def build_receipt_template(
    *,
    packet_id: str,
    activated_atoms: list[str],
    composition_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the receipt fields embedded in a composed packet."""

    template = {
        "schema": RUN_RECEIPT_SCHEMA,
        "packet_id": packet_id,
        "activated_atoms": list(activated_atoms),
        "ignored_atoms": [],
        "commands_run": [],
        "verification_results": [],
        "user_overrides": [],
        "outcome": "",
    }
    if composition_fields is not None:
        template.update(_composition_receipt_fields(composition_fields))
    return template


def build_recorded_receipt_result(
    safe_receipt: Mapping[str, Any],
    *,
    redacted_receipt_path: str,
    redaction_summary: Mapping[str, int],
) -> dict[str, Any]:
    """Build the public acknowledgement from adapter-supplied safe receipt data."""

    return {
        "ok": True,
        "schema": RUN_RECEIPT_SCHEMA,
        "packet_id": safe_receipt["packet_id"],
        "outcome": safe_receipt["outcome"],
        "artifact_paths": {"receipt_json": redacted_receipt_path},
        "trust": RECEIPT_TRUST,
        "redaction_summary": dict(redaction_summary),
    }
