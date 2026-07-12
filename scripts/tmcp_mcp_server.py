#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.tmcp_mcp_framing import read_message, write_message  # noqa: E402
from scripts.tmcp_redaction import merge_redactions  # noqa: E402
from tmcp_runtime.domain.routes import (  # noqa: E402
    derive_task_identity,
    task_identity_delta,
    validate_proposed_changes,
)
from tmcp_runtime.domain.families import (  # noqa: E402
    compose_family_context,
    runtime_family_packet_delta,
    runtime_family_seed_context,
)
from tmcp_runtime.domain.declared_loads import (  # noqa: E402
    resolve_declared_load_nodes,
)
from tmcp_runtime.domain.recompile import (  # noqa: E402
    apply_validated_proposals,
    merge_packet_delta,
    packet_diff as build_packet_diff,
    parse_previous_packet,
    recompile_detail,
    render_recompiled_packet_markdown,
    resolve_recompile_reason,
)
from tmcp_runtime.domain.composition import (  # noqa: E402
    contextual_atoms_and_gates,
    filter_source_verification_gates,
    merge_composition_nodes,
    matching_reference_reads,
    select_composition_nodes,
)
from tmcp_runtime.domain.packets import (  # noqa: E402
    build_composed_packet,
    render_composed_packet_markdown,
)
from tmcp_runtime.domain.standalone_packets import (  # noqa: E402
    compile_standalone_packet,
)
from tmcp_runtime.domain.harvest_nodes import (  # noqa: E402
    node_signal_text as _domain_node_signal_text,
    routing_metadata_for as _domain_routing_metadata_for,
    source_node_from_text as _domain_source_node_from_text,
)
from tmcp_runtime.domain.review_evidence import (  # noqa: E402
    parse_evidence,
)
from tmcp_runtime.domain.review_results import (  # noqa: E402
    render_audit_markdown,
    render_remediation_plan_markdown,
    render_rubric_markdown,
)
from tmcp_runtime.domain.workflow_catalog import (  # noqa: E402
    workflow_catalog_by_id,
)
from tmcp_runtime.domain.workflow_activation import (  # noqa: E402
    build_global_workflow_activation,
    select_global_workflows,
)
from tmcp_runtime.domain.workflow_promotion import (  # noqa: E402
    render_promotion_markdown,
)
from tmcp_runtime.domain.workflow_adaptive import (  # noqa: E402
    render_workflow_recommendations_markdown,
)
from scripts.tmcp_skill_evaluate import evaluate_skills, harvest_warnings_for_source  # noqa: E402
from tmcp_runtime.api.registry import (  # noqa: E402
    CLI_COMMAND_DEFAULT_ARGUMENTS,
    CLI_HELP_ALIASES,
    CLI_LIST_TOOLS_ALIASES,
    CLI_TOOL_ALIASES,
    TOOLS,
    cli_usage,
    mcp_server_info,
    mcp_tools,
)
from tmcp_runtime.safety import (  # noqa: E402
    collect_harvest_roots,
    iter_harvest_candidates,
    redact_json_value,
    redact_path,
    read_harvest_text,
)
from tmcp_runtime.storage import (  # noqa: E402
    ArtifactStorageError,
    AtomicArtifactStore,
    PacketSessionStore,
    artifact_persistence_available,
)
from tmcp_runtime.services.harvest import (  # noqa: E402
    DEFAULT_HARVEST_EXCLUDE_DIR_NAMES,
    DEFAULT_HARVEST_EXCLUDE_GLOBS,
    DEFAULT_HARVEST_INCLUDE_GLOBS,
    harvest_skills as _runtime_harvest_skills,
    require_default_artifact_root as _runtime_require_default_artifact_root,
    source_project_path as _runtime_source_project_path,
)
from tmcp_runtime.services.recommendations import (  # noqa: E402
    recommend_workflows as _runtime_recommend_workflows,
)
from tmcp_runtime.services.promotion import (  # noqa: E402
    promote_harvest as _runtime_promote_harvest,
)
from tmcp_runtime.services.review import (  # noqa: E402
    build_review_plan as _runtime_build_review_plan,
)

AIOS_ROOT = (
    Path(os.environ["AIOS_ROOT"]).expanduser() if os.environ.get("AIOS_ROOT") else None
)
TMCP_HOME = Path(os.environ.get("TMCP_HOME", "~/.tmcp")).expanduser()
UTC = timezone.utc

COMPOSED_PACKET_SCHEMA = "tmcp-composed-packet-v0.1"
RUNTIME_NEXT_SCHEMA = "tmcp-runtime-next-v0.1"
RECOMPILED_PACKET_SCHEMA = "tmcp-recompiled-packet-v0.1"
RUN_RECEIPT_SCHEMA = "tmcp-run-receipt-v0.1"
MAX_GLOBAL_CACHE_CANDIDATES = 64
MAX_GLOBAL_CACHE_SCAN_ENTRIES = 256
MAX_GLOBAL_CACHE_ENTRIES = 32
MAX_GLOBAL_CACHE_ENTRY_BYTES = 262_144
MAX_GLOBAL_CACHE_JSON_DEPTH = 32
MAX_GLOBAL_CACHE_JSON_NODES = 2_048
MAX_GLOBAL_CACHE_WARNINGS = 12

def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _aios_available() -> bool:
    if AIOS_ROOT is None:
        return False
    return (AIOS_ROOT / "bin" / "aios.py").exists()


def _should_use_aios(adapter: str) -> bool:
    if adapter == "standalone":
        return False
    if adapter == "aios":
        return True
    return _aios_available()


def _run_aios(args: list[str]) -> dict[str, Any]:
    if not _aios_available():
        return {
            "ok": False,
            "adapter": "aios",
            "error": "AIOS adapter requested but AIOS_ROOT/bin/aios.py was not found.",
            "aios_root": str(AIOS_ROOT) if AIOS_ROOT is not None else None,
            "remediation": (
                "Continue with --adapter standalone, or set AIOS_ROOT to an AIOS "
                "checkout if you explicitly want the optional adapter."
            ),
        }
    command = (
        ["uv", "run", "python", "bin/aios.py", *args]
        if shutil.which("uv")
        else [sys.executable, "bin/aios.py", *args]
    )
    completed = subprocess.run(
        command,
        cwd=cast(Path, AIOS_ROOT),
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "adapter": "aios",
            "returncode": completed.returncode,
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout, "stderr": completed.stderr}
    if isinstance(payload, dict):
        response = cast(dict[str, object], payload)
        response.setdefault("ok", True)
        response.setdefault("adapter", "aios")
        return response
    return {"ok": True, "adapter": "aios", "data": payload}


def _enrich_packet_from_source_nodes(
    packet: dict[str, Any], source_nodes: list[dict[str, Any]], read_paths: list[str]
) -> dict[str, Any]:
    if not read_paths:
        return packet
    wanted_paths = set(read_paths)
    citations = [
        item
        for item in _json_list(packet.get("evidence_citations"))
        if isinstance(item, dict)
    ]
    cited_paths = {
        str(item.get("source") or item.get("path") or "") for item in citations
    }
    active_instructions = _string_list(packet.get("active_instructions"))
    for node in source_nodes:
        rel_path = str(node.get("relative_path") or "")
        if rel_path not in wanted_paths or rel_path in cited_paths:
            continue
        citations.append(
            {
                "source": rel_path,
                "path": node.get("path"),
                "trust": node.get("trust", "untrusted_harvested_text"),
                "matched_atoms": _string_list(node.get("behavior_atoms"))[:5],
            }
        )
        active_instructions.extend(_node_active_instructions(node))
        cited_paths.add(rel_path)
    packet["evidence_citations"] = citations
    packet["active_instructions"] = _ordered_unique(active_instructions)[:10]
    return packet


def _build_runtime_state(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(arguments.get("objective") or "").strip()
    if not objective:
        raise ValueError("tmcp_runtime_next requires objective.")
    phase = str(arguments.get("current_phase") or "start")
    cache_policy = str(arguments.get("cache_policy") or "none")
    latest_user_message = str(arguments.get("latest_user_message") or "")
    files_changed = _string_list(arguments.get("files_changed"))
    failures = _string_list(arguments.get("failures"))
    browser_evidence = _string_list(arguments.get("browser_evidence"))
    context = {
        "files_changed": files_changed,
        "failures": failures,
        "browser_evidence": browser_evidence,
    }
    combined_objective = " ".join(
        part for part in (objective, latest_user_message) if part
    ).strip()
    activated_atoms, newly_required_reads, next_gates = contextual_atoms_and_gates(
        combined_objective, phase, context
    )
    stale_atoms: list[str] = []
    warnings: list[str] = []
    family_delta: dict[str, Any] = {}
    family_context: dict[str, Any] | None = None
    source_nodes: list[dict[str, Any]] = []
    suggested_phase = ""
    harvest_root = str(
        arguments.get("source_path") or arguments.get("project_path") or ""
    ).strip()
    if harvest_root and Path(harvest_root).expanduser().exists():
        harvest = _harvest_skills(_runtime_harvest_arguments(arguments))
        source_nodes = [
            item
            for item in _json_list(harvest.get("source_nodes"))
            if isinstance(item, dict)
        ]
        family_context, seed_node = runtime_family_seed_context(
            source_nodes,
            combined_objective,
            phase,
            node_signal_text=_node_signal_text,
        )
        family_delta = runtime_family_packet_delta(
            current_phase=phase,
            family_context=family_context,
            seed_node=seed_node,
            source_nodes=source_nodes,
            objective=combined_objective,
            context=context,
            latest_user_message=latest_user_message,
        )
        if family_delta:
            activated_atoms = _ordered_unique(
                activated_atoms + _string_list(family_delta.get("activated_atoms"))
            )
            newly_required_reads = _ordered_unique(
                newly_required_reads
                + _string_list(family_delta.get("newly_required_reads"))
            )
            next_gates = _ordered_unique(
                next_gates + _string_list(family_delta.get("verification_gates"))
            )
            stale_atoms = _ordered_unique(
                stale_atoms + _string_list(family_delta.get("deactivated_atoms"))
            )
            suggested_phase = str(family_delta.get("suggested_phase") or "")
    if any(
        term in latest_user_message.lower()
        for term in ("actually", "instead", "new goal", "different")
    ):
        stale_atoms.append("previous-objective-specific-atoms")
        warnings.append(
            "Latest user message may redirect the objective; stale atoms should be rechecked before use."
        )
    if cache_policy != "none":
        _, graph_warnings = _load_global_promoted_graphs(cache_policy)
        _, receipt_warnings = _load_recent_receipts(cache_policy, limit=10)
        warnings.extend(graph_warnings + receipt_warnings)
    if not next_gates:
        next_gates.append("Read the next required source before changing behavior.")
    identity_context = dict(context)
    identity_context["latest_user_message"] = latest_user_message
    resolved_family_context = family_context
    if not resolved_family_context:
        packet_family_context = family_delta.get("family_context")
        if isinstance(packet_family_context, dict) and packet_family_context:
            resolved_family_context = packet_family_context
    current_task_identity = derive_task_identity(
        combined_objective,
        identity_context,
        resolved_family_context,
    )
    previous_task_identity = arguments.get("previous_task_identity")
    if not isinstance(previous_task_identity, dict):
        previous_packet = parse_previous_packet(arguments)
        if isinstance(previous_packet, dict):
            previous_task_identity = previous_packet.get("task_identity")
    identity_delta: dict[str, Any] | None = None
    if isinstance(previous_task_identity, dict):
        delta_reason = "runtime_context_changed"
        if any(
            term in latest_user_message.lower()
            for term in ("actually", "instead", "new goal", "different")
        ):
            delta_reason = "user_redirect"
        elif suggested_phase:
            delta_reason = "phase_transition"
        elif files_changed:
            delta_reason = "implementation_phase_detected"
        identity_delta = task_identity_delta(
            previous_task_identity,
            current_task_identity,
            reason=delta_reason,
        )
    packet_delta = {
        "activated_atoms": activated_atoms,
        "deactivated_atoms": stale_atoms,
        "stale_atoms": stale_atoms,
        "newly_required_reads": newly_required_reads,
        "suggested_phase": suggested_phase,
        "suggested_skills": _string_list(family_delta.get("suggested_skills")),
        "deferred_skills": _string_list(family_delta.get("deferred_skills")),
        "family_context": family_delta.get("family_context", {}),
    }
    proposed_changes = [
        item
        for item in _json_list(arguments.get("proposed_changes"))
        if isinstance(item, dict)
    ]
    validated_changes, proposal_warnings = validate_proposed_changes(proposed_changes)
    warnings.extend(proposal_warnings)
    return {
        "objective": objective,
        "combined_objective": combined_objective,
        "project_path": str(arguments.get("project_path") or "."),
        "phase": phase,
        "suggested_phase": suggested_phase,
        "cache_policy": cache_policy,
        "context": context,
        "latest_user_message": latest_user_message,
        "source_nodes": source_nodes,
        "task_identity": current_task_identity,
        "task_identity_delta": identity_delta,
        "packet_delta": packet_delta,
        "next_verification_gate": next_gates,
        "warnings": _ordered_unique(warnings),
        "proposed_changes": proposed_changes,
        "validated_changes": validated_changes,
    }


def _recompile_packet(arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    previous_packet = parse_previous_packet(arguments)
    if not isinstance(previous_packet, dict):
        raise ValueError(
            "tmcp_runtime_next output_mode=full requires previous_packet as an object."
        )
    packet_delta = dict(state.get("packet_delta") or {})
    next_gates = _string_list(state.get("next_verification_gate"))
    target_phase = str(state.get("suggested_phase") or state.get("phase") or "start")
    session_project_path = (
        state.get("project_path")
        if arguments.get("session_id") is not None
        else previous_packet.get("project_path") or state.get("project_path")
    )
    source_path = arguments.get("source_path") or arguments.get("project_path")
    if not source_path and arguments.get("session_id") is None:
        source_path = previous_packet.get("project_path")
    compose_arguments = {
        "objective": state.get("combined_objective") or state.get("objective"),
        "project_path": session_project_path,
        "source_path": source_path,
        "phase": target_phase,
        "cache_policy": state.get("cache_policy") or "none",
        "runtime_context": state.get("context") or {},
        "latest_user_message": state.get("latest_user_message") or "",
        "limit": arguments.get("limit", 40),
    }
    for key in (
        "source_paths",
        "include_globs",
        "exclude_globs",
        "max_file_bytes",
        "max_excerpt_chars",
        "follow_symlinks",
        "redact_sensitive",
    ):
        if key in arguments:
            compose_arguments[key] = arguments[key]
    new_packet = _compose_packet(compose_arguments)
    new_packet = merge_packet_delta(new_packet, packet_delta, next_gates=next_gates)
    source_nodes = [
        item
        for item in _json_list(state.get("source_nodes"))
        if isinstance(item, dict)
    ]
    new_packet = _enrich_packet_from_source_nodes(
        new_packet,
        source_nodes,
        _string_list(packet_delta.get("newly_required_reads")),
    )
    new_packet = apply_validated_proposals(
        new_packet, _json_list(state.get("validated_changes"))
    )
    new_packet["task_identity"] = state.get("task_identity") or new_packet.get(
        "task_identity"
    )
    recompile_reason = resolve_recompile_reason(arguments, state)
    packet_change = build_packet_diff(
        previous_packet,
        new_packet,
        packet_delta=packet_delta,
        recompile_reason=recompile_reason,
    )
    if arguments.get("session_id") is not None:
        previous_packet_id = str(previous_packet.get("packet_id") or "")
    else:
        previous_packet_id = str(
            arguments.get("previous_packet_id")
            or previous_packet.get("packet_id")
            or ""
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
        "task_identity": state.get("task_identity"),
        "task_identity_delta": state.get("task_identity_delta"),
        "warnings": state.get("warnings") or [],
        "safety": {
            "stateless": True,
            "cache_trust": "advisory_untrusted",
            "instruction_override_policy": (
                "Recompiled packets never override system, developer, user, or project instructions."
            ),
        },
    }
    new_packet["packet_markdown"] = render_recompiled_packet_markdown(
        recompiled, compose_markdown=render_composed_packet_markdown
    )
    recompiled["packet"] = new_packet
    return recompiled


def _redacted_mapping(value: dict[str, Any]) -> dict[str, Any]:
    safe_value, _ = redact_json_value(value, enabled=True)
    return safe_value if isinstance(safe_value, dict) else {}


def _opaque_storage_key(raw_value: str, display_value: str) -> str:
    digest = hashlib.sha256(raw_value.encode()).hexdigest()[:32]
    return f"{_promotion_slug(display_value)[:80]}-{digest}"


def _redact_result(result: dict[str, Any]) -> dict[str, Any]:
    safe_result, redactions = redact_json_value(result, enabled=True)
    if not isinstance(safe_result, dict):
        raise ValueError("TMCP result must be a JSON object.")
    existing = safe_result.get("redaction_summary")
    summary = dict(existing) if isinstance(existing, dict) else {}
    merge_redactions(summary, redactions)
    safe_result["redaction_summary"] = summary
    return safe_result


def _persist_artifacts(
    output_dir: Path,
    *,
    json_artifacts: dict[str, Any],
    text_artifacts: dict[str, str],
    fresh_bundle: bool,
) -> dict[str, str]:
    if set(json_artifacts).intersection(text_artifacts):
        raise ValueError("Artifact names must be unique.")
    safe_json = _redacted_mapping(json_artifacts)
    safe_text = {
        name: str(redact_json_value(content, enabled=True)[0])
        for name, content in text_artifacts.items()
    }
    if fresh_bundle:
        paths = AtomicArtifactStore.write_bundle(
            output_dir,
            json_artifacts=safe_json,
            text_artifacts=safe_text,
        )
    else:
        store = AtomicArtifactStore.explicit(output_dir)
        paths = {
            name: str(store.write_json(name, payload))
            for name, payload in safe_json.items()
        }
        paths.update(
            {
                name: str(store.write_text(name, content))
                for name, content in safe_text.items()
            }
        )
    return {name: redact_path(path) for name, path in paths.items()}


def _write_review_artifacts(
    output_dir: Path,
    packet: dict[str, Any],
    rubric: dict[str, Any],
    audit_report: dict[str, Any],
    remediation_plan: dict[str, Any],
    handoff: dict[str, Any],
    *,
    fresh_bundle: bool,
) -> dict[str, str]:
    safe_packet = _redacted_mapping(packet)
    safe_rubric = _redacted_mapping(rubric)
    safe_audit_report = _redacted_mapping(audit_report)
    safe_remediation_plan = _redacted_mapping(remediation_plan)
    safe_handoff = _redacted_mapping(handoff)
    paths = _persist_artifacts(
        output_dir,
        json_artifacts={
            "expertise-packet.json": safe_packet,
            "rubric.json": safe_rubric,
            "audit-report.json": safe_audit_report,
            "remediation-plan.json": safe_remediation_plan,
            "implementation-handoff.json": safe_handoff,
        },
        text_artifacts={
            "rubric.md": render_rubric_markdown(safe_rubric),
            "audit-report.md": render_audit_markdown(safe_audit_report),
            "remediation-plan.md": render_remediation_plan_markdown(
                safe_remediation_plan
            ),
        },
        fresh_bundle=fresh_bundle,
    )
    return {
        "expertise_packet": paths["expertise-packet.json"],
        "rubric_json": paths["rubric.json"],
        "rubric_markdown": paths["rubric.md"],
        "audit_report_json": paths["audit-report.json"],
        "audit_report_markdown": paths["audit-report.md"],
        "remediation_plan_json": paths["remediation-plan.json"],
        "remediation_plan_markdown": paths["remediation-plan.md"],
        "implementation_handoff_json": paths["implementation-handoff.json"],
    }


def _default_output_dir(project_root: Path) -> Path:
    return project_root / ".aios" / "reviews" / f"tmcp-mcp-{uuid.uuid4().hex[:8]}"


def _harvest_review_sources(
    project_path: str, objective: str, source_limit: int
) -> tuple[list[dict[str, Any]], list[str]]:
    harvest = _harvest_skills(
        {
            "source_path": project_path,
            "objective": f"Harvest source material for review: {objective}",
            "limit": max(1, source_limit),
            "write_artifacts": False,
        }
    )
    return _json_list(harvest.get("source_nodes")), _string_list(
        harvest.get("warnings")
    )


def _standalone_review_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(arguments["objective"])
    project_path = str(arguments.get("project_path") or ".")
    run_id = f"tmcp-review-plan-{uuid.uuid4().hex[:8]}"
    evidence_items = parse_evidence(arguments.get("evidence_json") or "[]")
    harvested_nodes: list[dict[str, Any]] = []
    harvest_warnings: list[str] = []
    if bool(arguments.get("harvest_sources", True)):
        harvested_nodes, harvest_warnings = _harvest_review_sources(
            str(Path(project_path).expanduser()),
            objective,
            int(arguments.get("source_limit") or 24),
        )
    result = _runtime_build_review_plan(
        objective=objective,
        project_path=str(Path(project_path).expanduser()),
        run_id=run_id,
        evidence_items=evidence_items,
        harvested_nodes=harvested_nodes,
        harvest_warnings=harvest_warnings,
        selected_slice_id=str(arguments.get("selected_slice_id") or "") or None,
    )
    safe_result = _redact_result(result)
    if bool(arguments.get("write_artifacts", True)):
        output_dir = (
            Path(str(arguments["output_dir"])).expanduser()
            if arguments.get("output_dir")
            else _default_output_dir(_require_default_artifact_root(arguments))
        )
        safe_result["artifact_paths"] = _write_review_artifacts(
            output_dir,
            dict(safe_result["expertise_packet"]),
            dict(safe_result["rubric"]),
            dict(safe_result["audit_report"]),
            dict(safe_result["remediation_plan"]),
            dict(safe_result["implementation_handoff"]),
            fresh_bundle=not bool(arguments.get("output_dir")),
        )
    return safe_result


def _source_project_path(arguments: dict[str, Any]) -> str:
    return _runtime_source_project_path(arguments)


def _require_default_artifact_root(arguments: dict[str, Any]) -> Path:
    return _runtime_require_default_artifact_root(arguments)


def _runtime_harvest_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    source_paths = _string_list(arguments.get("source_paths"))
    if not source_paths:
        source_path = arguments.get("source_path") or arguments.get("project_path") or "."
        source_paths = [str(source_path)]
    return {
        "objective": str(arguments.get("objective") or ""),
        "source_paths": source_paths,
        "include_globs": arguments.get("include_globs"),
        "exclude_globs": arguments.get("exclude_globs"),
        "limit": arguments.get("limit", 40),
        "max_file_bytes": arguments.get("max_file_bytes", 262144),
        "max_excerpt_chars": arguments.get("max_excerpt_chars", 1200),
        "follow_symlinks": bool(arguments.get("follow_symlinks", False)),
        "redact_sensitive": bool(arguments.get("redact_sensitive", True)),
        "write_artifacts": False,
    }


def _routing_metadata_for(rel_path: str, text: str) -> dict[str, Any]:
    return _domain_routing_metadata_for(rel_path, text)


def _harvest_source_advisories(
    path: Path,
    text: str,
    relative_path: str,
    source_type: str,
) -> list[dict[str, Any]]:
    return harvest_warnings_for_source(
        path,
        text,
        rel_path=relative_path,
        source_type=source_type,
    )


def _source_node_from_text(
    *,
    root_path: str,
    source_path: str,
    relative_path: str,
    text: str,
    max_excerpt_chars: int,
    redactions: dict[str, int],
    source_type: str,
) -> dict[str, Any]:
    return _domain_source_node_from_text(
        root_path=root_path,
        source_path=source_path,
        relative_path=relative_path,
        text=text,
        max_excerpt_chars=max_excerpt_chars,
        redactions=redactions,
        source_type=source_type,
        source_advisories=_harvest_source_advisories,
    )


def _harvest_skills(arguments: dict[str, Any]) -> dict[str, Any]:
    return _runtime_harvest_skills(
        arguments,
        source_advisories=_harvest_source_advisories,
    )


def _node_signal_text(node: dict[str, Any]) -> str:
    return _domain_node_signal_text(node)


def _write_workflow_recommendation_artifacts(
    output_dir: Path,
    result: dict[str, Any],
    *,
    fresh_bundle: bool,
) -> dict[str, str]:
    safe_result = _redacted_mapping(result)
    profile = safe_result.get("priority_profile")
    json_artifacts: dict[str, Any] = {
        "workflow-recommendations.json": safe_result,
    }
    if isinstance(profile, dict):
        json_artifacts["priority-profile.json"] = profile
    adaptive_pack = safe_result.get("adaptive_workflow_pack")
    if isinstance(adaptive_pack, dict):
        json_artifacts["adaptive-workflow-pack.json"] = adaptive_pack
    paths = _persist_artifacts(
        output_dir,
        json_artifacts=json_artifacts,
        text_artifacts={
            "workflow-recommendations.md": render_workflow_recommendations_markdown(
                safe_result
            ),
        },
        fresh_bundle=fresh_bundle,
    )
    result_paths = {
        "recommendation_json": paths["workflow-recommendations.json"],
        "recommendation_markdown": paths["workflow-recommendations.md"],
    }
    if "priority-profile.json" in paths:
        result_paths["priority_profile_json"] = paths["priority-profile.json"]
    if "adaptive-workflow-pack.json" in paths:
        result_paths["adaptive_pack_json"] = paths["adaptive-workflow-pack.json"]
    return result_paths


def _write_promotion_artifacts(
    output_dir: Path, result: dict[str, Any]
) -> dict[str, str]:
    safe_result = _redacted_mapping(result)
    graph = safe_result.get("promotion_graph")
    json_artifacts: dict[str, Any] = {
        "promoted-harvest.json": safe_result,
    }
    if isinstance(graph, dict):
        json_artifacts["promotion-graph.json"] = graph
    adaptive_pack = safe_result.get("adaptive_workflow_pack")
    if isinstance(adaptive_pack, dict):
        json_artifacts["adaptive-workflow-pack.json"] = adaptive_pack
    paths = _persist_artifacts(
        output_dir,
        json_artifacts=json_artifacts,
        text_artifacts={
            "promoted-harvest.md": render_promotion_markdown(safe_result)
        },
        fresh_bundle=False,
    )
    result_paths = {
        "promotion_json": paths["promoted-harvest.json"],
        "promotion_markdown": paths["promoted-harvest.md"],
    }
    if "promotion-graph.json" in paths:
        result_paths["promotion_graph_json"] = paths["promotion-graph.json"]
    if "adaptive-workflow-pack.json" in paths:
        result_paths["adaptive_pack_json"] = paths["adaptive-workflow-pack.json"]
    return result_paths


def _tmcp_home() -> Path:
    configured = globals().get("TMCP_HOME")
    if configured is None:
        configured = os.environ.get("TMCP_HOME", "~/.tmcp")
    return Path(str(configured)).expanduser()


def _promotion_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip(".-_") or "promotion"


def _global_promoted_root() -> Path:
    return _tmcp_home() / "promoted-harvests"


def _global_receipts_root() -> Path:
    return _tmcp_home() / "receipts"


def _normalized_global_graph(result: dict[str, Any]) -> dict[str, Any]:
    graph = dict(result.get("promotion_graph") or {})
    source_nodes: list[dict[str, Any]] = []
    for node in _json_list(graph.get("source_nodes")):
        if not isinstance(node, dict):
            continue
        source_nodes.append(
            {
                "relative_path": node.get("relative_path"),
                "source_type": node.get("source_type"),
                "source_scope": node.get("source_scope"),
                "behavior_atoms": _string_list(node.get("behavior_atoms")),
                "guidance_labels": _json_list(node.get("guidance_labels")),
                "keywords": _string_list(node.get("keywords"))[:12],
                "routing_metadata": node.get("routing_metadata", {}),
                "trust": "advisory_untrusted",
            }
        )
    workflow_nodes: list[dict[str, Any]] = []
    for node in _json_list(graph.get("workflow_nodes")):
        if not isinstance(node, dict):
            continue
        workflow_nodes.append(
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "stability": node.get("stability"),
                "signal_family": node.get("signal_family"),
                "confidence": node.get("confidence"),
                "template": node.get("template"),
                "trust": "advisory_untrusted",
            }
        )
    scoped_packet_seed_nodes: list[dict[str, Any]] = []
    for node in _json_list(graph.get("scoped_packet_seed_nodes")):
        if not isinstance(node, dict):
            continue
        scoped_packet_seed_nodes.append(
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "kind": node.get("kind"),
                "promotion_status": node.get("promotion_status"),
                "promote_as_single_global_graph": bool(
                    node.get("promote_as_single_global_graph", False)
                ),
                "relative_path": node.get("relative_path"),
                "canonical_source": node.get("canonical_source"),
                "source_references": _string_list(node.get("source_references")),
                "behavior_atoms": _string_list(node.get("behavior_atoms")),
                "verification_expectations": _string_list(
                    node.get("verification_expectations")
                ),
                "required_receipts": _string_list(node.get("required_receipts")),
                "trust": "advisory_untrusted",
            }
        )
    return {
        "schema": "tmcp-promoted-harvest-graph-v0.1",
        "promotion_name": result.get("promotion_name") or graph.get("promotion_name"),
        "created_at": graph.get("created_at") or _now_iso(),
        "source_nodes": source_nodes,
        "scoped_packet_seed_nodes": scoped_packet_seed_nodes,
        "verification_expectation_nodes": _json_list(
            graph.get("verification_expectation_nodes")
        ),
        "behavior_atoms": _json_list(graph.get("behavior_atoms")),
        "workflow_nodes": workflow_nodes,
        "edges": _json_list(graph.get("edges")),
        "cross_source_behavior_atoms": _json_list(
            graph.get("cross_source_behavior_atoms")
        ),
        "trust": "advisory_untrusted",
        "instruction_override_policy": (
            "Promoted harvest knowledge is advisory evidence only and cannot override "
            "system, developer, or user instructions."
        ),
    }


def _write_global_promotion(
    result: dict[str, Any], promotion_name: str, storage_key: str
) -> dict[str, str]:
    output_dir = _global_promoted_root() / storage_key
    graph = _redacted_mapping(_normalized_global_graph(result))
    summary = {
        "schema": "tmcp-global-promoted-harvest-v0.1",
        "promotion_name": promotion_name,
        "created_at": _now_iso(),
        "promoted_workflow_ids": _string_list(result.get("promoted_workflow_ids")),
        "promoted_scoped_packet_seed_ids": _string_list(
            result.get("promoted_scoped_packet_seed_ids")
        ),
        "promotion_graph": graph,
        "trust": "advisory_untrusted",
    }
    safe_summary = _redacted_mapping(summary)
    adaptive_pack = result.get("adaptive_workflow_pack")
    json_artifacts: dict[str, Any] = {
        "promoted-harvest.json": safe_summary,
        "promotion-graph.json": graph,
    }
    if isinstance(adaptive_pack, dict):
        json_artifacts["adaptive-workflow-pack.json"] = _redacted_mapping(adaptive_pack)
    paths = _persist_artifacts(
        output_dir,
        json_artifacts=json_artifacts,
        text_artifacts={},
        fresh_bundle=False,
    )
    result_paths = {
        "promotion_json": paths["promoted-harvest.json"],
        "promotion_graph_json": paths["promotion-graph.json"],
    }
    if "adaptive-workflow-pack.json" in paths:
        result_paths["adaptive_pack_json"] = paths["adaptive-workflow-pack.json"]
    return result_paths


def _append_global_cache_warning(warnings: list[str], warning: str) -> None:
    if len(warnings) < MAX_GLOBAL_CACHE_WARNINGS:
        warnings.append(warning)


def _bounded_global_cache_limit(value: object) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(requested, MAX_GLOBAL_CACHE_ENTRIES))


def _cache_json_is_bounded(value: object) -> bool:
    pending: list[tuple[object, int]] = [(value, 1)]
    node_count = 0
    while pending:
        current, depth = pending.pop()
        node_count += 1
        if node_count > MAX_GLOBAL_CACHE_JSON_NODES or depth > MAX_GLOBAL_CACHE_JSON_DEPTH:
            return False
        if isinstance(current, dict):
            for key, item in current.items():
                pending.append((key, depth + 1))
                pending.append((item, depth + 1))
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return True


def _safe_global_cache_entries(
    root: Path,
    *,
    filename: str | None,
    limit: int = MAX_GLOBAL_CACHE_ENTRIES,
) -> tuple[list[tuple[dict[str, Any], str, int]], list[str]]:
    try:
        root.lstat()
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [
            "Could not inspect TMCP global cache root "
            f"{redact_path(root)}: {redact_path(str(exc))}"
        ]
    roots, root_warnings = collect_harvest_roots([root], follow_symlinks=False)
    warnings = list(root_warnings[:MAX_GLOBAL_CACHE_WARNINGS])
    if len(roots) != 1 or roots[0].kind != "directory":
        return [], warnings
    entry_limit = _bounded_global_cache_limit(limit)
    if entry_limit == 0:
        return [], warnings
    include_globs = [f"*/{filename}"] if filename is not None else ["*.json"]
    candidates, traversal_warnings = iter_harvest_candidates(
        roots,
        include_globs,
        [],
        set(),
        follow_symlinks=False,
        max_candidates=MAX_GLOBAL_CACHE_CANDIDATES,
        max_scan_entries=MAX_GLOBAL_CACHE_SCAN_ENTRIES,
        max_relative_depth=2,
    )
    for warning in traversal_warnings:
        _append_global_cache_warning(warnings, warning)

    eligible_candidates: list[tuple[Any, os.stat_result]] = []
    matching_candidate_count = 0
    for candidate in candidates:
        parts = Path(candidate.relative_path).parts
        if len(parts) != 2 or (filename is not None and parts[-1] != filename):
            continue
        matching_candidate_count += 1
        if matching_candidate_count > MAX_GLOBAL_CACHE_CANDIDATES:
            _append_global_cache_warning(
                warnings,
                "Global cache candidate limit reached; skipped additional entries.",
            )
            break
        try:
            metadata = candidate.resolved_path.lstat()
        except OSError as exc:
            _append_global_cache_warning(
                warnings,
                "Could not inspect global cache entry "
                f"{candidate.display_path}: {redact_path(str(exc))}",
            )
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino)
            != (candidate.device, candidate.inode)
        ):
            _append_global_cache_warning(
                warnings,
                "Skipped global cache entry that changed before reading: "
                f"{candidate.display_path}",
            )
            continue
        if metadata.st_size > MAX_GLOBAL_CACHE_ENTRY_BYTES:
            _append_global_cache_warning(
                warnings,
                "Skipped large global cache entry "
                f"{candidate.display_path} ({metadata.st_size} bytes > "
                f"{MAX_GLOBAL_CACHE_ENTRY_BYTES})",
            )
            continue
        eligible_candidates.append((candidate, metadata))

    eligible_candidates.sort(key=lambda item: item[1].st_mtime_ns, reverse=True)
    entries: list[tuple[dict[str, Any], str, int]] = []
    for candidate, _ in eligible_candidates[:entry_limit]:
        source, warning = read_harvest_text(
            candidate,
            MAX_GLOBAL_CACHE_ENTRY_BYTES,
            redact_sensitive=True,
        )
        if warning or source is None:
            _append_global_cache_warning(
                warnings,
                warning
                or f"Skipped unreadable global cache entry {candidate.display_path}.",
            )
            continue
        try:
            payload = json.loads(source.text)
        except (json.JSONDecodeError, MemoryError, RecursionError, ValueError) as exc:
            _append_global_cache_warning(
                warnings,
                "Skipped invalid global cache entry "
                f"{candidate.display_path}: {redact_path(str(exc))}",
            )
            continue
        if not isinstance(payload, dict):
            _append_global_cache_warning(
                warnings,
                "Skipped non-object global cache entry: " f"{candidate.display_path}",
            )
            continue
        if not _cache_json_is_bounded(payload):
            _append_global_cache_warning(
                warnings,
                "Skipped overly complex global cache entry: "
                f"{candidate.display_path}",
            )
            continue
        try:
            metadata = candidate.resolved_path.lstat()
        except OSError:
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != (candidate.device, candidate.inode)
        ):
            _append_global_cache_warning(
                warnings,
                "Skipped global cache entry that changed while reading: "
                f"{candidate.display_path}",
            )
            continue
        try:
            safe_payload, _ = redact_json_value(payload, enabled=True)
        except (MemoryError, RecursionError):
            _append_global_cache_warning(
                warnings,
                "Skipped global cache entry that could not be redacted safely: "
                f"{candidate.display_path}",
            )
            continue
        if isinstance(safe_payload, dict):
            entries.append(
                (
                    safe_payload,
                    candidate.display_path,
                    metadata.st_mtime_ns,
                )
            )
    return entries, warnings[:MAX_GLOBAL_CACHE_WARNINGS]


def _cached_promotion_graph(
    payload: dict[str, Any], display_path: str
) -> tuple[dict[str, Any] | None, str | None]:
    required_list_fields = (
        "source_nodes",
        "behavior_atoms",
        "workflow_nodes",
        "edges",
    )
    if (
        payload.get("schema") != "tmcp-promoted-harvest-graph-v0.1"
        or payload.get("trust") != "advisory_untrusted"
        or not isinstance(payload.get("created_at"), str)
        or not isinstance(payload.get("promotion_name"), (str, type(None)))
        or any(not isinstance(payload.get(field), list) for field in required_list_fields)
    ):
        return (
            None,
            "Skipped global cache graph with unexpected schema: " f"{display_path}",
        )

    catalog = workflow_catalog_by_id()
    workflow_nodes: list[dict[str, str]] = []
    unknown_nodes = False
    seen_workflows: set[str] = set()
    for node in _json_list(payload.get("workflow_nodes")):
        if not isinstance(node, dict):
            unknown_nodes = True
            continue
        workflow_id = str(node.get("id") or "")
        if workflow_id not in catalog:
            unknown_nodes = True
            continue
        if workflow_id in seen_workflows:
            continue
        seen_workflows.add(workflow_id)
        workflow_nodes.append({"id": workflow_id})

    if not workflow_nodes:
        return (
            None,
            "Skipped global cache graph without recognized workflow IDs: "
            f"{display_path}",
        )
    promotion_name = payload.get("promotion_name")
    safe_promotion_name, _ = redact_json_value(promotion_name, enabled=True)
    graph = {
        "schema": "tmcp-promoted-harvest-graph-v0.1",
        "promotion_name": safe_promotion_name,
        "workflow_nodes": workflow_nodes,
        "_global_cache_path": display_path,
        "trust": "advisory_untrusted",
    }
    warning = None
    if unknown_nodes:
        warning = "Skipped unknown workflow IDs in global cache graph: " f"{display_path}"
    return graph, warning


def _cached_receipt(
    payload: dict[str, Any], display_path: str
) -> tuple[dict[str, Any] | None, str | None]:
    required_string_fields = (
        "created_at",
        "packet_id",
        "outcome",
        "instruction_override_policy",
    )
    required_list_fields = (
        "activated_atoms",
        "ignored_atoms",
        "commands_run",
        "verification_results",
        "user_overrides",
    )
    if (
        payload.get("schema") != RUN_RECEIPT_SCHEMA
        or payload.get("trust") != "advisory_untrusted"
        or any(not isinstance(payload.get(field), str) for field in required_string_fields)
        or any(
            not isinstance(payload.get(field), list)
            or not all(isinstance(item, str) for item in payload[field])
            for field in required_list_fields
        )
    ):
        return (
            None,
            "Skipped global cache receipt with unexpected schema: " f"{display_path}",
        )
    safe_packet_id, _ = redact_json_value(payload["packet_id"], enabled=True)
    return (
        {
            "schema": RUN_RECEIPT_SCHEMA,
            "packet_id": safe_packet_id,
            "_global_cache_path": display_path,
            "trust": "advisory_untrusted",
        },
        None,
    )


def _load_global_promoted_graphs(
    cache_policy: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if cache_policy == "none":
        return [], []
    entries, warnings = _safe_global_cache_entries(
        _global_promoted_root(),
        filename="promotion-graph.json",
    )
    graphs: list[dict[str, Any]] = []
    for payload, display_path, _ in entries:
        graph, warning = _cached_promotion_graph(payload, display_path)
        if warning:
            _append_global_cache_warning(warnings, warning)
        if graph is not None:
            graphs.append(graph)
    return graphs, warnings[:MAX_GLOBAL_CACHE_WARNINGS]


def _load_recent_receipts(
    cache_policy: str, *, limit: int = 25
) -> tuple[list[dict[str, Any]], list[str]]:
    if cache_policy == "none":
        return [], []
    receipt_limit = _bounded_global_cache_limit(limit)
    if receipt_limit == 0:
        return [], []
    entries, warnings = _safe_global_cache_entries(
        _global_receipts_root(),
        filename=None,
        limit=receipt_limit,
    )
    entries.sort(key=lambda item: item[2], reverse=True)
    receipts: list[dict[str, Any]] = []
    for payload, display_path, _ in entries:
        receipt, warning = _cached_receipt(payload, display_path)
        if warning:
            _append_global_cache_warning(warnings, warning)
        if receipt is not None:
            receipts.append(receipt)
    return receipts, warnings[:MAX_GLOBAL_CACHE_WARNINGS]


def _compose_harvest_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    project_path = str(arguments.get("project_path") or ".")
    source_paths = _string_list(arguments.get("source_paths"))
    if not source_paths:
        source_path = arguments.get("source_path")
        source_paths = [str(source_path)] if source_path else [project_path]
    harvest_args: dict[str, Any] = {
        "objective": str(arguments.get("objective") or ""),
        "source_paths": source_paths,
        "include_globs": arguments.get("include_globs"),
        "exclude_globs": arguments.get("exclude_globs"),
        "limit": arguments.get("limit", 40),
        "max_file_bytes": arguments.get("max_file_bytes", 262144),
        "max_excerpt_chars": arguments.get("max_excerpt_chars", 1200),
        "follow_symlinks": bool(arguments.get("follow_symlinks", False)),
        "redact_sensitive": bool(arguments.get("redact_sensitive", True)),
        "write_artifacts": False,
    }
    return harvest_args


def _routing_metadata(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("routing_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _compose_context(arguments: dict[str, Any]) -> dict[str, Any]:
    context = arguments.get("runtime_context")
    return context if isinstance(context, dict) else {}


def _node_active_instructions(node: dict[str, Any]) -> list[str]:
    rel_path = str(node.get("relative_path") or node.get("path") or "source")
    text = _node_signal_text(node)
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
    if not instructions:
        atoms = ", ".join(_string_list(node.get("behavior_atoms"))[:4])
        if atoms:
            instructions.append(
                f"Apply relevant harvested behavior atoms from {rel_path}: {atoms}."
            )
    return instructions


def _compose_packet_from_source_nodes(
    arguments: dict[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    objective = str(arguments.get("objective") or "").strip()
    if not objective:
        raise ValueError("tmcp_compose_packet requires objective.")
    phase = str(arguments.get("phase") or "start")
    cache_policy = str(arguments.get("cache_policy") or "none")
    context = _compose_context(arguments)
    identity_context = dict(context)
    identity_context["latest_user_message"] = str(arguments.get("latest_user_message") or "")
    preliminary_routes = _string_list(
        derive_task_identity(objective, identity_context).get("active_routes")
    )
    family_context = compose_family_context(
        source_nodes,
        objective,
        context=identity_context,
        active_routes=preliminary_routes,
        node_signal_text=_node_signal_text,
    )
    task_identity = derive_task_identity(
        objective,
        identity_context,
        family_context if family_context else None,
    )
    active_routes = _string_list(task_identity.get("active_routes")) or preliminary_routes
    selected_nodes = select_composition_nodes(
        source_nodes,
        objective,
        phase,
        context,
        family_context=family_context,
        active_routes=active_routes,
        node_signal_text=_node_signal_text,
    )
    declared_load_paths, declared_load_nodes = resolve_declared_load_nodes(
        selected_nodes=selected_nodes,
        source_nodes=source_nodes,
        objective=objective,
        family_context=family_context,
    )
    selected_nodes = merge_composition_nodes(selected_nodes, declared_load_nodes)
    global_graphs, graph_warnings = _load_global_promoted_graphs(cache_policy)
    receipts, receipt_warnings = _load_recent_receipts(cache_policy)
    selected_workflows = select_global_workflows(global_graphs, objective)
    active_instructions: list[str] = []
    required_reads: list[str] = []
    tool_script_prompts: list[str] = []
    verification_gates: list[str] = []
    stop_conditions: list[str] = []
    active_atoms: list[str] = []
    evidence_citations: list[dict[str, Any]] = []

    for node in selected_nodes:
        metadata = _routing_metadata(node)
        active_instructions.extend(_node_active_instructions(node))
        required_reads.extend(_string_list(metadata.get("required_reads")))
        tool_script_prompts.extend(_string_list(metadata.get("tool_script_prompts")))
        verification_gates.extend(
            filter_source_verification_gates(
                _string_list(metadata.get("verification_gates")),
                objective,
                context,
            )
        )
        stop_conditions.extend(_string_list(metadata.get("stop_conditions")))
        active_atoms.extend(_string_list(node.get("behavior_atoms")))
        evidence_citations.append(
            {
                "source": node.get("relative_path"),
                "path": node.get("path"),
                "trust": node.get("trust", "untrusted_harvested_text"),
                "matched_atoms": _string_list(node.get("behavior_atoms"))[:5],
            }
        )

    required_reads.extend(matching_reference_reads(source_nodes, objective))
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

    ignored_sources = [
        {
            "source": node.get("relative_path"),
            "reason": "No objective, phase, command, or runtime-context match for this packet.",
        }
        for node in source_nodes
        if node not in selected_nodes
    ][:12]
    conflicts: list[dict[str, Any]] = []
    selected_text = " ".join(_node_signal_text(node) for node in selected_nodes)
    if "npm" in selected_text and "pnpm" in selected_text:
        conflicts.append(
            {
                "id": "javascript_package_manager",
                "detail": "Harvested sources mention npm and pnpm; higher-priority user/project rules decide.",
            }
        )

    global_cache = {
        "cache_policy": cache_policy,
        "tmcp_home": redact_path(_tmcp_home()),
        "promoted_graph_count": len(global_graphs),
        "receipt_count": len(receipts),
        "warnings": graph_warnings + receipt_warnings,
        "trust": "advisory_untrusted",
    }
    return build_composed_packet(
        composed_packet_schema=COMPOSED_PACKET_SCHEMA,
        receipt_schema=RUN_RECEIPT_SCHEMA,
        objective=objective,
        project_path=str(arguments.get("project_path") or "."),
        phase=phase,
        task_identity=task_identity,
        family_context=family_context,
        source_nodes=source_nodes,
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
        receipt_count=len(receipts),
        user_overrides=_string_list(arguments.get("user_overrides")),
    )


def _compose_packet(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(arguments.get("objective") or "").strip()
    if not objective:
        raise ValueError("tmcp_compose_packet requires objective.")
    store = _packet_session_store(arguments)
    harvest = _harvest_skills(_compose_harvest_arguments(arguments))
    source_nodes = [
        item
        for item in _json_list(harvest.get("source_nodes"))
        if isinstance(item, dict)
    ]
    packet = _compose_packet_from_source_nodes(arguments, source_nodes=source_nodes)
    if store is not None:
        packet["session"] = store.create(packet).metadata()
    return packet


def _compose_evaluation_row(
    row: dict[str, Any],
    project_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compose one redacted evaluation row without reading its source path."""

    source_nodes: list[dict[str, Any]] = []
    if str(row.get("variant_id") or "") != "baseline":
        attachment = row.get("skill_attachment")
        if not isinstance(attachment, str):
            raise ValueError("Evaluation row requires a text skill_attachment.")
        source_nodes.append(
            _source_node_from_text(
                root_path=redact_path(project_path or "."),
                source_path=redact_path(str(row.get("skill_path") or "SKILL.md")),
                relative_path="SKILL.md",
                text=attachment,
                max_excerpt_chars=1200,
                redactions={},
                source_type="skill_definition",
            )
        )
    return _compose_packet_from_source_nodes(
        {
            "objective": str(row.get("prompt") or "Evaluate skill behavior."),
            "project_path": redact_path(project_path or "."),
            "phase": "start",
            "cache_policy": "none",
            "redact_sensitive": True,
        },
        source_nodes=source_nodes,
    )


def _packet_session_store(arguments: dict[str, Any]) -> PacketSessionStore | None:
    session_id = arguments.get("session_id")
    if session_id is None:
        return None
    project_path = arguments.get("project_path")
    if isinstance(project_path, bool) or not isinstance(project_path, (str, Path)):
        raise ValueError("session_id requires an explicit project_path.")
    path = Path(project_path).expanduser()
    if not str(project_path).strip() or not path.is_absolute():
        raise ValueError("session_id requires an absolute project_path.")
    return PacketSessionStore.open(path, session_id)


def _runtime_next(arguments: dict[str, Any]) -> dict[str, Any]:
    output_mode = str(arguments.get("output_mode") or "delta").strip().lower()
    session_id = arguments.get("session_id")
    if session_id is not None and output_mode != "full":
        raise ValueError("session_id requires tmcp_runtime_next output_mode=full.")
    runtime_arguments = dict(arguments)
    session_snapshot = None
    if session_id is not None:
        if "previous_packet" in arguments:
            raise ValueError("session_id cannot be combined with previous_packet.")
        session_store = _packet_session_store(arguments)
        if session_store is None:
            raise RuntimeError("Packet session was not initialized.")
        session_snapshot = session_store.load()
        stored_packet_id = str(session_snapshot.packet.get("packet_id") or "")
        previous_packet_id = arguments.get("previous_packet_id")
        if (
            previous_packet_id is not None
            and str(previous_packet_id) != stored_packet_id
        ):
            raise ValueError("previous_packet_id must match the packet in session_id.")
        runtime_arguments["project_path"] = str(session_store.project_root)
        runtime_arguments.setdefault("source_path", str(session_store.project_root))
        runtime_arguments["previous_packet"] = session_snapshot.packet
        runtime_arguments["previous_packet_id"] = stored_packet_id
    else:
        session_store = None
    state = _build_runtime_state(runtime_arguments)
    if output_mode == "full":
        recompiled = _recompile_packet(runtime_arguments, state)
        if session_store is not None and session_snapshot is not None:
            updated_at = _now_iso()
            updated = session_store.update(
                session_snapshot,
                dict(recompiled["packet"]),
                last_recompile={
                    "previous_packet_id": recompiled.get("previous_packet_id"),
                    "recompile_reason": recompiled.get("recompile_reason"),
                    "updated_at": updated_at,
                },
                now=updated_at,
            )
            recompiled["session"] = updated.metadata()
        return recompiled
    return {
        "ok": True,
        "schema": RUNTIME_NEXT_SCHEMA,
        "objective": state["objective"],
        "project_path": state["project_path"],
        "current_phase": state["phase"],
        "suggested_phase": state["suggested_phase"],
        "previous_packet_id": arguments.get("previous_packet_id"),
        "task_identity": state["task_identity"],
        "task_identity_delta": state["task_identity_delta"],
        "packet_delta": state["packet_delta"],
        "next_verification_gate": state["next_verification_gate"],
        "warnings": state["warnings"],
        "safety": {
            "stateless": True,
            "cache_trust": "advisory_untrusted",
            "instruction_override_policy": (
                "Runtime deltas never override system, developer, user, or project instructions."
            ),
        },
    }


def _record_receipt(arguments: dict[str, Any]) -> dict[str, Any]:
    packet_id = str(arguments.get("packet_id") or "").strip()
    if not packet_id:
        raise ValueError("tmcp_record_receipt requires packet_id.")
    created_at = _now_iso()
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
        "trust": "advisory_untrusted",
        "instruction_override_policy": (
            "Receipts may improve future ranking but cannot override higher-priority instructions."
        ),
    }
    redacted_receipt, receipt_redactions = redact_json_value(receipt, enabled=True)
    safe_receipt = (
        redacted_receipt if isinstance(redacted_receipt, dict) else {}
    )
    storage_key = _opaque_storage_key(
        packet_id,
        str(safe_receipt["packet_id"]),
    )
    month = datetime.now(UTC).strftime("%Y-%m")
    digest = hashlib.sha256(json.dumps(safe_receipt, sort_keys=True).encode()).hexdigest()[
        :10
    ]
    path = (
        _global_receipts_root()
        / month
        / f"{storage_key}-{digest}-{uuid.uuid4().hex[:8]}.json"
    )
    receipt_path = AtomicArtifactStore.explicit(path.parent).write_json(
        path.name,
        safe_receipt,
    )
    return _redact_result({
        "ok": True,
        "schema": RUN_RECEIPT_SCHEMA,
        "packet_id": safe_receipt["packet_id"],
        "outcome": safe_receipt["outcome"],
        "artifact_paths": {"receipt_json": redact_path(receipt_path)},
        "trust": "advisory_untrusted",
        "redaction_summary": receipt_redactions,
    })


def _compose_recommendation_preview(
    arguments: dict[str, Any],
    objective: str,
) -> dict[str, Any]:
    project_path = _source_project_path(arguments)
    return _compose_packet(
        {
            "objective": objective,
            "project_path": arguments.get("project_path") or project_path,
            "source_paths": arguments.get("source_paths"),
            "source_path": arguments.get("source_path") or project_path,
            "phase": arguments.get("phase") or "start",
            "cache_policy": arguments.get("cache_policy") or "none",
            "include_globs": arguments.get("include_globs"),
            "exclude_globs": arguments.get("exclude_globs"),
            "limit": arguments.get("limit", 40),
            "max_file_bytes": arguments.get("max_file_bytes", 262144),
            "max_excerpt_chars": arguments.get("max_excerpt_chars", 1200),
            "follow_symlinks": bool(arguments.get("follow_symlinks", False)),
            "redact_sensitive": bool(arguments.get("redact_sensitive", True)),
        }
    )


def _recommend_workflows(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(
        arguments.get("objective")
        or "Recommend custom TMCP workflows from harvested skill signals."
    )
    safe_result = _redact_result(
        _runtime_recommend_workflows(
            arguments,
            source_advisories=_harvest_source_advisories,
            compose_preview=(
                (lambda: _compose_recommendation_preview(arguments, objective))
                if bool(arguments.get("compose", False))
                else None
            ),
        )
    )
    if bool(arguments.get("write_artifacts", False)):
        output_dir = (
            Path(str(arguments["output_dir"])).expanduser()
            if arguments.get("output_dir")
            else _require_default_artifact_root(arguments)
            / ".tmcp"
            / f"workflow-recommendations-{uuid.uuid4().hex[:8]}"
        )
        safe_result["artifact_paths"] = _write_workflow_recommendation_artifacts(
            output_dir,
            safe_result,
            fresh_bundle=not bool(arguments.get("output_dir")),
        )
    else:
        safe_result["artifact_paths"] = {}
    return safe_result


def _promote_harvest(arguments: dict[str, Any]) -> dict[str, Any]:
    result = _runtime_promote_harvest(
        arguments,
        source_advisories=_harvest_source_advisories,
        compose_preview_for_objective=(
            lambda objective: _compose_recommendation_preview(arguments, objective)
        ),
        now_iso=_now_iso,
    )
    promotion_name = str(result["promotion_name"])
    safe_result = _redact_result(result)
    promotion_storage_key = _opaque_storage_key(
        promotion_name,
        str(safe_result["promotion_name"]),
    )
    write_artifacts = bool(arguments.get("write_artifacts", True))
    has_promotable_output = bool(
        safe_result.get("promoted_workflow_ids")
        or safe_result.get("promoted_scoped_packet_seed_ids")
    )
    if write_artifacts and has_promotable_output:
        output_dir = (
            Path(str(arguments["output_dir"])).expanduser()
            if arguments.get("output_dir")
            else _require_default_artifact_root(arguments)
            / ".tmcp"
            / "promoted-harvests"
            / promotion_storage_key
        )
        safe_result["artifact_paths"] = _write_promotion_artifacts(
            output_dir,
            safe_result,
        )
    else:
        safe_result["artifact_paths"] = {}
    if (
        write_artifacts
        and has_promotable_output
        and bool(arguments.get("persist_global", True))
        and bool(safe_result.get("promoted_workflow_ids"))
    ):
        safe_result["global_artifact_paths"] = _write_global_promotion(
            safe_result,
            str(safe_result["promotion_name"]),
            promotion_storage_key,
        )
    else:
        safe_result["global_artifact_paths"] = {}
    return safe_result


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "tmcp_doctor":
        client = str(arguments.get("client") or "auto")
        plugin_root = PLUGIN_ROOT
        checks = [
            {
                "id": "plugin_root",
                "status": "pass" if plugin_root.exists() else "fail",
                "detail": str(plugin_root),
            },
            {
                "id": "node_launcher",
                "status": "pass"
                if (plugin_root / "scripts" / "tmcp_launcher.mjs").exists()
                else "fail",
                "detail": "scripts/tmcp_launcher.mjs",
            },
            {
                "id": "node_runtime",
                "status": "pass" if shutil.which("node") else "fail",
                "detail": "Install Node.js 20+ if the MCP host cannot launch node.",
            },
            {
                "id": "python_server",
                "status": "pass"
                if (plugin_root / "scripts" / "tmcp_mcp_server.py").exists()
                else "fail",
                "detail": "scripts/tmcp_mcp_server.py",
            },
            {
                "id": "python_runtime",
                "status": "pass"
                if (
                    shutil.which("python3")
                    or shutil.which("python")
                    or shutil.which("py")
                )
                else "fail",
                "detail": "Set TMCP_PYTHON if automatic Python discovery fails.",
            },
            {
                "id": "secure_artifact_persistence",
                "status": "pass"
                if artifact_persistence_available()
                else "limited",
                "detail": (
                    "Secure local artifact writes are available."
                    if artifact_persistence_available()
                    else "Secure artifact writes are unavailable on this platform; "
                    "rerun write-capable tools with write_artifacts=false."
                ),
            },
            {
                "id": "aios_adapter",
                "status": "pass" if _aios_available() else "optional",
                "detail": (
                    f"AIOS_ROOT={AIOS_ROOT}"
                    if AIOS_ROOT is not None
                    else "AIOS_ROOT is not set; standalone TMCP is available."
                ),
            },
        ]
        failed = [check for check in checks if check["status"] == "fail"]
        install_paths = {
            "skill_only": (
                "Copy skills/tmcp into a skills directory. Use manual packet synthesis "
                "unless the host also exposes this package's launcher."
            ),
            "repo_checkout": (
                "Clone TMCP and run node scripts/tmcp_launcher.mjs doctor from the repo root."
            ),
            "codex_plugin_cache": (
                "Install as a Codex plugin; MCP config should launch relative "
                "scripts/tmcp_launcher.mjs from the plugin root."
            ),
            "claude_code": "Run: claude plugin marketplace add jakyeamos/tmcp && claude plugin install tmcp@tmcp",
            "claude_desktop": "Add the node launcher as a local stdio MCP server in claude_desktop_config.json.",
            "plain_mcp": "Use command node with args [scripts/tmcp_launcher.mjs] and cwd set to the TMCP repo.",
            "aios_backed": (
                "Set AIOS_ROOT explicitly only when you want optional AIOS storage/adapter behavior."
            ),
        }
        codex_tool_discovery = {
            "known_gap": (
                "Some Codex personal-plugin installs expose TMCP skills while deferred "
                "tool discovery does not surface the plugin MCP tools. In that case, "
                "the installed launcher can still be used directly."
            ),
            "symptom": (
                "tool_search for tmcp_explain, tmcp_doctor, or "
                "expert_rubric_review_plan returns no TMCP tools."
            ),
            "verify_launcher": [
                "node scripts/tmcp_launcher.mjs doctor --client codex",
                "node scripts/tmcp_launcher.mjs list-tools",
            ],
            "codex_mcp_config": {
                "mcp_servers": {
                    "tmcp": {
                        "command": "node",
                        "args": ["scripts/tmcp_launcher.mjs"],
                        "cwd": str(plugin_root),
                    }
                }
            },
            "fallback": (
                "Run the equivalent node scripts/tmcp_launcher.mjs CLI command from "
                "the TMCP plugin root, then cite the generated JSON/artifacts in the "
                "agent response."
            ),
        }
        return {
            "ok": not failed,
            "schema": "tmcp-doctor-v0.1",
            "client": client,
            "plugin_root": str(plugin_root),
            "checks": checks,
            "recommended_install_paths": install_paths,
            "codex_tool_discovery": codex_tool_discovery
            if client in {"auto", "codex"}
            else None,
            "smoke_test": {
                "tool": "tmcp_status",
                "expected": "structuredContent.standalone.available == true",
            },
            "next_action": (
                "Run tmcp_status, then tmcp_explain with your objective."
                if not failed
                else "Fix failing checks, then rerun tmcp_doctor."
            ),
            "missing_launcher_remediation": (
                "If no MCP tool, local CLI, repo/plugin launcher, or AIOS adapter is available, "
                "clone or copy TMCP, run node scripts/tmcp_launcher.mjs doctor from the TMCP root, "
                "and set TMCP_PYTHON if Python discovery fails. Until then, synthesize packets "
                "manually using sources inspected, skipped sources, packet summary, behavior atoms, "
                "evidence gaps, recommendation/remediation, and verification expectations."
            ),
        }
    if name == "tmcp_status":
        artifact_persistence = artifact_persistence_available()
        capabilities = [
            "packet_compile",
            "packet_composition",
            "runtime_next",
            "receipt_recording",
            "portable_skill_harvest",
            "multi_root_harvest",
            "global_cache",
            "source_type_classification",
            "workflow_recommendation",
            "harvest_promotion",
            "expert_rubric_review_plan",
        ]
        if artifact_persistence:
            capabilities.append("artifact_write")
        return {
            "ok": True,
            "schema": "tmcp-status-v0.1",
            "standalone": {
                "available": True,
                "plugin_root": str(PLUGIN_ROOT),
                "capabilities": capabilities,
                "artifact_persistence": {
                    "available": artifact_persistence,
                    "detail": (
                        "Secure descriptor-relative no-follow artifact writes are available."
                        if artifact_persistence
                        else "Secure artifact writes are unavailable on this platform; "
                        "write-capable tools fail closed."
                    ),
                },
            },
            "aios_adapter": {
                "available": _aios_available(),
                "aios_root": str(AIOS_ROOT) if AIOS_ROOT is not None else None,
                "configured": AIOS_ROOT is not None,
                "role": "optional storage and adapter layer",
            },
        }
    if name == "tmcp_explain":
        adapter = str(arguments.get("adapter") or "auto")
        if _should_use_aios(adapter):
            args = [
                "tmcp",
                "explain",
                str(arguments["objective"]),
                "--project-path",
                str(arguments.get("project_path") or "."),
                "--json",
            ]
            if arguments.get("phase"):
                args.extend(["--phase", str(arguments["phase"])])
            if arguments.get("domain"):
                args.extend(["--domain", str(arguments["domain"])])
            payload = _run_aios(args)
            if payload.get("ok") or adapter == "aios":
                if bool(arguments.get("compose", False)):
                    payload["composed_packet"] = _compose_packet(
                        {
                            "objective": arguments["objective"],
                            "project_path": arguments.get("project_path") or ".",
                            "source_path": arguments.get("source_path")
                            or arguments.get("project_path")
                            or ".",
                            "phase": arguments.get("phase") or "start",
                            "cache_policy": arguments.get("cache_policy") or "none",
                        }
                    )
                return payload
        result = {
            "ok": True,
            "adapter": "standalone",
            "command": "tmcp-explain",
            "data_status": "compiled",
            "packet": compile_standalone_packet(
                objective=str(arguments["objective"]),
                project_path=str(arguments.get("project_path") or "."),
                phase=str(arguments.get("phase") or "") or None,
                domain=str(arguments.get("domain") or "") or None,
            ),
        }
        if bool(arguments.get("compose", False)):
            result["composed_packet"] = _compose_packet(
                {
                    "objective": arguments["objective"],
                    "project_path": arguments.get("project_path") or ".",
                    "source_path": arguments.get("source_path")
                    or arguments.get("project_path")
                    or ".",
                    "phase": arguments.get("phase") or "start",
                    "cache_policy": arguments.get("cache_policy") or "none",
                }
            )
        return result
    if name == "tmcp_harvest_skills":
        return _harvest_skills(arguments)
    if name == "tmcp_evaluate_skills":
        return evaluate_skills(
            arguments,
            compose_evaluation_row=_compose_evaluation_row,
        )
    if name == "tmcp_recommend_workflows":
        return _recommend_workflows(arguments)
    if name == "tmcp_compose_packet":
        return _compose_packet(arguments)
    if name == "tmcp_runtime_next":
        return _runtime_next(arguments)
    if name == "tmcp_record_receipt":
        return _record_receipt(arguments)
    if name == "tmcp_promote_harvest":
        return _promote_harvest(arguments)
    if name == "expert_rubric_review_plan":
        adapter = str(arguments.get("adapter") or "auto")
        if adapter == "aios":
            if not _aios_available():
                return _redact_result(_run_aios([]))
            if bool(arguments.get("write_artifacts", True)):
                raise ArtifactStorageError(
                    "The AIOS review adapter only supports write_artifacts=false. "
                    "Use adapter=standalone for persisted review artifacts."
                )
            project_path = str(arguments.get("project_path") or ".")
            args = [
                "tmcp",
                "review-plan",
                str(arguments["objective"]),
                "--project-path",
                project_path,
                "--evidence-json",
                str(arguments.get("evidence_json") or "[]"),
                "--json",
                "--no-write-artifacts",
            ]
            if arguments.get("selected_slice_id"):
                args.extend(
                    ["--selected-slice-id", str(arguments["selected_slice_id"])]
                )
            payload = _run_aios(args)
            safe_payload = _redact_result(payload)
            safe_payload.pop("output_dir", None)
            safe_payload.pop("global_artifact_paths", None)
            safe_payload["artifact_paths"] = {}
            return safe_payload
        return _standalone_review_plan(arguments)
    raise ValueError(f"Unknown TMCP tool: {name}")


def _result(request_id: Any, result: dict[str, Any]) -> None:
    write_message(
        sys.stdout.buffer, {"jsonrpc": "2.0", "id": request_id, "result": result}
    )


def _error(request_id: Any, code: int, message: str) -> None:
    write_message(
        sys.stdout.buffer,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        },
    )


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}
        ],
        "structuredContent": payload,
        "isError": not bool(payload.get("ok", True)),
    }


def _handle(request: dict[str, Any]) -> None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if method == "initialize":
        _result(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "serverInfo": mcp_server_info(),
                "capabilities": {"tools": {}},
            },
        )
        return
    if method == "tools/list":
        _result(
            request_id,
            {
                "tools": mcp_tools(),
            },
        )
        return
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            _error(request_id, -32602, "Tool arguments must be an object.")
            return
        try:
            _result(request_id, _tool_result(_call_tool(name, arguments)))
        except Exception as exc:
            _error(request_id, -32000, str(exc))
        return
    if method in {"notifications/initialized", "ping"}:
        if request_id is not None:
            _result(request_id, {})
        return
    if method in {"resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts"
        _result(request_id, {key: []})
        return
    if request_id is not None:
        _error(request_id, -32601, f"Unsupported method: {method}")


def _run_mcp_stdio() -> None:
    while True:
        message = read_message(sys.stdin.buffer)
        if message is None:
            break
        _handle(message)


def _cli_usage() -> str:
    return cli_usage()


def _decode_cli_value(value: str) -> Any:
    stripped = value.strip()
    if stripped in {"true", "false", "null"}:
        return json.loads(stripped)
    if stripped.startswith(("{", "[")):
        return json.loads(stripped)
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return value


def _set_cli_argument(arguments: dict[str, Any], key: str, value: Any) -> None:
    normalized = key.replace("-", "_")
    if normalized in arguments:
        existing = arguments[normalized]
        if isinstance(existing, list):
            existing.append(value)
        else:
            arguments[normalized] = [existing, value]
        return
    arguments[normalized] = value


def _parse_cli_arguments(argv: list[str]) -> tuple[str, dict[str, Any], bool]:
    if not argv or argv[0] in CLI_HELP_ALIASES:
        return "help", {}, False
    if argv[0] in CLI_LIST_TOOLS_ALIASES:
        return "list-tools", {}, False

    command = argv[0]
    tool_name = CLI_TOOL_ALIASES.get(command)
    if not tool_name:
        raise ValueError(f"Unknown TMCP command: {command}")

    compact = False
    positionals: list[str] = []
    arguments: dict[str, Any] = {}
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--compact":
            compact = True
            index += 1
            continue
        if token in {"-h", "--help"}:
            return "help", {}, compact
        if token.startswith("--no-"):
            _set_cli_argument(arguments, token[5:], False)
            index += 1
            continue
        if token.startswith("--"):
            key = token[2:]
            next_index = index + 1
            if next_index >= len(argv) or argv[next_index].startswith("--"):
                _set_cli_argument(arguments, key, True)
                index += 1
                continue
            value = (
                argv[next_index]
                if key.replace("-", "_") == "session_id"
                else _decode_cli_value(argv[next_index])
            )
            _set_cli_argument(arguments, key, value)
            index += 2
            continue
        positionals.append(token)
        index += 1

    if positionals:
        if tool_name in {"tmcp_explain", "expert_rubric_review_plan"}:
            arguments.setdefault("objective", positionals[0])
        elif tool_name in {"tmcp_compose_packet", "tmcp_runtime_next"}:
            arguments.setdefault("objective", positionals[0])
        elif tool_name == "tmcp_record_receipt":
            arguments.setdefault("packet_id", positionals[0])
        elif tool_name in {
            "tmcp_harvest_skills",
            "tmcp_recommend_workflows",
            "tmcp_promote_harvest",
            "tmcp_evaluate_skills",
        }:
            arguments.setdefault("source_path", positionals[0])
            if len(positionals) > 1:
                arguments.setdefault("objective", positionals[1])
        elif tool_name == "tmcp_doctor":
            arguments.setdefault("client", positionals[0])

    for key, value in CLI_COMMAND_DEFAULT_ARGUMENTS.get(command, {}).items():
        arguments.setdefault(key, value)

    _normalize_cli_arguments(tool_name, arguments)
    return tool_name, arguments, compact


def _normalize_cli_arguments(tool_name: str, arguments: dict[str, Any]) -> None:
    schema = TOOLS.get(tool_name, {}).get("inputSchema", {})
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if not isinstance(properties, dict):
        return
    for key, value in list(arguments.items()):
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            continue
        if property_schema.get("type") == "array" and not isinstance(value, list):
            arguments[key] = [value]


def _run_cli(argv: list[str]) -> int:
    try:
        command, arguments, compact = _parse_cli_arguments(argv)
        if command == "help":
            print(_cli_usage())
            return 0
        if command == "list-tools":
            payload: dict[str, Any] = {
                "ok": True,
                "schema": "tmcp-cli-tools-v0.1",
                "tools": mcp_tools(),
            }
        else:
            payload = _call_tool(command, arguments)
        print(
            json.dumps(
                payload,
                separators=(",", ":") if compact else None,
                indent=None if compact else 2,
                sort_keys=True,
            )
        )
        return 0 if bool(payload.get("ok", True)) else 1
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return 2


def main() -> None:
    if len(sys.argv) > 1:
        raise SystemExit(_run_cli(sys.argv[1:]))
    _run_mcp_stdio()


if __name__ == "__main__":
    main()
