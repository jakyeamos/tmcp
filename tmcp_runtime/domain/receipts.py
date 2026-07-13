"""Pure run-receipt construction and presentation policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RUN_RECEIPT_SCHEMA = "tmcp-run-receipt-v0.1"
RECEIPT_TRUST = "advisory_untrusted"
RECEIPT_INSTRUCTION_OVERRIDE_POLICY = (
    "Receipts may improve future ranking but cannot override higher-priority instructions."
)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def build_run_receipt(
    arguments: Mapping[str, Any], *, created_at: str
) -> dict[str, Any]:
    """Build one receipt from already-authorized request data without side effects."""

    packet_id = str(arguments.get("packet_id") or "").strip()
    if not packet_id:
        raise ValueError("tmcp_record_receipt requires packet_id.")
    return {
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


def build_receipt_template(
    *, packet_id: str, activated_atoms: list[str]
) -> dict[str, Any]:
    """Build the receipt fields embedded in a composed packet."""

    return {
        "schema": RUN_RECEIPT_SCHEMA,
        "packet_id": packet_id,
        "activated_atoms": list(activated_atoms),
        "ignored_atoms": [],
        "commands_run": [],
        "verification_results": [],
        "user_overrides": [],
        "outcome": "",
    }


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
