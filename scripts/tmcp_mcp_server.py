#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tmcp_runtime.adapters.cli import run_cli as _runtime_run_cli  # noqa: E402
from tmcp_runtime.adapters.aios import (  # noqa: E402
    is_available as _runtime_aios_available,
    run as _runtime_run_aios,
    should_use as _runtime_should_use_aios,
)
from tmcp_runtime.adapters.dispatch import (  # noqa: E402
    ToolDispatcher,
    ToolRequest,
)
from tmcp_runtime.adapters.framing import write_message as _runtime_write_message  # noqa: E402
from tmcp_runtime.adapters.mcp import (  # noqa: E402
    handle_message as _runtime_handle_message,
    run_stdio as _runtime_run_mcp_stdio,
)
from tmcp_runtime.safety.redaction import merge_redactions  # noqa: E402
from tmcp_runtime.domain.admission import decide_admission  # noqa: E402
from tmcp_runtime.domain.composition import (  # noqa: E402
    normalize_cache_policy as _runtime_normalize_cache_policy,
)
from tmcp_runtime.domain.receipts import (  # noqa: E402
    RUN_RECEIPT_SCHEMA,
    build_recorded_receipt_result as _runtime_build_recorded_receipt_result,
    build_run_receipt as _runtime_build_run_receipt,
)
from tmcp_runtime.domain.harvest_nodes import (  # noqa: E402
    routing_metadata_for as _domain_routing_metadata_for,
    source_node_from_text as _domain_source_node_from_text,
)
from tmcp_runtime.domain.routes import derive_task_identity  # noqa: E402
from tmcp_runtime.domain.workflow_catalog import (  # noqa: E402
    workflow_catalog_by_id,
)
from tmcp_runtime.api.evaluation import evaluate_skills  # noqa: E402
from tmcp_runtime.api.registry import (  # noqa: E402
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
from tmcp_runtime.services.global_promotion import (  # noqa: E402
    GlobalPromotionArtifactService,
    GlobalPromotionContext,
)
from tmcp_runtime.services.explain import (  # noqa: E402
    ExplainService,
    ExplainServiceContext,
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
from tmcp_runtime.services.runtime import (  # noqa: E402
    RuntimeService,
    RuntimeServiceContext,
)
from tmcp_runtime.services.sessions import RuntimeSessionService  # noqa: E402
from tmcp_runtime.services.receipts import (  # noqa: E402
    ReceiptService,
    ReceiptServiceContext,
)
from tmcp_runtime.services.review import (  # noqa: E402
    build_review_plan as _runtime_build_review_plan,
    parse_review_evidence as _runtime_parse_review_evidence,
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
from tmcp_runtime.services.artifact_persistence import (  # noqa: E402
    ArtifactPersistenceContext,
    ArtifactPersistenceService,
)

AIOS_ADAPTER_COMPATIBILITY_ENABLED = (
    os.environ.get("TMCP_ENABLE_DEPRECATED_AIOS_ADAPTER") == "1"
)
AIOS_ROOT = (
    Path(os.environ["AIOS_ROOT"]).expanduser()
    if AIOS_ADAPTER_COMPATIBILITY_ENABLED and os.environ.get("AIOS_ROOT")
    else None
)
TMCP_HOME = Path(os.environ.get("TMCP_HOME", "~/.tmcp")).expanduser()
UTC = timezone.utc

PROMOTED_HARVEST_GRAPH_SCHEMA = "tmcp-promoted-harvest-graph-v0.1"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _aios_available() -> bool:
    return _runtime_aios_available(AIOS_ROOT)


def _should_use_aios(adapter: str) -> bool:
    return _runtime_should_use_aios(adapter)


def _run_aios(args: list[str]) -> dict[str, Any]:
    return _runtime_run_aios(
        args,
        root=AIOS_ROOT,
        available=_aios_available(),
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


def _project_public_packet(result: dict[str, Any]) -> dict[str, Any]:
    """Keep packet substance metadata public without returning source excerpts."""
    public_result = dict(result)
    for packet_key in ("packet", "expertise_packet"):
        packet = public_result.get(packet_key)
        if not isinstance(packet, dict):
            continue
        source_nodes = packet.get("source_skill_nodes")
        if not isinstance(source_nodes, list):
            continue
        public_packet = dict(packet)
        public_packet["source_skill_nodes"] = [
            {
                key: value
                for key, value in node.items()
                if key not in {"excerpt", "signal_excerpt"}
            }
            if isinstance(node, dict)
            else node
            for node in source_nodes
        ]
        public_result[packet_key] = public_packet
    return public_result


def _write_artifact_bundle(
    output_dir: Path,
    json_artifacts: Mapping[str, Any],
    text_artifacts: Mapping[str, str],
) -> Mapping[str, str]:
    return AtomicArtifactStore.write_bundle(
        output_dir,
        json_artifacts=json_artifacts,
        text_artifacts=text_artifacts,
    )


def _open_artifact_store(output_dir: Path) -> AtomicArtifactStore:
    return AtomicArtifactStore.explicit(output_dir)


def _redact_artifact_text(content: str) -> str:
    return str(redact_json_value(content, enabled=True)[0])


def _artifact_persistence_service() -> ArtifactPersistenceService:
    return ArtifactPersistenceService(
        ArtifactPersistenceContext(
            redact_json=_redacted_mapping,
            redact_text=_redact_artifact_text,
            present_path=redact_path,
            write_bundle=_write_artifact_bundle,
            open_store=_open_artifact_store,
        )
    )


def _persist_artifacts(
    output_dir: Path,
    *,
    json_artifacts: dict[str, Any],
    text_artifacts: dict[str, str],
    fresh_bundle: bool,
) -> dict[str, str]:
    return _artifact_persistence_service().persist(
        output_dir,
        json_artifacts=json_artifacts,
        text_artifacts=text_artifacts,
        fresh_bundle=fresh_bundle,
    )


def _persist_artifact_plan(
    output_dir: Path,
    plan: ArtifactPlan,
    *,
    fresh_bundle: bool,
) -> dict[str, str]:
    return _artifact_persistence_service().persist_plan(
        output_dir,
        plan,
        fresh_bundle=fresh_bundle,
    )


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
    evidence_items = _runtime_parse_review_evidence(
        arguments.get("evidence_json") or "[]"
    )
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
    return _project_public_packet(safe_result)


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


def _write_global_promotion(
    result: dict[str, Any], promotion_name: str, storage_key: str
) -> dict[str, str]:
    output_dir = _global_promoted_root() / storage_key
    artifact_plan = _global_promotion_service().build(result, promotion_name)
    return _persist_artifact_plan(
        output_dir,
        artifact_plan,
        fresh_bundle=False,
    )


def _global_promotion_service() -> GlobalPromotionArtifactService:
    return GlobalPromotionArtifactService(
        GlobalPromotionContext(
            normalize_graph=lambda result, created_at: (
                _runtime_normalize_promoted_graph(
                    dict(result),
                    graph_schema=PROMOTED_HARVEST_GRAPH_SCHEMA,
                    created_at=created_at,
                )
            ),
            redact_mapping=_redacted_mapping,
            build_artifact_plan=lambda summary, graph, adaptive_pack: (
                _runtime_build_global_promotion_artifact_plan(
                    promotion_summary=summary,
                    promotion_graph=graph,
                    adaptive_workflow_pack=adaptive_pack,
                )
            ),
            now_iso=_now_iso,
        )
    )


def _compose_harvest_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return _runtime_read_only_harvest_arguments(arguments)


def _compose_packet_from_source_nodes(
    arguments: dict[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    compose_arguments = dict(arguments)
    cache_policy = _runtime_normalize_cache_policy(
        compose_arguments.get("cache_policy")
    )
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
    source_nodes: list[dict[str, Any]] = []
    admission_mode = str(arguments.get("admission_mode") or "forced")
    context = arguments.get("runtime_context")
    if not isinstance(context, dict):
        context = {}
    identity_context = dict(context)
    identity_context["latest_user_message"] = str(
        arguments.get("latest_user_message") or ""
    )
    pre_admission = decide_admission(
        objective,
        derive_task_identity(objective, identity_context),
        mode=admission_mode,
        context=context,
    )
    if pre_admission["action"] != "bypass":
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


def _runtime_source_nodes(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    harvest = _harvest_skills(_runtime_harvest_arguments(arguments))
    return [
        item
        for item in _json_list(harvest.get("source_nodes"))
        if isinstance(item, dict)
    ]


def _runtime_cache_warnings(cache_policy: str) -> list[str]:
    return list(_global_cache_snapshot(cache_policy, receipt_limit=10).warnings)


def _runtime_service() -> RuntimeService:
    return RuntimeService(
        RuntimeServiceContext(
            source_exists=lambda path: Path(path).expanduser().exists(),
            load_source_nodes=_runtime_source_nodes,
            load_cache_warnings=_runtime_cache_warnings,
            compose_packet=_compose_packet,
        )
    )


def _build_runtime_state(arguments: dict[str, Any]) -> dict[str, Any]:
    return _runtime_service().build_state(arguments)


def _recompile_packet(
    arguments: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    return _runtime_service().recompile(arguments, state)


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


def _open_packet_session(
    project_path: object,
    session_id: object,
) -> PacketSessionStore:
    if isinstance(project_path, bool) or not isinstance(project_path, (str, Path)):
        raise ValueError("session_id requires an explicit project_path.")
    path = Path(project_path).expanduser()
    if not str(project_path).strip() or not path.is_absolute():
        raise ValueError("session_id requires an absolute project_path.")
    return PacketSessionStore.open(path, session_id)


def _packet_session_store(arguments: dict[str, Any]) -> PacketSessionStore | None:
    session_id = arguments.get("session_id")
    if session_id is None:
        return None
    project_path = arguments.get("project_path")
    if not isinstance(project_path, (str, Path)) or isinstance(project_path, bool):
        raise ValueError("session_id requires an explicit project_path.")
    return _open_packet_session(project_path, session_id)


def _runtime_next(arguments: dict[str, Any]) -> dict[str, Any]:
    service = RuntimeSessionService(
        open_store=_open_packet_session,
        build_state=_build_runtime_state,
        recompile_packet=_recompile_packet,
        now_iso=_now_iso,
    )
    return _redact_result(service.run(arguments))


def _redact_receipt(
    receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    redacted_receipt, redactions = redact_json_value(receipt, enabled=True)
    return (
        redacted_receipt if isinstance(redacted_receipt, dict) else {},
        redactions,
    )


def _receipt_path(
    created_at: str,
    storage_key: str,
    safe_receipt: Mapping[str, Any],
) -> Path:
    month = created_at[:7]
    digest = hashlib.sha256(
        json.dumps(safe_receipt, sort_keys=True).encode()
    ).hexdigest()[:10]
    return (
        _global_receipts_root()
        / month
        / f"{storage_key}-{digest}-{uuid.uuid4().hex}.json"
    )


def _write_receipt(
    path: Path,
    safe_receipt: Mapping[str, Any],
) -> Path:
    return AtomicArtifactStore.explicit(path.parent).write_json(
        path.name,
        safe_receipt,
    )


def _receipt_service() -> ReceiptService:
    return ReceiptService(
        ReceiptServiceContext(
            build_receipt=lambda arguments, created_at: _runtime_build_run_receipt(
                arguments,
                created_at=created_at,
            ),
            redact_receipt=_redact_receipt,
            storage_key=_opaque_storage_key,
            build_path=_receipt_path,
            write_receipt=_write_receipt,
            present_path=redact_path,
            build_result=lambda safe_receipt, path, redactions: (
                _runtime_build_recorded_receipt_result(
                    safe_receipt,
                    redacted_receipt_path=path,
                    redaction_summary=redactions,
                )
            ),
            redact_result=_redact_result,
            now_iso=_now_iso,
        )
    )


def _record_receipt(arguments: dict[str, Any]) -> dict[str, Any]:
    return _receipt_service().record(arguments)


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


def _tool_doctor(arguments: dict[str, Any]) -> dict[str, Any]:
    client = str(arguments.get("client") or "auto")
    plugin_root = PLUGIN_ROOT
    return _runtime_build_doctor_report(
        client,
        redact_path(plugin_root),
        plugin_root_exists=plugin_root.exists(),
        node_launcher_exists=(plugin_root / "scripts" / "tmcp_launcher.mjs").exists(),
        node_available=bool(shutil.which("node")),
        python_server_exists=(plugin_root / "scripts" / "tmcp_mcp_server.py").exists(),
        python_available=bool(
            shutil.which("python3") or shutil.which("python") or shutil.which("py")
        ),
        artifact_persistence=artifact_persistence_available(),
        aios_available=_aios_available(),
        aios_root_display=(redact_path(AIOS_ROOT) if AIOS_ROOT is not None else None),
    )


def _tool_status(arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    return _runtime_build_status_report(
        redact_path(PLUGIN_ROOT),
        artifact_persistence_available(),
        _aios_available(),
        aios_root_display=(redact_path(AIOS_ROOT) if AIOS_ROOT is not None else None),
    )


def _tool_explain(arguments: dict[str, Any]) -> dict[str, Any]:
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
            return _project_public_packet(_redact_result(payload))
    result = ExplainService(
        ExplainServiceContext(compose_packet=_compose_packet)
    ).standalone(arguments)
    return _project_public_packet(_redact_result(result))


def _tool_evaluate_skills(arguments: dict[str, Any]) -> dict[str, Any]:
    return evaluate_skills(
        arguments,
        compose_evaluation_row=_compose_evaluation_row,
        artifact_writer=lambda plan, report: _persist_evaluation_artifacts(
            arguments,
            plan,
            report,
        ),
    )


def _tool_compose_packet(arguments: dict[str, Any]) -> dict[str, Any]:
    return _redact_result(_compose_packet(arguments))


def _tool_review_plan(arguments: dict[str, Any]) -> dict[str, Any]:
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
            args.extend(["--selected-slice-id", str(arguments["selected_slice_id"])])
        payload = _run_aios(args)
        safe_payload = _redact_result(payload)
        safe_payload.pop("output_dir", None)
        safe_payload.pop("global_artifact_paths", None)
        safe_payload["artifact_paths"] = {}
        return safe_payload
    return _standalone_review_plan(arguments)


_TOOL_HANDLERS = {
    "tmcp_doctor": _tool_doctor,
    "tmcp_status": _tool_status,
    "tmcp_explain": _tool_explain,
    "tmcp_harvest_skills": _harvest_skills,
    "tmcp_evaluate_skills": _tool_evaluate_skills,
    "tmcp_recommend_workflows": _recommend_workflows,
    "tmcp_compose_packet": _tool_compose_packet,
    "tmcp_runtime_next": _runtime_next,
    "tmcp_record_receipt": _record_receipt,
    "tmcp_promote_harvest": _promote_harvest,
    "expert_rubric_review_plan": _tool_review_plan,
}
_TOOL_DISPATCHER = ToolDispatcher(_TOOL_HANDLERS)


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return _TOOL_DISPATCHER.dispatch(
        ToolRequest.from_parts(name, arguments)
    ).to_payload()


def _handle(request: dict[str, Any]) -> None:
    response = _runtime_handle_message(
        request,
        dispatcher=_TOOL_DISPATCHER,
        server_info=mcp_server_info,
        tools=mcp_tools,
    )
    if response is not None:
        _runtime_write_message(sys.stdout.buffer, response)


def _run_mcp_stdio() -> None:
    _runtime_run_mcp_stdio(
        sys.stdin.buffer,
        sys.stdout.buffer,
        dispatcher=_TOOL_DISPATCHER,
        server_info=mcp_server_info,
        tools=mcp_tools,
    )


def _run_cli(argv: list[str]) -> int:
    return _runtime_run_cli(argv, dispatcher=_TOOL_DISPATCHER)


def main() -> None:
    if len(sys.argv) > 1:
        raise SystemExit(_run_cli(sys.argv[1:]))
    _run_mcp_stdio()


if __name__ == "__main__":
    main()
