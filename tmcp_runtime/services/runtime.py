"""Runtime-state and recompile orchestration over explicit adapter callbacks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from tmcp_runtime.domain.composition import normalize_cache_policy
from tmcp_runtime.domain.harvest_nodes import string_list
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
        runtime_arguments = dict(arguments)
        source_nodes: list[dict[str, Any]] = []
        harvest_roots = string_list(runtime_arguments.get("source_paths"))
        if not harvest_roots:
            harvest_root = str(
                runtime_arguments.get("source_path")
                or runtime_arguments.get("project_path")
                or ""
            ).strip()
            if harvest_root:
                harvest_roots = [harvest_root]
        if not harvest_roots:
            previous_packet = parse_previous_packet(runtime_arguments)
            previous_project_path = (
                str(previous_packet.get("project_path") or "").strip()
                if isinstance(previous_packet, Mapping)
                else ""
            )
            if previous_project_path and "[REDACTED:" not in previous_project_path:
                harvest_roots = [previous_project_path]
                runtime_arguments["source_path"] = previous_project_path
                runtime_arguments["project_path"] = previous_project_path
        if harvest_roots and any(
            self._context.source_exists(path) for path in harvest_roots
        ):
            source_nodes = [
                item
                for item in self._context.load_source_nodes(runtime_arguments)
                if isinstance(item, dict)
            ]
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
        proposal = argument_map.get("semantic_proposal")
        composition_runtime = state.get("composition_runtime")
        proposal_phase = (
            str(proposal.get("current_phase") or "")
            if isinstance(proposal, Mapping)
            else ""
        )
        runtime_phase = (
            str(composition_runtime.get("current_phase") or "")
            if isinstance(composition_runtime, Mapping)
            else ""
        )
        target_phase = str(
            runtime_phase
            or proposal_phase
            or state.get("suggested_phase")
            or state.get("phase")
            or "start"
        )
        session_project_path = (
            state.get("project_path")
            if argument_map.get("session_id") is not None
            else previous_packet.get("project_path") or state.get("project_path")
        )
        source_paths = string_list(argument_map.get("source_paths"))
        source_path = argument_map.get("source_path") or argument_map.get(
            "project_path"
        )
        if (
            not source_paths
            and not source_path
            and argument_map.get("session_id") is None
        ):
            source_path = previous_packet.get("project_path")
            if "[REDACTED:" in str(source_path):
                raise ValueError(
                    "tmcp_runtime_next requires an explicit source_path or project_path "
                    "when previous_packet has a redacted project path."
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
        }
        if proposal is not None:
            compose_arguments["semantic_proposal"] = proposal
        for key in (
            "source_paths",
            "include_globs",
            "exclude_globs",
            "max_file_bytes",
            "max_excerpt_chars",
            "max_total_chars",
            "max_total_tokens",
            "candidate_limit",
            "explicitly_scoped_paths",
            "project_recipe_id",
            "follow_symlinks",
            "redact_sensitive",
            "user_overrides",
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
