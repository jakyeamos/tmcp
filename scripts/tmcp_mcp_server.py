#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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
from tmcp_runtime.domain.composition import (  # noqa: E402
    normalize_cache_policy as _runtime_normalize_cache_policy,
)
from tmcp_runtime.domain.recompile import parse_previous_packet  # noqa: E402
from tmcp_runtime.domain.receipts import (  # noqa: E402
    RUN_RECEIPT_SCHEMA,
    build_recorded_receipt_result as _runtime_build_recorded_receipt_result,
    build_run_receipt as _runtime_build_run_receipt,
)
from tmcp_runtime.domain.runtime_state import (  # noqa: E402
    derive_runtime_state as _runtime_derive_runtime_state,
)
from tmcp_runtime.domain.standalone_packets import (  # noqa: E402
    compile_standalone_packet,
)
from tmcp_runtime.domain.harvest_nodes import (  # noqa: E402
    routing_metadata_for as _domain_routing_metadata_for,
    source_node_from_text as _domain_source_node_from_text,
)
from tmcp_runtime.domain.review_evidence import (  # noqa: E402
    parse_evidence,
)
from tmcp_runtime.domain.workflow_catalog import (  # noqa: E402
    workflow_catalog_by_id,
)
from tmcp_runtime.api.evaluation import evaluate_skills  # noqa: E402
from tmcp_runtime.api.cli import parse_cli_arguments as _parse_cli_arguments  # noqa: E402
from tmcp_runtime.api.registry import (  # noqa: E402
    cli_usage as _cli_usage,
    mcp_server_info,
    mcp_tools,
)
from tmcp_runtime.safety import (  # noqa: E402
    redact_json_value,
    redact_path,
)
from tmcp_runtime.storage import (  # noqa: E402
    ArtifactStorageError,
    AtomicArtifactStore,
    PacketSessionStore,
    artifact_persistence_available,
)
from tmcp_runtime.storage.cache_policy import (  # noqa: E402
    normalize_promoted_graph as _runtime_normalize_promoted_graph,
)
from tmcp_runtime.storage.global_cache import (  # noqa: E402
    GlobalCacheSnapshot,
    read_global_cache_snapshot as _runtime_read_global_cache_snapshot,
)
from tmcp_runtime.services.harvest import (  # noqa: E402
    DEFAULT_HARVEST_EXCLUDE_DIR_NAMES,
    DEFAULT_HARVEST_EXCLUDE_GLOBS,
    DEFAULT_HARVEST_INCLUDE_GLOBS,
    harvest_skills as _runtime_harvest_skills,
    read_only_harvest_arguments as _runtime_read_only_harvest_arguments,
    require_default_artifact_root as _runtime_require_default_artifact_root,
    source_project_path as _runtime_source_project_path,
)
from tmcp_runtime.services.compose import (  # noqa: E402
    compose_packet_from_source_nodes as _runtime_compose_packet_from_source_nodes,
)
from tmcp_runtime.services.evaluation_rendering import (  # noqa: E402
    build_pattern_catalog as _runtime_build_pattern_catalog,
    render_guidebook_markdown as _runtime_render_guidebook_markdown,
)
from tmcp_runtime.services.harvest_advisories import (  # noqa: E402
    harvest_warnings_for_source,
)
from tmcp_runtime.services.evaluation_catalog import (  # noqa: E402
    EFFECTIVE_PATTERNS,
    EVIDENCE_LEVELS,
    V01_ANTI_PATTERNS,
)
from tmcp_runtime.services.recommendations import (  # noqa: E402
    recommend_workflows as _runtime_recommend_workflows,
)
from tmcp_runtime.services.promotion import (  # noqa: E402
    promote_harvest as _runtime_promote_harvest,
)
from tmcp_runtime.services.recompile import (  # noqa: E402
    finalize_recompiled_packet as _runtime_finalize_recompiled_packet,
)
from tmcp_runtime.services.review import (  # noqa: E402
    build_review_plan as _runtime_build_review_plan,
)
from tmcp_runtime.services.diagnostics import (  # noqa: E402
    build_doctor_report as _runtime_build_doctor_report,
    build_status_report as _runtime_build_status_report,
)
from tmcp_runtime.services.artifact_plans import (  # noqa: E402
    ArtifactPlan,
    build_evaluation_artifact_plan as _runtime_build_evaluation_artifact_plan,
    build_global_promotion_artifact_plan as _runtime_build_global_promotion_artifact_plan,
    build_promotion_artifact_plan as _runtime_build_promotion_artifact_plan,
    build_review_artifact_plan as _runtime_build_review_artifact_plan,
    build_workflow_recommendation_artifact_plan as _runtime_build_workflow_recommendation_artifact_plan,
)

AIOS_ROOT = (
    Path(os.environ["AIOS_ROOT"]).expanduser() if os.environ.get("AIOS_ROOT") else None
)
TMCP_HOME = Path(os.environ.get("TMCP_HOME", "~/.tmcp")).expanduser()
UTC = timezone.utc

RUNTIME_NEXT_SCHEMA = "tmcp-runtime-next-v0.1"
PROMOTED_HARVEST_GRAPH_SCHEMA = "tmcp-promoted-harvest-graph-v0.1"
def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _aios_available() -> bool:
    if AIOS_ROOT is None:
        return False
    return (AIOS_ROOT / "bin" / "aios.py").exists()


def _should_use_aios(adapter: str) -> bool:
    return adapter == "aios"


def _aios_command_redactions(args: list[str]) -> dict[str, int]:
    redactions: dict[str, int] = {}
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == "--evidence-json" and index + 1 < len(args):
            evidence_json = args[index + 1]
            try:
                evidence_value = json.loads(evidence_json)
            except json.JSONDecodeError:
                evidence_value = evidence_json
            _, evidence_redactions = redact_json_value(evidence_value, enabled=True)
            merge_redactions(redactions, evidence_redactions)
            index += 2
            continue
        _, argument_redactions = redact_json_value(argument, enabled=True)
        merge_redactions(redactions, argument_redactions)
        index += 1
    return redactions


def _run_aios(args: list[str]) -> dict[str, Any]:
    if not _aios_available():
        return {
            "ok": False,
            "adapter": "aios",
            "error": "AIOS adapter requested but AIOS_ROOT/bin/aios.py was not found.",
            "aios_root": redact_path(AIOS_ROOT) if AIOS_ROOT is not None else None,
            "remediation": (
                "Continue with --adapter standalone, or set AIOS_ROOT to an AIOS "
                "checkout if you explicitly want the optional adapter."
            ),
        }
    command_redactions = _aios_command_redactions(args)
    if command_redactions:
        return {
            "ok": False,
            "adapter": "aios",
            "error": (
                "AIOS adapter cannot receive sensitive request values through "
                "command arguments."
            ),
            "remediation": (
                "Use --adapter standalone, or configure AIOS with a protected "
                "request-input protocol."
            ),
            "redaction_summary": command_redactions,
        }
    command = (
        ["uv", "run", "python", "bin/aios.py", *args]
        if shutil.which("uv")
        else [sys.executable, "bin/aios.py", *args]
    )
    try:
        completed = subprocess.run(
            command,
            cwd=cast(Path, AIOS_ROOT),
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "adapter": "aios",
            "error": "AIOS adapter command did not complete.",
            "error_type": type(exc).__name__,
        }
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


def _build_runtime_state(arguments: dict[str, Any]) -> dict[str, Any]:
    source_nodes: list[dict[str, Any]] = []
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
    runtime_arguments = dict(arguments)
    cache_warnings: list[str] = []
    cache_policy = _runtime_normalize_cache_policy(runtime_arguments.get("cache_policy"))
    runtime_arguments["cache_policy"] = cache_policy
    if cache_policy == "global":
        cache_warnings.extend(
            _global_cache_snapshot(cache_policy, receipt_limit=10).warnings
        )
    return _runtime_derive_runtime_state(
        runtime_arguments,
        source_nodes=source_nodes,
        cache_warnings=cache_warnings,
    )


def _recompile_packet(arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    previous_packet = parse_previous_packet(arguments)
    if not isinstance(previous_packet, dict):
        raise ValueError(
            "tmcp_runtime_next output_mode=full requires previous_packet as an object."
        )
    target_phase = str(state.get("suggested_phase") or state.get("phase") or "start")
    session_project_path = (
        state.get("project_path")
        if arguments.get("session_id") is not None
        else previous_packet.get("project_path") or state.get("project_path")
    )
    source_path = arguments.get("source_path") or arguments.get("project_path")
    if not source_path and arguments.get("session_id") is None:
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
    composed_packet = _compose_packet(compose_arguments)
    if arguments.get("session_id") is not None:
        previous_packet_id = str(previous_packet.get("packet_id") or "")
    else:
        previous_packet_id = str(
            arguments.get("previous_packet_id")
            or previous_packet.get("packet_id")
            or ""
        )
    return _runtime_finalize_recompiled_packet(
        arguments,
        state,
        previous_packet=previous_packet,
        composed_packet=composed_packet,
        previous_packet_id=previous_packet_id or None,
    )


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


def _persist_artifact_plan(
    output_dir: Path,
    plan: ArtifactPlan,
    *,
    fresh_bundle: bool,
) -> dict[str, str]:
    paths = _persist_artifacts(
        output_dir,
        json_artifacts=plan.json_artifacts,
        text_artifacts=plan.text_artifacts,
        fresh_bundle=fresh_bundle,
    )
    return {alias: paths[name] for alias, name in plan.path_aliases.items()}


def _persist_harvest_artifacts(
    output_dir: Path,
    result: dict[str, Any],
) -> dict[str, str]:
    json_artifacts: dict[str, Any] = {"tmcp-harvest-result.json": result}
    if isinstance(result.get("packet_seed"), dict):
        json_artifacts["tmcp-packet-seed.json"] = result["packet_seed"]
    paths = _persist_artifacts(
        output_dir,
        json_artifacts=json_artifacts,
        text_artifacts={},
        fresh_bundle=True,
    )
    aliases = {"harvest_result": paths["tmcp-harvest-result.json"]}
    if "tmcp-packet-seed.json" in paths:
        aliases["packet_seed"] = paths["tmcp-packet-seed.json"]
    return aliases


def _persist_evaluation_artifacts(
    arguments: dict[str, Any],
    plan: dict[str, Any] | None,
    report: dict[str, Any] | None,
) -> dict[str, str]:
    output_dir = (
        Path(str(arguments["output_dir"])).expanduser()
        if arguments.get("output_dir")
        else _require_default_artifact_root(arguments)
        / ".tmcp"
        / f"skill-eval-{uuid.uuid4().hex[:8]}"
    )
    artifact_plan = _runtime_build_evaluation_artifact_plan(
        plan=plan,
        report=report,
        guidebook_markdown=lambda entries: _runtime_render_guidebook_markdown(
            entries,
            evidence_levels=EVIDENCE_LEVELS,
        ),
        pattern_catalog=lambda entries: _runtime_build_pattern_catalog(
            entries,
            patterns=(*EFFECTIVE_PATTERNS, *V01_ANTI_PATTERNS),
            created_at=_now_iso(),
        ),
    )
    return _persist_artifact_plan(
        output_dir,
        artifact_plan,
        fresh_bundle=report is None,
    )


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
        artifact_plan = _runtime_build_review_artifact_plan(
            expertise_packet=dict(safe_result["expertise_packet"]),
            rubric=dict(safe_result["rubric"]),
            audit_report=dict(safe_result["audit_report"]),
            remediation_plan=dict(safe_result["remediation_plan"]),
            implementation_handoff=dict(safe_result["implementation_handoff"]),
        )
        safe_result["artifact_paths"] = _persist_artifact_plan(
            output_dir,
            artifact_plan,
            fresh_bundle=not bool(arguments.get("output_dir")),
        )
    return safe_result


def _source_project_path(arguments: dict[str, Any]) -> str:
    return _runtime_source_project_path(arguments)


def _require_default_artifact_root(arguments: dict[str, Any]) -> Path:
    return _runtime_require_default_artifact_root(arguments)


def _runtime_harvest_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return _runtime_read_only_harvest_arguments(arguments)


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
    result = _runtime_harvest_skills(
        {**arguments, "write_artifacts": False},
        source_advisories=_harvest_source_advisories,
    )
    if bool(arguments.get("write_artifacts", False)):
        output_dir = (
            Path(str(arguments["output_dir"])).expanduser()
            if arguments.get("output_dir")
            else _runtime_require_default_artifact_root(arguments)
            / ".tmcp"
            / f"harvest-{uuid.uuid4().hex[:8]}"
        )
        result["artifact_paths"] = _persist_harvest_artifacts(output_dir, result)
    return result


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


def _global_cache_snapshot(
    cache_policy: object,
    *,
    receipt_limit: object = 25,
) -> GlobalCacheSnapshot:
    return _runtime_read_global_cache_snapshot(
        promoted_root=_global_promoted_root(),
        receipts_root=_global_receipts_root(),
        cache_policy=cache_policy,
        graph_schema=PROMOTED_HARVEST_GRAPH_SCHEMA,
        receipt_schema=RUN_RECEIPT_SCHEMA,
        known_workflow_ids=workflow_catalog_by_id(),
        receipt_limit=receipt_limit,
    )


def _normalized_global_graph(result: dict[str, Any]) -> dict[str, Any]:
    return _runtime_normalize_promoted_graph(
        result,
        graph_schema=PROMOTED_HARVEST_GRAPH_SCHEMA,
        created_at=_now_iso(),
    )


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
    artifact_plan = _runtime_build_global_promotion_artifact_plan(
        promotion_summary=safe_summary,
        promotion_graph=graph,
        adaptive_workflow_pack=(
            _redacted_mapping(adaptive_pack)
            if isinstance(adaptive_pack, dict)
            else None
        ),
    )
    return _persist_artifact_plan(
        output_dir,
        artifact_plan,
        fresh_bundle=False,
    )


def _compose_harvest_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return _runtime_read_only_harvest_arguments(arguments)


def _compose_packet_from_source_nodes(
    arguments: dict[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    compose_arguments = dict(arguments)
    cache_policy = _runtime_normalize_cache_policy(compose_arguments.get("cache_policy"))
    compose_arguments["cache_policy"] = cache_policy
    snapshot = _global_cache_snapshot(cache_policy)
    return _runtime_compose_packet_from_source_nodes(
        compose_arguments,
        source_nodes=source_nodes,
        global_graphs=list(snapshot.promoted_graphs),
        receipts=list(snapshot.receipts),
        cache_warnings=list(snapshot.warnings),
        cache_home=redact_path(_tmcp_home()),
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
        return _redact_result(recompiled)
    return _redact_result({
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
    })


def _record_receipt(arguments: dict[str, Any]) -> dict[str, Any]:
    created_at = _now_iso()
    receipt = _runtime_build_run_receipt(arguments, created_at=created_at)
    redacted_receipt, receipt_redactions = redact_json_value(receipt, enabled=True)
    safe_receipt = (
        redacted_receipt if isinstance(redacted_receipt, dict) else {}
    )
    packet_id = str(receipt["packet_id"])
    storage_key = _opaque_storage_key(
        packet_id,
        str(safe_receipt["packet_id"]),
    )
    month = created_at[:7]
    digest = hashlib.sha256(json.dumps(safe_receipt, sort_keys=True).encode()).hexdigest()[
        :10
    ]
    path = (
        _global_receipts_root()
        / month
        / f"{storage_key}-{digest}-{uuid.uuid4().hex}.json"
    )
    receipt_path = AtomicArtifactStore.explicit(path.parent).write_json(
        path.name,
        safe_receipt,
    )
    return _redact_result(
        _runtime_build_recorded_receipt_result(
            safe_receipt,
            redacted_receipt_path=redact_path(receipt_path),
            redaction_summary=receipt_redactions,
        )
    )


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
        artifact_plan = _runtime_build_workflow_recommendation_artifact_plan(
            safe_result
        )
        safe_result["artifact_paths"] = _persist_artifact_plan(
            output_dir,
            artifact_plan,
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
        artifact_plan = _runtime_build_promotion_artifact_plan(safe_result)
        safe_result["artifact_paths"] = _persist_artifact_plan(
            output_dir,
            artifact_plan,
            fresh_bundle=False,
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
        return _runtime_build_doctor_report(
            client,
            redact_path(plugin_root),
            plugin_root_exists=plugin_root.exists(),
            node_launcher_exists=(
                plugin_root / "scripts" / "tmcp_launcher.mjs"
            ).exists(),
            node_available=bool(shutil.which("node")),
            python_server_exists=(
                plugin_root / "scripts" / "tmcp_mcp_server.py"
            ).exists(),
            python_available=bool(
                shutil.which("python3")
                or shutil.which("python")
                or shutil.which("py")
            ),
            artifact_persistence=artifact_persistence_available(),
            aios_available=_aios_available(),
            aios_root_display=(
                redact_path(AIOS_ROOT) if AIOS_ROOT is not None else None
            ),
        )
    if name == "tmcp_status":
        artifact_persistence = artifact_persistence_available()
        return _runtime_build_status_report(
            redact_path(PLUGIN_ROOT),
            artifact_persistence,
            _aios_available(),
            aios_root_display=(
                redact_path(AIOS_ROOT) if AIOS_ROOT is not None else None
            ),
        )
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
                return _redact_result(payload)
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
        return _redact_result(result)
    if name == "tmcp_harvest_skills":
        return _harvest_skills(arguments)
    if name == "tmcp_evaluate_skills":
        return evaluate_skills(
            arguments,
            compose_evaluation_row=_compose_evaluation_row,
            artifact_writer=lambda plan, report: _persist_evaluation_artifacts(
                arguments,
                plan,
                report,
            ),
        )
    if name == "tmcp_recommend_workflows":
        return _recommend_workflows(arguments)
    if name == "tmcp_compose_packet":
        return _redact_result(_compose_packet(arguments))
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
