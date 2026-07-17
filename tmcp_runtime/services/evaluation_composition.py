"""Validation contracts for source-bundle composition experiments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.services.evaluation_plan import displayed_content_digest


COMPOSITION_PROVENANCE_SCHEMA = "tmcp-composition-source-bundle-v0.1"
SOURCE_BUNDLE_INCLUSION_KIND = "source_bundle_inclusion"


def _non_empty_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value


def _sha256(value: Any, *, label: str) -> str:
    digest = _non_empty_text(value, label=label)
    if not digest.startswith("sha256:"):
        raise ValueError(f"{label} must use a sha256 digest.")
    return digest


def _source_entries(value: Any, *, label: str) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a list.")
    entries: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"{label}[{index}] must be an object.")
        entries.append(
            {
                "path": _non_empty_text(item.get("path"), label=f"{label}[{index}].path"),
                "sha256": _sha256(item.get("sha256"), label=f"{label}[{index}].sha256"),
            }
        )
    return entries


def _provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("composition_provenance")
    if not isinstance(value, Mapping):
        raise ValueError("source bundle composition rows require composition_provenance.")
    provenance = dict(value)
    if provenance.get("schema") != COMPOSITION_PROVENANCE_SCHEMA:
        raise ValueError("source bundle composition provenance schema does not match.")
    if provenance.get("delivery_mode") != "materialized_packet_attachment":
        raise ValueError("source bundle composition delivery mode is invalid.")
    for field in (
        "packet_id",
        "packet_sha256",
        "receipt_sha256",
        "task_evidence_bundle_sha256",
        "base_attachment_sha256",
        "attachment_sha256",
        "source_bundle_sha256",
    ):
        if field == "packet_id":
            _non_empty_text(provenance.get(field), label=f"composition_provenance.{field}")
        else:
            _sha256(provenance.get(field), label=f"composition_provenance.{field}")
    attachment = row.get("skill_attachment")
    if not isinstance(attachment, str):
        raise ValueError("source bundle composition rows require skill_attachment.")
    if provenance["attachment_sha256"] != displayed_content_digest(attachment):
        raise ValueError("source bundle composition attachment digest does not match.")
    bundle_text = provenance.get("source_bundle_text")
    if not isinstance(bundle_text, str):
        raise ValueError("source bundle composition source_bundle_text must be a string.")
    if provenance["source_bundle_sha256"] != displayed_content_digest(bundle_text):
        raise ValueError("source bundle composition source bundle digest does not match.")
    provenance["selected_sources"] = _source_entries(
        provenance.get("selected_sources"), label="composition_provenance.selected_sources"
    )
    return provenance


def validate_source_bundle_inclusion_contrast(
    control_row: Mapping[str, Any],
    intervention_row: Mapping[str, Any],
) -> None:
    """Require a byte-pinned materialized bundle as the only causal delta."""

    control = _provenance(control_row)
    intervention = _provenance(intervention_row)
    for field in (
        "schema",
        "delivery_mode",
        "packet_id",
        "packet_sha256",
        "receipt_sha256",
        "task_evidence_bundle_sha256",
        "base_attachment_sha256",
    ):
        if control[field] != intervention[field]:
            raise ValueError(
                f"source bundle composition contrast changes shared field {field}."
            )
    control_attachment = control_row.get("skill_attachment")
    intervention_attachment = intervention_row.get("skill_attachment")
    if not isinstance(control_attachment, str) or not isinstance(
        intervention_attachment, str
    ):
        raise ValueError("source bundle composition contrast skill attachments are missing.")
    if control["base_attachment_sha256"] != displayed_content_digest(control_attachment):
        raise ValueError(
            "source bundle composition base attachment digest does not match control."
        )
    if control["source_bundle_text"] or control["selected_sources"]:
        raise ValueError(
            "source bundle composition control must not include selected sources."
        )
    source_bundle_text = str(intervention["source_bundle_text"])
    expected_attachment = f"{control_attachment}\n\n{source_bundle_text}".strip()
    if intervention_attachment != expected_attachment:
        raise ValueError(
            "source bundle composition intervention must append only the declared source bundle."
        )
    if not intervention["selected_sources"]:
        raise ValueError(
            "source bundle composition intervention must declare selected sources."
        )
