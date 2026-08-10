"""Runtime-state and recompile orchestration over explicit adapter callbacks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from tmcp_runtime.domain.composition import normalize_cache_policy
from tmcp_runtime.domain.recompile import parse_previous_packet
from tmcp_runtime.domain.runtime_state import derive_runtime_state
from tmcp_runtime.services.recompile import finalize_recompiled_packet


SourceExists = Callable[[str], bool]
SourceNodeLoader = Callable[[dict[str, Any]], list[dict[str, Any]]]
CacheWarningLoader = Callable[[str], list[str]]
PacketComposer = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RuntimeServiceContext:
    """Acquisition callbacks supplied by the compatibility adapter."""

    source_exists: SourceExists
    load_source_nodes: SourceNodeLoader
    load_cache_warnings: CacheWarningLoader
    compose_packet: PacketComposer


class RuntimeService:
    """Coordinate safe runtime inputs without owning their acquisition."""

    def __init__(self, context: RuntimeServiceContext) -> None:
        self._context = context

    def build_state(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        source_nodes: list[dict[str, Any]] = []
        harvest_root = str(
            arguments.get("source_path") or arguments.get("project_path") or ""
        ).strip()
        if harvest_root and self._context.source_exists(harvest_root):
            source_nodes = [
                item
                for item in self._context.load_source_nodes(dict(arguments))
                if isinstance(item, dict)
            ]
        runtime_arguments = dict(arguments)
        cache_policy = normalize_cache_policy(runtime_arguments.get("cache_policy"))
        runtime_arguments["cache_policy"] = cache_policy
        cache_warnings = (
            self._context.load_cache_warnings(cache_policy)
            if cache_policy == "global"
            else []
        )
        return derive_runtime_state(
            runtime_arguments,
            source_nodes=source_nodes,
            cache_warnings=list(cache_warnings),
        )

    def recompile(
        self,
        arguments: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        argument_map = dict(arguments)
        previous_packet = parse_previous_packet(argument_map)
        if not isinstance(previous_packet, dict):
            raise ValueError(
                "tmcp_runtime_next output_mode=full requires previous_packet as an object."
            )
        source_path = argument_map.get("source_path") or argument_map.get(
            "project_path"
        )
        if not source_path and argument_map.get("session_id") is None:
            source_path = previous_packet.get("project_path")
            if "[REDACTED:" in str(source_path):
                raise ValueError(
                    "tmcp_runtime_next requires an explicit source_path or project_path "
                    "when previous_packet has a redacted project path."
                )
        if not bool(state.get("recompile_required", True)):
            unchanged_packet = dict(previous_packet)
            active_atoms = unchanged_packet.get("active_atoms")
            if not isinstance(active_atoms, list):
                active_atoms = []
            return {
                "ok": True,
                "schema": "tmcp-recompiled-packet-v0.1",
                "previous_packet_id": str(previous_packet.get("packet_id") or "") or None,
                "recompile_reason": "no_material_change",
                "recompile_detail": (
                    "No phase, evidence, failure, redirect, or task-identity change "
                    "requires recompilation."
                ),
                "packet": unchanged_packet,
                "packet_diff": {
                    "dropped": [],
                    "added": [],
                    "unchanged": sorted(str(item) for item in active_atoms),
                    "phase_change": None,
                },
                "agent_proposals": state.get("proposed_changes") or [],
                "validated_changes": state.get("validated_changes") or [],
                "suggested_phase": "",
                "task_identity": unchanged_packet.get("task_identity"),
                "task_identity_delta": None,
                "warnings": state.get("warnings") or [],
                "recompile_required": False,
                "recompile_triggers": [],
                "safety": {
                    "stateless": True,
                    "cache_trust": "advisory_untrusted",
                    "instruction_override_policy": (
                        "Recompiled packets never override system, developer, user, or project instructions."
                    ),
                },
            }
        target_phase = str(
            state.get("suggested_phase") or state.get("phase") or "start"
        )
        session_project_path = (
            state.get("project_path")
            if argument_map.get("session_id") is not None
            else previous_packet.get("project_path") or state.get("project_path")
        )
        compose_arguments = {
            "objective": state.get("combined_objective") or state.get("objective"),
            "project_path": session_project_path,
            "source_path": source_path,
            "phase": target_phase,
            "cache_policy": state.get("cache_policy") or "none",
            "runtime_context": state.get("context") or {},
            "latest_user_message": state.get("latest_user_message") or "",
            "limit": argument_map.get("limit", 40),
            "admission_mode": argument_map.get("admission_mode")
            or (previous_packet.get("admission") or {}).get("mode")
            or "forced",
        }
        for key in (
            "source_paths",
            "include_globs",
            "exclude_globs",
            "max_file_bytes",
            "max_excerpt_chars",
            "follow_symlinks",
            "redact_sensitive",
            "include_test_sources",
        ):
            if key in argument_map:
                compose_arguments[key] = argument_map[key]
        composed_packet = self._context.compose_packet(compose_arguments)
        if argument_map.get("session_id") is not None:
            previous_packet_id = str(previous_packet.get("packet_id") or "")
        else:
            previous_packet_id = str(
                argument_map.get("previous_packet_id")
                or previous_packet.get("packet_id")
                or ""
            )
        return finalize_recompiled_packet(
            argument_map,
            state,
            previous_packet=previous_packet,
            composed_packet=composed_packet,
            previous_packet_id=previous_packet_id or None,
        )
