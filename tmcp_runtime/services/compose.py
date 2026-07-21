"""In-memory composed-packet assembly over adapter-supplied safe inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.composition import (
    contextual_atoms_and_gates,
    filter_source_verification_gates,
    matching_reference_reads,
    merge_composition_nodes,
    select_composition_nodes_with_diagnostics,
    validate_project_recipe_cache_policy,
)
from tmcp_runtime.domain.declared_loads import resolve_declared_load_nodes
from tmcp_runtime.domain.compositional_intelligence import (
    compile_semantic_composition,
    prepare_composition,
)
from tmcp_runtime.domain.composition_declared_dependencies import (
    node_is_explicitly_scoped,
)
from tmcp_runtime.domain.families import compose_family_context
from tmcp_runtime.domain.harvest_nodes import (
    json_list,
    node_source_role,
    node_signal_text,
    ordered_unique,
    source_role_is_activation_eligible,
    string_list,
)
from tmcp_runtime.domain.packets import build_composed_packet
from tmcp_runtime.domain.routes import derive_task_identity
from tmcp_runtime.domain.source_activation_projection import (
    project_source_node_for_composition,
)
from tmcp_runtime.domain.workflow_activation import (
    build_global_workflow_activation,
    select_global_workflows,
)
from tmcp_runtime.services.semantic_compose import apply_semantic_composition


COMPOSED_PACKET_SCHEMA = "tmcp-composed-packet-v0.1"


def _routing_metadata(node: Mapping[str, Any]) -> dict[str, Any]:
    metadata = node.get("routing_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _compose_context(arguments: Mapping[str, Any]) -> dict[str, Any]:
    context = arguments.get("runtime_context")
    return context if isinstance(context, dict) else {}


def _composition_limit(
    arguments: Mapping[str, Any],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = arguments.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer.")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _composition_boolean(
    arguments: Mapping[str, Any],
    name: str,
    *,
    default: bool,
) -> bool:
    value = arguments.get(name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean.")
    return value


def _optional_digest(arguments: Mapping[str, Any], name: str) -> str | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 64 or value != value.casefold():
        raise ValueError(f"{name} must be a lowercase SHA-256 digest.")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest.")
    return value


def _composition_identity(
    arguments: Mapping[str, Any],
    source_nodes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any], list[str]]:
    objective = str(arguments.get("objective") or "").strip()
    context = dict(_compose_context(arguments))
    context["explicitly_scoped_paths"] = string_list(
        arguments.get("explicitly_scoped_paths")
    )
    identity_context = dict(context)
    identity_context["latest_user_message"] = str(
        arguments.get("latest_user_message") or ""
    )
    preliminary_routes = string_list(
        derive_task_identity(objective, identity_context).get("active_routes")
    )
    family_context = compose_family_context(
        source_nodes,
        objective,
        context=identity_context,
        active_routes=preliminary_routes,
        node_signal_text=node_signal_text,
    )
    task_identity = derive_task_identity(
        objective,
        identity_context,
        family_context if family_context else None,
    )
    return context, family_context, task_identity, preliminary_routes


def _composition_scope_nodes(
    arguments: Mapping[str, Any], source_nodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Bind exact caller-scoped paths before compatibility selection.

    Direct file-root harvests record their own scope. A project harvest needs
    the caller's exact ``explicitly_scoped_paths`` to make the same
    user-authorized exception available to direct composition.
    """

    scoped_paths = string_list(arguments.get("explicitly_scoped_paths"))
    return [
        {
            **node,
            "explicitly_scoped": node_is_explicitly_scoped(node, scoped_paths),
        }
        for node in source_nodes
    ]


def prepare_composition_from_source_nodes(
    arguments: Mapping[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Prepare the same semantic evidence identity consumed by compose."""

    objective = str(arguments.get("objective") or "").strip()
    if not objective:
        raise ValueError("tmcp_prepare_composition requires objective.")
    composition_nodes = [
        project_source_node_for_composition(node)
        for node in _composition_scope_nodes(arguments, source_nodes)
    ]
    _context, _family_context, task_identity, _routes = _composition_identity(
        arguments,
        composition_nodes,
    )
    return prepare_composition(
        composition_nodes,
        objective,
        task_identity=task_identity,
        explicitly_scoped_paths=string_list(arguments.get("explicitly_scoped_paths")),
        max_slices=_composition_limit(
            arguments,
            "candidate_limit",
            default=12,
            minimum=1,
            maximum=24,
        ),
        max_chars_per_slice=_composition_limit(
            arguments,
            "max_excerpt_chars",
            default=1200,
            minimum=64,
            maximum=48000,
        ),
        max_total_chars=_composition_limit(
            arguments,
            "max_total_chars",
            default=12000,
            minimum=1000,
            maximum=48000,
        ),
        max_total_tokens=_composition_limit(
            arguments,
            "max_total_tokens",
            default=3000,
            minimum=250,
            maximum=12000,
        ),
        include_all_active_source_slices=_composition_boolean(
            arguments,
            "include_all_active_source_slices",
            default=False,
        ),
        task_context_digest=_optional_digest(arguments, "task_context_digest"),
    )


def _validated_prepared_composition(
    arguments: Mapping[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
    prepared_composition: Mapping[str, Any],
) -> dict[str, Any]:
    """Accept an internal preflight only when it matches this exact input snapshot."""

    expected = prepare_composition_from_source_nodes(
        arguments,
        source_nodes=source_nodes,
    )
    if dict(prepared_composition) != expected:
        raise ValueError(
            "prepared_composition does not match the current objective, "
            "composition controls, and source snapshot."
        )
    return expected


def active_instructions_for_source_node(node: Mapping[str, Any]) -> list[str]:
    """Derive advisory instructions from one already-harvested source node."""

    if not source_role_is_activation_eligible(node_source_role(dict(node))):
        return []
    text = node_signal_text(dict(node))
    instructions: list[str] = []
    if "pnpm" in text:
        instructions.append(
            "Use pnpm for JavaScript dependency management, installs, and scripts."
        )
    if "read before modifying" in text or "read before" in text:
        instructions.append("Read relevant project files before modifying behavior.")
    if "existing behavior" in text or "existing implementation" in text:
        instructions.append(
            "Search existing behavior first and reuse established components or helpers."
        )
    if (
        "brand or product register" in text
        or "brand register" in text
        or "product register" in text
    ):
        instructions.append(
            "Choose the brand or product register before implementation decisions."
        )
    if "canonical spreadsheet" in text:
        instructions.append(
            "Maintain one canonical spreadsheet/status-machine source of truth with stable Feature IDs."
        )
    if "last tested commit" in text:
        instructions.append("Record the last tested commit with verification evidence.")
    if "contrast" in text or "reduced motion" in text or "responsive" in text:
        instructions.append(
            "Apply UI verification atoms for contrast, reduced motion, responsive behavior, and browser evidence."
        )
    return instructions


def enrich_packet_from_source_nodes(
    packet: dict[str, Any],
    source_nodes: list[dict[str, Any]],
    read_paths: list[str],
) -> dict[str, Any]:
    """Attach newly required source evidence without performing any reads."""

    if not read_paths:
        return packet
    wanted_paths = set(read_paths)
    citations = [
        item
        for item in json_list(packet.get("evidence_citations"))
        if isinstance(item, dict)
    ]
    cited_paths = {
        str(item.get("source") or item.get("path") or "") for item in citations
    }
    active_instructions = string_list(packet.get("active_instructions"))
    for node in source_nodes:
        rel_path = str(node.get("relative_path") or "")
        if rel_path not in wanted_paths or rel_path in cited_paths:
            continue
        projected_node = project_source_node_for_composition(node)
        citations.append(
            {
                "source": rel_path,
                "path": node.get("path"),
                "trust": node.get("trust", "untrusted_harvested_text"),
                "matched_atoms": string_list(projected_node.get("behavior_atoms"))[
                    :5
                ],
            }
        )
        active_instructions.extend(active_instructions_for_source_node(projected_node))
        cited_paths.add(rel_path)
    packet["evidence_citations"] = citations
    packet["active_instructions"] = ordered_unique(active_instructions)[:10]
    return packet


def compose_packet_from_source_nodes(
    arguments: Mapping[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
    global_graphs: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    cache_warnings: list[str],
    cache_home: str,
    prepared_composition: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a packet from harvested nodes and a pre-screened cache snapshot."""

    objective = str(arguments.get("objective") or "").strip()
    if not objective:
        raise ValueError("tmcp_compose_packet requires objective.")
    phase = str(arguments.get("phase") or "start")
    cache_policy = validate_project_recipe_cache_policy(
        cache_policy=arguments.get("cache_policy"),
        project_recipe_id=arguments.get("project_recipe_id"),
    )
    composition_nodes = [
        project_source_node_for_composition(node)
        for node in _composition_scope_nodes(arguments, source_nodes)
    ]
    context, family_context, task_identity, preliminary_routes = _composition_identity(
        arguments,
        composition_nodes,
    )
    active_routes = (
        string_list(task_identity.get("active_routes")) or preliminary_routes
    )
    selected_nodes, selection_diagnostics = select_composition_nodes_with_diagnostics(
        composition_nodes,
        objective,
        phase,
        context,
        family_context=family_context,
        active_routes=active_routes,
        node_signal_text=node_signal_text,
    )
    declared_load_paths, declared_load_nodes = resolve_declared_load_nodes(
        selected_nodes=selected_nodes,
        source_nodes=composition_nodes,
        objective=objective,
        family_context=family_context,
    )
    selected_nodes = merge_composition_nodes(selected_nodes, declared_load_nodes)
    selection_diagnostics["declared_load_paths"] = declared_load_paths
    selection_diagnostics["declared_load_sources"] = [
        str(node.get("relative_path") or node.get("id") or "")
        for node in declared_load_nodes
    ]

    active_global_graphs: list[dict[str, Any]] = []
    active_receipts: list[dict[str, Any]] = []
    active_cache_warnings: list[str] = []
    if cache_policy == "global":
        active_global_graphs = global_graphs
        active_receipts = receipts
        active_cache_warnings = cache_warnings
    selected_workflows = select_global_workflows(active_global_graphs, objective)

    active_instructions: list[str] = []
    required_reads: list[str] = []
    tool_script_prompts: list[str] = []
    verification_gates: list[str] = []
    stop_conditions: list[str] = []
    active_atoms: list[str] = []
    evidence_citations: list[dict[str, Any]] = []

    for node in selected_nodes:
        metadata = _routing_metadata(node)
        if source_role_is_activation_eligible(node_source_role(node)):
            active_instructions.extend(active_instructions_for_source_node(node))
            required_reads.extend(string_list(metadata.get("required_reads")))
            tool_script_prompts.extend(
                string_list(metadata.get("tool_script_prompts"))
            )
            verification_gates.extend(
                filter_source_verification_gates(
                    string_list(metadata.get("verification_gates")),
                    objective,
                    context,
                )
            )
            stop_conditions.extend(string_list(metadata.get("stop_conditions")))
            active_atoms.extend(string_list(node.get("behavior_atoms")))
        evidence_citations.append(
            {
                "source": node.get("relative_path"),
                "path": node.get("path"),
                "trust": node.get("trust", "untrusted_harvested_text"),
                "matched_atoms": string_list(node.get("behavior_atoms"))[:5],
            }
        )

    required_reads.extend(matching_reference_reads(composition_nodes, objective))
    required_reads.extend(declared_load_paths)
    global_activation = build_global_workflow_activation(selected_workflows)
    active_instructions.extend(global_activation["active_instructions"])
    active_atoms.extend(global_activation["active_atoms"])
    evidence_citations.extend(global_activation["evidence_citations"])

    context_atoms, context_reads, context_gates = contextual_atoms_and_gates(
        objective, phase, context
    )
    active_atoms.extend(context_atoms)
    required_reads.extend(context_reads)
    verification_gates.extend(context_gates)

    conflicts: list[dict[str, Any]] = []
    selected_text = " ".join(node_signal_text(node) for node in selected_nodes)
    if "npm" in selected_text and "pnpm" in selected_text:
        conflicts.append(
            {
                "id": "javascript_package_manager",
                "detail": "Harvested sources mention npm and pnpm; higher-priority user/project rules decide.",
            }
        )

    global_cache = {
        "cache_policy": cache_policy,
        "tmcp_home": cache_home,
        "promoted_graph_count": len(active_global_graphs),
        "receipt_count": len(active_receipts),
        "warnings": active_cache_warnings,
        "trust": "advisory_untrusted",
    }
    packet = build_composed_packet(
        composed_packet_schema=COMPOSED_PACKET_SCHEMA,
        objective=objective,
        project_path=str(arguments.get("project_path") or "."),
        phase=phase,
        task_identity=task_identity,
        family_context=family_context,
        source_nodes=composition_nodes,
        selected_nodes=selected_nodes,
        active_instructions=active_instructions,
        required_reads=required_reads,
        tool_script_prompts=tool_script_prompts,
        verification_gates=verification_gates,
        stop_conditions=stop_conditions,
        active_atoms=active_atoms,
        evidence_citations=evidence_citations,
        conflicts=conflicts,
        cache_policy=cache_policy,
        global_cache=global_cache,
        receipt_count=len(active_receipts),
        user_overrides=string_list(arguments.get("user_overrides")),
    )
    diagnostics = dict(packet.get("composition_diagnostics") or {})
    diagnostics["compatibility_selection"] = selection_diagnostics
    packet["composition_diagnostics"] = diagnostics
    proposal = arguments.get("semantic_proposal")
    if proposal is None:
        return packet
    if not isinstance(proposal, Mapping):
        raise ValueError("semantic_proposal must be an object.")
    if prepared_composition is None:
        preflight = prepare_composition_from_source_nodes(
            arguments,
            source_nodes=composition_nodes,
        )
    elif isinstance(prepared_composition, Mapping):
        if cache_policy == "project":
            # Project recipes are rehydrated and validated against their closed
            # runtime capsule by the owning recipe service before this point.
            # Their replay preflight may intentionally retain original source
            # node IDs after a same-content rename, so a raw equality check
            # would reject the safe rehydration path.
            preflight = dict(prepared_composition)
        else:
            preflight = _validated_prepared_composition(
                arguments,
                source_nodes=source_nodes,
                prepared_composition=prepared_composition,
            )
    else:
        raise ValueError("prepared_composition must be an object.")
    compiled = compile_semantic_composition(
        dict(proposal),
        preflight,
        current_phase=phase,
    )
    return apply_semantic_composition(
        packet,
        # Re-apply the cited activation projection to the original harvested
        # nodes so diagnostics retain rejected adapter metadata.  The semantic
        # projection is the sole path from those nodes into active fields.
        source_nodes=source_nodes,
        preflight=preflight,
        compiled=compiled,
        instruction_builder=active_instructions_for_source_node,
    )
