"""Closed advisory provenance for native host-assisted composition."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.composition_preflight import stable_digest


HOST_COMPOSITION_INTAKE_SCHEMA = "tmcp-host-composition-intake-v0.1"
HOST_COMPOSITION_LINEAGE_SCHEMA = "tmcp-host-composition-lineage-v0.1"
HOST_COMPOSITION_RECEIPT_PROVENANCE_SCHEMA = (
    "tmcp-host-composition-receipt-provenance-v0.1"
)
HOST_COMPOSITION_TRUST = "advisory_untrusted"
HOST_COMPOSITION_RUNTIME_STATUSES = frozenset(
    {
        "initial_frozen_snapshot",
        "runtime_capsule_revalidated",
        "runtime_capsule_rejected",
        "fresh_semantic_composition",
        "fresh_semantic_composition_rejected",
        "fresh_composition_required",
        "not_revalidated",
    }
)
_CURRENT_PLAN_BOUND_STATUSES = frozenset(
    {"runtime_capsule_revalidated", "fresh_semantic_composition"}
)

_SHA256_DIGEST_RE = re.compile(r"[a-f0-9]{64}")
_ORIGIN_FIELDS = frozenset(
    {
        "schema",
        "preflight_id",
        "preflight_digest",
        "source_snapshot_digest",
        "request_digest",
        "task_identity_digest",
        "reused_snapshot",
        "automatic_tool_execution",
        "receipt_persistence",
    }
)
_LINEAGE_FIELDS = frozenset(
    {
        "schema",
        "origin",
        "origin_digest",
        "runtime_snapshot_status",
        "current_preflight_id",
        "inherited_origin",
        "trust",
    }
)
_RECEIPT_PROVENANCE_FIELDS = frozenset(
    {
        "schema",
        "origin_digest",
        "origin_preflight_id",
        "runtime_snapshot_status",
        "runtime_preflight_id",
        "inherited_origin",
        "trust",
    }
)


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string.")
    return value.strip()


def _digest(value: object, field: str) -> str:
    digest = _required_string(value, field)
    if _SHA256_DIGEST_RE.fullmatch(digest) is None:
        raise ValueError(f"{field} must be a sha256 digest.")
    return digest


def _current_preflight_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field)


def _runtime_status(value: object, field: str) -> str:
    status = _required_string(value, field)
    if status not in HOST_COMPOSITION_RUNTIME_STATUSES:
        raise ValueError(f"{field} is not an allowed host composition status.")
    return status


def _validate_current_plan_binding(
    *,
    status: str,
    current_preflight_id: str | None,
    composition_plan: Mapping[str, Any] | None,
) -> None:
    if status not in _CURRENT_PLAN_BOUND_STATUSES:
        return
    if current_preflight_id is None:
        raise ValueError(
            "successful host composition runtime status requires current_preflight_id."
        )
    if not isinstance(composition_plan, Mapping):
        raise ValueError(
            "successful host composition runtime status requires a current composition plan."
        )
    plan_preflight_id = _required_string(
        composition_plan.get("preflight_id"), "composition_plan.preflight_id"
    )
    if current_preflight_id != plan_preflight_id:
        raise ValueError(
            "host composition current preflight is not bound to the current plan."
        )


def _validate_receipt_status_matrix(
    *,
    status: str,
    origin_preflight_id: str,
    runtime_preflight_id: str | None,
    inherited_origin: bool,
) -> None:
    if status == "initial_frozen_snapshot":
        if inherited_origin or runtime_preflight_id != origin_preflight_id:
            raise ValueError(
                "initial host composition receipt provenance is not self-consistent."
            )
        return
    if not inherited_origin:
        raise ValueError(
            "recompiled host composition receipt provenance must inherit origin."
        )
    if status in _CURRENT_PLAN_BOUND_STATUSES and runtime_preflight_id is None:
        raise ValueError(
            "successful host composition receipt provenance requires runtime_preflight_id."
        )


def validate_host_composition_origin(value: object) -> dict[str, Any]:
    """Validate the immutable first prepare-to-compose attestation."""

    if not isinstance(value, Mapping) or set(value) != _ORIGIN_FIELDS:
        raise ValueError("host composition origin must use the closed origin schema.")
    if value.get("schema") != HOST_COMPOSITION_INTAKE_SCHEMA:
        raise ValueError("host composition origin has an unsupported schema.")
    if value.get("reused_snapshot") is not True:
        raise ValueError("host composition origin must attest reused_snapshot=true.")
    if value.get("automatic_tool_execution") is not False:
        raise ValueError(
            "host composition origin must attest automatic_tool_execution=false."
        )
    if value.get("receipt_persistence") != "not_performed":
        raise ValueError(
            "host composition origin must attest receipt_persistence=not_performed."
        )
    return {
        "schema": HOST_COMPOSITION_INTAKE_SCHEMA,
        "preflight_id": _required_string(value.get("preflight_id"), "preflight_id"),
        "preflight_digest": _digest(value.get("preflight_digest"), "preflight_digest"),
        "source_snapshot_digest": _digest(
            value.get("source_snapshot_digest"), "source_snapshot_digest"
        ),
        "request_digest": _digest(value.get("request_digest"), "request_digest"),
        "task_identity_digest": _digest(
            value.get("task_identity_digest"), "task_identity_digest"
        ),
        "reused_snapshot": True,
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
    }


def build_host_composition_lineage(
    origin: Mapping[str, Any],
    *,
    runtime_snapshot_status: str,
    current_preflight_id: str | None,
    inherited_origin: bool,
    current_composition_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one closed lineage envelope without claiming a runtime snapshot reuse."""

    normalized_origin = validate_host_composition_origin(origin)
    status = _runtime_status(runtime_snapshot_status, "runtime_snapshot_status")
    normalized_current_preflight_id = _current_preflight_id(
        current_preflight_id, "current_preflight_id"
    )
    if status == "initial_frozen_snapshot":
        if inherited_origin:
            raise ValueError("initial host composition lineage cannot inherit origin.")
        if normalized_current_preflight_id != normalized_origin["preflight_id"]:
            raise ValueError(
                "initial host composition lineage must bind its original preflight."
            )
    elif not inherited_origin:
        raise ValueError("recompiled host composition lineage must inherit origin.")
    _validate_current_plan_binding(
        status=status,
        current_preflight_id=normalized_current_preflight_id,
        composition_plan=current_composition_plan,
    )
    return {
        "schema": HOST_COMPOSITION_LINEAGE_SCHEMA,
        "origin": normalized_origin,
        "origin_digest": stable_digest(normalized_origin),
        "runtime_snapshot_status": status,
        "current_preflight_id": normalized_current_preflight_id,
        "inherited_origin": inherited_origin,
        "trust": HOST_COMPOSITION_TRUST,
    }


def validate_host_composition_lineage(
    value: object,
    *,
    composition_plan: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate a packet lineage and bind its origin to its prior graph plan."""

    if not isinstance(value, Mapping) or set(value) != _LINEAGE_FIELDS:
        raise ValueError("host composition lineage must use the closed lineage schema.")
    if value.get("schema") != HOST_COMPOSITION_LINEAGE_SCHEMA:
        raise ValueError("host composition lineage has an unsupported schema.")
    if value.get("trust") != HOST_COMPOSITION_TRUST:
        raise ValueError("host composition lineage has an unsupported trust level.")
    origin = validate_host_composition_origin(value.get("origin"))
    if _digest(value.get("origin_digest"), "origin_digest") != stable_digest(origin):
        raise ValueError("host composition lineage origin digest does not match origin.")
    status = _runtime_status(
        value.get("runtime_snapshot_status"), "runtime_snapshot_status"
    )
    inherited_origin = value.get("inherited_origin")
    if not isinstance(inherited_origin, bool):
        raise ValueError("host composition lineage inherited_origin must be boolean.")
    current_preflight_id = _current_preflight_id(
        value.get("current_preflight_id"), "current_preflight_id"
    )
    if status == "initial_frozen_snapshot":
        if inherited_origin or current_preflight_id != origin["preflight_id"]:
            raise ValueError("initial host composition lineage is not self-consistent.")
    elif not inherited_origin:
        raise ValueError("recompiled host composition lineage must inherit origin.")
    if status == "initial_frozen_snapshot":
        if not isinstance(composition_plan, Mapping):
            raise ValueError("initial host composition lineage requires a bound plan.")
        if origin["preflight_id"] != _required_string(
            composition_plan.get("preflight_id"), "composition_plan.preflight_id"
        ):
            raise ValueError("host composition origin is not bound to the initial plan.")
    _validate_current_plan_binding(
        status=status,
        current_preflight_id=current_preflight_id,
        composition_plan=composition_plan,
    )
    return {
        "schema": HOST_COMPOSITION_LINEAGE_SCHEMA,
        "origin": origin,
        "origin_digest": stable_digest(origin),
        "runtime_snapshot_status": status,
        "current_preflight_id": current_preflight_id,
        "inherited_origin": inherited_origin,
        "trust": HOST_COMPOSITION_TRUST,
    }


def host_composition_receipt_provenance(
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    """Project safe provenance fields for a receipt template or recorded receipt."""

    if not isinstance(lineage, Mapping):
        raise ValueError("host composition receipt provenance requires a lineage.")
    if set(lineage) != _LINEAGE_FIELDS:
        raise ValueError("host composition receipt provenance requires closed lineage.")
    if lineage.get("schema") != HOST_COMPOSITION_LINEAGE_SCHEMA:
        raise ValueError("host composition receipt provenance has an invalid lineage schema.")
    if lineage.get("trust") != HOST_COMPOSITION_TRUST:
        raise ValueError("host composition receipt provenance has an invalid trust level.")
    origin = validate_host_composition_origin(lineage.get("origin"))
    origin_digest = _digest(lineage.get("origin_digest"), "origin_digest")
    if origin_digest != stable_digest(origin):
        raise ValueError("host composition receipt provenance has an invalid origin.")
    status = _runtime_status(
        lineage.get("runtime_snapshot_status"), "runtime_snapshot_status"
    )
    inherited_origin = lineage.get("inherited_origin")
    if not isinstance(inherited_origin, bool):
        raise ValueError("host composition receipt provenance inherited_origin must be boolean.")
    runtime_preflight_id = _current_preflight_id(
        lineage.get("current_preflight_id"), "current_preflight_id"
    )
    _validate_receipt_status_matrix(
        status=status,
        origin_preflight_id=origin["preflight_id"],
        runtime_preflight_id=runtime_preflight_id,
        inherited_origin=inherited_origin,
    )
    return {
        "schema": HOST_COMPOSITION_RECEIPT_PROVENANCE_SCHEMA,
        "origin_digest": origin_digest,
        "origin_preflight_id": origin["preflight_id"],
        "runtime_snapshot_status": status,
        "runtime_preflight_id": runtime_preflight_id,
        "inherited_origin": inherited_origin,
        "trust": HOST_COMPOSITION_TRUST,
    }


def validate_host_composition_receipt_provenance(value: object) -> dict[str, Any]:
    """Validate the bounded host provenance that may be retained in receipts."""

    if not isinstance(value, Mapping) or set(value) != _RECEIPT_PROVENANCE_FIELDS:
        raise ValueError(
            "host_composition_provenance must use the closed receipt provenance schema."
        )
    if value.get("schema") != HOST_COMPOSITION_RECEIPT_PROVENANCE_SCHEMA:
        raise ValueError("host_composition_provenance has an unsupported schema.")
    if value.get("trust") != HOST_COMPOSITION_TRUST:
        raise ValueError("host_composition_provenance has an unsupported trust level.")
    inherited_origin = value.get("inherited_origin")
    if not isinstance(inherited_origin, bool):
        raise ValueError("host_composition_provenance inherited_origin must be boolean.")
    status = _runtime_status(
        value.get("runtime_snapshot_status"), "runtime_snapshot_status"
    )
    runtime_preflight_id = _current_preflight_id(
        value.get("runtime_preflight_id"), "runtime_preflight_id"
    )
    origin_preflight_id = _required_string(
        value.get("origin_preflight_id"), "origin_preflight_id"
    )
    _validate_receipt_status_matrix(
        status=status,
        origin_preflight_id=origin_preflight_id,
        runtime_preflight_id=runtime_preflight_id,
        inherited_origin=inherited_origin,
    )
    return {
        "schema": HOST_COMPOSITION_RECEIPT_PROVENANCE_SCHEMA,
        "origin_digest": _digest(value.get("origin_digest"), "origin_digest"),
        "origin_preflight_id": origin_preflight_id,
        "runtime_snapshot_status": status,
        "runtime_preflight_id": runtime_preflight_id,
        "inherited_origin": inherited_origin,
        "trust": HOST_COMPOSITION_TRUST,
    }


def _host_composition_snapshot(
    packet: Mapping[str, Any],
) -> dict[str, str | bool | None] | None:
    metadata = packet.get("host_composition")
    if not isinstance(metadata, Mapping):
        return None
    origin_digest = metadata.get("origin_digest")
    runtime_status = metadata.get("runtime_snapshot_status")
    current_preflight_id = metadata.get("current_preflight_id")
    inherited_origin = metadata.get("inherited_origin")
    return {
        "origin_digest": (
            origin_digest if isinstance(origin_digest, str) and origin_digest else None
        ),
        "runtime_snapshot_status": (
            runtime_status
            if isinstance(runtime_status, str) and runtime_status
            else None
        ),
        "current_preflight_id": (
            current_preflight_id
            if isinstance(current_preflight_id, str) and current_preflight_id
            else None
        ),
        "inherited_origin": (
            inherited_origin if isinstance(inherited_origin, bool) else None
        ),
    }


def _host_composition_omission(packet: Mapping[str, Any]) -> bool:
    diagnostics = packet.get("composition_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return False
    provenance = diagnostics.get("host_composition_provenance")
    return (
        isinstance(provenance, Mapping)
        and provenance.get("status") == "untrusted_or_unbound_origin_omitted"
    )


def host_composition_packet_diff(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Describe host lineage transitions without exposing harvested source content."""

    if _host_composition_omission(current):
        return {
            "origin": {"status": "untrusted_or_unbound_origin_omitted"},
            "runtime_snapshot_status": {"previous": None, "current": None},
            "current_preflight_id": {"previous": None, "current": None},
            "inherited_origin": {"previous": None, "current": None},
        }
    previous_snapshot = _host_composition_snapshot(previous)
    current_snapshot = _host_composition_snapshot(current)
    if previous_snapshot is None and current_snapshot is None:
        return None
    previous_digest = (
        previous_snapshot.get("origin_digest") if previous_snapshot is not None else None
    )
    current_digest = (
        current_snapshot.get("origin_digest") if current_snapshot is not None else None
    )
    if previous_digest is None:
        origin_status = "added"
    elif current_digest is None:
        origin_status = "dropped"
    elif previous_digest == current_digest:
        origin_status = "preserved"
    else:
        origin_status = "changed"
    return {
        "origin": {
            "status": origin_status,
            "previous_digest": previous_digest,
            "current_digest": current_digest,
        },
        "runtime_snapshot_status": {
            "previous": (
                previous_snapshot.get("runtime_snapshot_status")
                if previous_snapshot is not None
                else None
            ),
            "current": (
                current_snapshot.get("runtime_snapshot_status")
                if current_snapshot is not None
                else None
            ),
        },
        "current_preflight_id": {
            "previous": (
                previous_snapshot.get("current_preflight_id")
                if previous_snapshot is not None
                else None
            ),
            "current": (
                current_snapshot.get("current_preflight_id")
                if current_snapshot is not None
                else None
            ),
        },
        "inherited_origin": {
            "previous": (
                previous_snapshot.get("inherited_origin")
                if previous_snapshot is not None
                else None
            ),
            "current": (
                current_snapshot.get("inherited_origin")
                if current_snapshot is not None
                else None
            ),
        },
    }


def host_composition_lineage_for_recompile(
    lineage: Mapping[str, Any],
    *,
    runtime_snapshot_status: str,
    current_preflight_id: str | None,
    current_composition_plan: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Carry a validated historical origin into a fresh runtime decision."""

    origin = lineage.get("origin")
    if not isinstance(origin, Mapping):
        raise ValueError("host composition lineage is missing origin.")
    return build_host_composition_lineage(
        origin,
        runtime_snapshot_status=runtime_snapshot_status,
        current_preflight_id=current_preflight_id,
        inherited_origin=True,
        current_composition_plan=current_composition_plan,
    )
