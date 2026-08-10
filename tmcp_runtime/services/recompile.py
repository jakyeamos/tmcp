"""In-memory recompiled-packet finalization over adapter-composed packets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.harvest_nodes import json_list, string_list
from tmcp_runtime.domain.packets import render_composed_packet_markdown
from tmcp_runtime.domain.recompile import (
    apply_validated_proposals,
    merge_packet_delta,
    packet_diff,
    recompile_detail,
    render_recompiled_packet_markdown,
    resolve_recompile_reason,
)
from tmcp_runtime.services.compose import enrich_packet_from_source_nodes


RECOMPILED_PACKET_SCHEMA = "tmcp-recompiled-packet-v0.1"


def finalize_recompiled_packet(
    arguments: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    previous_packet: dict[str, Any],
    composed_packet: dict[str, Any],
    previous_packet_id: str | None,
) -> dict[str, Any]:
    """Finalize a full recompile without reading, writing, or redacting data."""

    packet_delta = dict(state.get("packet_delta") or {})
    next_gates = string_list(state.get("next_verification_gate"))
    new_packet = merge_packet_delta(
        composed_packet,
        packet_delta,
        next_gates=next_gates,
    )
    source_nodes = [
        item for item in json_list(state.get("source_nodes")) if isinstance(item, dict)
    ]
    new_packet = enrich_packet_from_source_nodes(
        new_packet,
        source_nodes,
        string_list(packet_delta.get("newly_required_reads")),
    )
    runtime_identity = state.get("task_identity")
    if isinstance(runtime_identity, dict):
        new_packet["task_identity"] = dict(runtime_identity)
    new_packet = apply_validated_proposals(
        new_packet,
        [
            item
            for item in json_list(state.get("validated_changes"))
            if isinstance(item, dict)
        ],
    )
    recompile_reason = resolve_recompile_reason(
        dict(arguments),
        dict(state),
    )
    packet_change = packet_diff(
        previous_packet,
        new_packet,
        packet_delta=packet_delta,
        recompile_reason=recompile_reason,
    )
    recompiled = {
        "ok": True,
        "schema": RECOMPILED_PACKET_SCHEMA,
        "previous_packet_id": previous_packet_id or None,
        "recompile_reason": recompile_reason,
        "recompile_detail": recompile_detail(recompile_reason),
        "packet": new_packet,
        "packet_diff": packet_change,
        "agent_proposals": state.get("proposed_changes") or [],
        "validated_changes": state.get("validated_changes") or [],
        "suggested_phase": state.get("suggested_phase") or "",
        "task_identity": new_packet.get("task_identity"),
        "task_identity_delta": state.get("task_identity_delta"),
        "warnings": state.get("warnings") or [],
        "recompile_required": True,
        "recompile_triggers": state.get("recompile_triggers") or [],
        "safety": {
            "stateless": True,
            "cache_trust": "advisory_untrusted",
            "instruction_override_policy": (
                "Recompiled packets never override system, developer, user, or project instructions."
            ),
        },
    }
    new_packet["packet_markdown"] = render_recompiled_packet_markdown(
        recompiled,
        compose_markdown=render_composed_packet_markdown,
    )
    recompiled["packet"] = new_packet
    return recompiled
