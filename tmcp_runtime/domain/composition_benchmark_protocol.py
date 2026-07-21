"""Prepare-only, content-bound host protocol for composition benchmarks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tmcp_runtime.api.registry import VERSION
from tmcp_runtime.domain.composition_benchmark_manifests import routing_input_digest
from tmcp_runtime.domain.composition_benchmark_sources import (
    fixture_source_node_id,
    validate_fixture_skill_sources,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import (
    content_digest_for,
    source_node_from_text,
)
from tmcp_runtime.services.compose import prepare_composition_from_source_nodes


BENCHMARK_RUN_PLAN_SCHEMA = "tmcp-composition-benchmark-run-plan-v0.1"
BENCHMARK_PROTOCOL_SCHEMA = "tmcp-composition-benchmark-protocol-v0.1"
TASK_CONTEXT_SCHEMA = "tmcp-composition-task-context-v0.1"
TASK_CONTEXT_MODE = "fixture_supplied_evidence"
_LOGICAL_WORKSPACE_ROOT = Path("/tmcp-benchmark")


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _nonempty(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required.")
    return result


def validate_fixture_observable_contracts(
    fixture_id: str,
    fixture: Mapping[str, Any],
) -> None:
    """Reject benchmark fixtures whose expected skills lack observable outputs."""

    sources = validate_fixture_skill_sources(fixture_id, fixture)
    raw_expected = fixture.get("expected_skill_ids")
    if isinstance(raw_expected, (str, bytes)) or not isinstance(raw_expected, Sequence):
        raise ValueError(f"{fixture_id}.expected_skill_ids must be a sequence.")
    expected_skill_ids = [str(item).strip() for item in raw_expected]
    missing: list[str] = []
    for skill_id in expected_skill_ids:
        source = sources.get(skill_id)
        content = str(source.get("content") if source is not None else "")
        lines = content.splitlines()
        marker = next(
            (
                index
                for index, line in enumerate(lines)
                if line.strip().casefold() in {"## output contract", "output contract:"}
            ),
            None,
        )
        contract_lines = (
            [line.strip() for line in lines[marker + 1 :] if line.strip()]
            if marker is not None
            else []
        )
        if marker is None or not contract_lines:
            missing.append(skill_id or "<empty>")
    if missing:
        raise ValueError(
            f"{fixture_id} expected skills require nonempty ## Output contract "
            f"sections: {', '.join(sorted(missing))}."
        )


def validate_fixture_task_context(
    fixture_id: str,
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the bounded task input kept separate from active skill sources."""

    raw_context = fixture.get("task_context")
    if not isinstance(raw_context, Mapping):
        raise ValueError(f"{fixture_id}.task_context must be an object.")
    if raw_context.get("schema") != TASK_CONTEXT_SCHEMA:
        raise ValueError(
            f"{fixture_id}.task_context.schema must be {TASK_CONTEXT_SCHEMA}."
        )
    if raw_context.get("mode") != TASK_CONTEXT_MODE:
        raise ValueError(
            f"{fixture_id}.task_context.mode must be {TASK_CONTEXT_MODE}."
        )
    objective_context = str(raw_context.get("objective_context") or "").strip()
    if not objective_context or len(objective_context) > 2000:
        raise ValueError(
            f"{fixture_id}.task_context.objective_context must be 1-2000 characters."
        )
    constraints = raw_context.get("constraints")
    if isinstance(constraints, (str, bytes)) or not isinstance(constraints, Sequence):
        raise ValueError(f"{fixture_id}.task_context.constraints must be a sequence.")
    normalized_constraints = [str(item or "").strip() for item in constraints]
    if not 1 <= len(normalized_constraints) <= 8 or any(
        not item or len(item) > 500 for item in normalized_constraints
    ):
        raise ValueError(
            f"{fixture_id}.task_context.constraints must contain 1-8 bounded strings."
        )
    if len(set(normalized_constraints)) != len(normalized_constraints):
        raise ValueError(f"{fixture_id}.task_context.constraints must be unique.")
    evidence = raw_context.get("evidence")
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
        raise ValueError(f"{fixture_id}.task_context.evidence must be a sequence.")
    if not 1 <= len(evidence) <= 8:
        raise ValueError(f"{fixture_id}.task_context.evidence must contain 1-8 items.")
    normalized_evidence: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"{fixture_id}.task_context.evidence[{index}] must be an object."
            )
        evidence_id = str(item.get("evidence_id") or "").strip()
        kind = str(item.get("kind") or "").strip()
        media_type = str(item.get("media_type") or "").strip()
        provenance = str(item.get("provenance") or "").strip()
        content = str(item.get("content") or "").strip()
        if not evidence_id or not kind or not media_type or not content:
            raise ValueError(
                f"{fixture_id}.task_context.evidence[{index}] has an empty field."
            )
        if evidence_id in seen_ids:
            raise ValueError(f"{fixture_id}.task_context evidence ids must be unique.")
        if len(kind) > 128 or len(media_type) > 128 or len(content) > 8000:
            raise ValueError(
                f"{fixture_id}.task_context.evidence[{index}] exceeds a bounded field."
            )
        if provenance != "fixture_supplied":
            raise ValueError(
                f"{fixture_id}.task_context.evidence[{index}].provenance must be fixture_supplied."
            )
        seen_ids.add(evidence_id)
        normalized_evidence.append(
            {
                "evidence_id": evidence_id,
                "kind": kind,
                "media_type": media_type,
                "provenance": provenance,
                "content": content,
            }
        )
    normalized = {
        "schema": TASK_CONTEXT_SCHEMA,
        "mode": TASK_CONTEXT_MODE,
        "objective_context": objective_context,
        "constraints": normalized_constraints,
        "evidence": normalized_evidence,
    }
    serialized = json.dumps(normalized, sort_keys=True).casefold()
    for forbidden in (
        "expected_skill_ids",
        "expected_order",
        "expected_relationships",
        "quality_rubric",
    ):
        if forbidden in serialized:
            raise ValueError(
                f"{fixture_id}.task_context must not contain benchmark oracle {forbidden}."
            )
    return normalized


def task_context_digest(fixture: Mapping[str, Any]) -> str:
    fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
    return stable_digest(validate_fixture_task_context(fixture_id, fixture))


def _json_text(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _relative_path(value: str, *, field: str) -> str:
    if not value or "\\" in value:
        raise ValueError(f"{field} must use a nonempty forward-slash path.")
    candidate = Path(value)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in value.split("/")
    ):
        raise ValueError(f"{field} must be a safe relative path.")
    return value


def _fixture_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    fixtures = _mapping_list(payload.get("fixtures"), field="behavioral.fixtures")
    if len(fixtures) < 5:
        raise ValueError("behavioral.fixtures must contain at least five fixtures.")
    by_id: set[str] = set()
    by_domain: set[str] = set()
    for fixture in fixtures:
        fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
        domain = _nonempty(fixture.get("domain"), field=f"{fixture_id}.domain")
        _nonempty(fixture.get("objective"), field=f"{fixture_id}.objective")
        if fixture_id in by_id:
            raise ValueError(
                f"behavioral.fixtures has duplicate fixture_id {fixture_id}."
            )
        if domain in by_domain:
            raise ValueError(f"behavioral.fixtures has duplicate domain {domain}.")
        by_id.add(fixture_id)
        by_domain.add(domain)
        validate_fixture_skill_sources(fixture_id, fixture)
        validate_fixture_observable_contracts(fixture_id, fixture)
        validate_fixture_task_context(fixture_id, fixture)
    return fixtures


def _routing_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cases = _mapping_list(payload.get("cases"), field="routing.cases")
    if len(cases) < 20:
        raise ValueError("routing.cases must contain at least twenty cases.")
    case_ids: set[str] = set()
    for case in cases:
        case_id = _nonempty(case.get("case_id"), field="routing.case_id")
        _nonempty(case.get("domain"), field=f"{case_id}.domain")
        _nonempty(case.get("objective"), field=f"{case_id}.objective")
        if case_id in case_ids:
            raise ValueError(f"routing.cases has duplicate case_id {case_id}.")
        case_ids.add(case_id)
    return cases


def fixture_workspace_relative_path(fixture: Mapping[str, Any]) -> str:
    fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
    return f"fixtures/{fixture_id}"


def fixture_source_nodes(
    fixture: Mapping[str, Any],
    *,
    logical_workspace_root: Path = _LOGICAL_WORKSPACE_ROOT,
) -> list[dict[str, Any]]:
    """Build explicit benchmark-only source nodes without reading the filesystem."""

    fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
    fixture_root = logical_workspace_root / fixture_workspace_relative_path(fixture)
    sources = validate_fixture_skill_sources(fixture_id, fixture)
    nodes: list[dict[str, Any]] = []
    for skill_id, source in sorted(sources.items()):
        relative_path = _relative_path(
            _nonempty(
                source.get("relative_path"), field=f"{fixture_id}.{skill_id}.path"
            ),
            field=f"{fixture_id}.{skill_id}.relative_path",
        )
        content = _nonempty(
            source.get("content"), field=f"{fixture_id}.{skill_id}.content"
        )
        node = source_node_from_text(
            root_path=str(fixture_root),
            source_path=str(fixture_root / relative_path),
            relative_path=relative_path,
            text=content,
            max_excerpt_chars=max(48_000, len(content)),
            redactions={},
            source_type="skill_definition",
            explicitly_scoped=True,
        )
        node["id"] = fixture_source_node_id(fixture_id, skill_id, content)
        node["skill_id"] = skill_id
        node["source_role"] = "active_skill"
        node["activation_eligible"] = True
        nodes.append(node)
    return nodes


def prepare_fixture_preflight(
    *,
    fixture: Mapping[str, Any],
    objective: str,
) -> dict[str, Any]:
    fixture_root = _LOGICAL_WORKSPACE_ROOT / fixture_workspace_relative_path(fixture)
    context_digest = task_context_digest(fixture)
    return prepare_composition_from_source_nodes(
        {
            "objective": objective,
            "project_path": str(fixture_root),
            "phase": "start",
            "cache_policy": "none",
            "candidate_limit": 24,
            "max_excerpt_chars": 48_000,
            "max_total_chars": 48_000,
            "max_total_tokens": 12_000,
            "explicitly_scoped_paths": ["skills"],
            "include_all_active_source_slices": True,
            "task_context_digest": context_digest,
        },
        source_nodes=fixture_source_nodes(fixture),
    )


def _source_inventory(fixture: Mapping[str, Any]) -> list[dict[str, str]]:
    fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
    sources = validate_fixture_skill_sources(fixture_id, fixture)
    inventory: list[dict[str, str]] = []
    workspace = fixture_workspace_relative_path(fixture)
    for skill_id, source in sorted(sources.items()):
        relative_path = _relative_path(
            _nonempty(
                source.get("relative_path"), field=f"{fixture_id}.{skill_id}.path"
            ),
            field=f"{fixture_id}.{skill_id}.relative_path",
        )
        content = _nonempty(
            source.get("content"), field=f"{fixture_id}.{skill_id}.content"
        )
        inventory.append(
            {
                "skill_id": skill_id,
                "relative_path": relative_path,
                "workspace_path": f"{workspace}/{relative_path}",
                "content_digest": content_digest_for(content),
                "raw_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "source_node_id": fixture_source_node_id(fixture_id, skill_id, content),
            }
        )
    return inventory


def _request_record(
    *,
    request_id: str,
    fixture: Mapping[str, Any],
    objective: str,
    artifact_path: str,
    input_digest: str,
    preflight: Mapping[str, Any],
    task_context_digest_value: str,
    task_context_artifact: str,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "fixture_id": _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id"),
        "objective": objective,
        "phase": "start",
        "cache_policy": "none",
        "input_digest": input_digest,
        "preflight_id": _nonempty(preflight.get("preflight_id"), field="preflight.id"),
        "preflight_digest": stable_digest(dict(preflight)),
        "preflight_artifact": artifact_path,
        "task_context_digest": task_context_digest_value,
        "task_context_artifact": task_context_artifact,
    }


def _plan_identity(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key not in {"run_manifest_id", "run_manifest_digest"}
    }


def build_benchmark_preparation(
    *,
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return a host intake plan and fresh-workspace artifacts without writing."""

    fixtures = _fixture_records(behavioral_fixtures)
    cases = _routing_records(routing_golden)
    fixtures_by_domain = {
        _nonempty(fixture.get("domain"), field="fixture.domain"): fixture
        for fixture in fixtures
    }
    unknown_domains = sorted(
        {
            _nonempty(case.get("domain"), field="routing.case.domain") for case in cases
        }.difference(fixtures_by_domain)
    )
    if unknown_domains:
        raise ValueError(
            "routing cases require a behavioral fixture for every domain: "
            f"{unknown_domains}."
        )

    artifacts: dict[str, str] = {}
    fixture_records: list[dict[str, Any]] = []
    behavioral_requests: list[dict[str, Any]] = []
    for fixture in fixtures:
        fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
        objective = _nonempty(fixture.get("objective"), field=f"{fixture_id}.objective")
        workspace = fixture_workspace_relative_path(fixture)
        context = validate_fixture_task_context(fixture_id, fixture)
        context_digest = stable_digest(context)
        context_path = f"host-inputs/behavioral-{fixture_id}-task-context.json"
        artifacts[context_path] = _json_text(context)
        for skill_id, source in validate_fixture_skill_sources(
            fixture_id, fixture
        ).items():
            source_path = _relative_path(
                _nonempty(
                    source.get("relative_path"), field=f"{fixture_id}.{skill_id}.path"
                ),
                field=f"{fixture_id}.{skill_id}.relative_path",
            )
            artifacts[f"{workspace}/{source_path}"] = _nonempty(
                source.get("content"), field=f"{fixture_id}.{skill_id}.content"
            )
        preflight = prepare_fixture_preflight(fixture=fixture, objective=objective)
        preflight_path = f"host-inputs/behavioral-{fixture_id}-preflight.json"
        artifacts[preflight_path] = _json_text(preflight)
        behavioral_requests.append(
            _request_record(
                request_id=f"behavioral-{fixture_id}",
                fixture=fixture,
                objective=objective,
                artifact_path=preflight_path,
                input_digest=stable_digest(
                    {
                        "fixture_id": fixture_id,
                        "objective": objective,
                        "phase": "start",
                        "cache_policy": "none",
                        "task_context_digest": context_digest,
                    }
                ),
                preflight=preflight,
                task_context_digest_value=context_digest,
                task_context_artifact=context_path,
            )
        )
        fixture_records.append(
            {
                "fixture_id": fixture_id,
                "domain": _nonempty(
                    fixture.get("domain"), field=f"{fixture_id}.domain"
                ),
                "workspace_root": workspace,
                "source_inventory": _source_inventory(fixture),
                "task_context_digest": context_digest,
                "task_context_artifact": context_path,
            }
        )

    routing_requests: list[dict[str, Any]] = []
    for case in cases:
        case_id = _nonempty(case.get("case_id"), field="routing.case_id")
        objective = _nonempty(case.get("objective"), field=f"{case_id}.objective")
        fixture = fixtures_by_domain[
            _nonempty(case.get("domain"), field=f"{case_id}.domain")
        ]
        preflight = prepare_fixture_preflight(fixture=fixture, objective=objective)
        preflight_path = f"host-inputs/routing-{case_id}-preflight.json"
        artifacts[preflight_path] = _json_text(preflight)
        context = validate_fixture_task_context(
            _nonempty(fixture.get("fixture_id"), field=f"{case_id}.fixture_id"),
            fixture,
        )
        context_digest = stable_digest(context)
        context_path = f"host-inputs/routing-{case_id}-task-context.json"
        artifacts[context_path] = _json_text(context)
        routing_requests.append(
            _request_record(
                request_id=f"routing-{case_id}",
                fixture=fixture,
                objective=objective,
                artifact_path=preflight_path,
                input_digest=stable_digest(
                    {
                        "routing_input_digest": routing_input_digest(case),
                        "task_context_digest": context_digest,
                    }
                ),
                preflight=preflight,
                task_context_digest_value=context_digest,
                task_context_artifact=context_path,
            )
            | {"case_id": case_id}
        )

    plan: dict[str, Any] = {
        "schema": BENCHMARK_RUN_PLAN_SCHEMA,
        "protocol": {
            "schema": BENCHMARK_PROTOCOL_SCHEMA,
            "cache_policy": "none",
            "tmcp_role": "compile_and_validate_only",
            "host_role": "propose_semantics_then_execute_explicit_controls",
            "automatic_tool_execution": False,
            "receipt_persistence": "explicit_host_write_only",
        },
        "runtime": {
            "release": VERSION.release,
            "compiler_contract_digest": stable_digest(
                {
                    "composition_plan_schema": "tmcp-composition-plan-v0.1",
                    "preflight_schema": "tmcp-composition-preflight-v0.1",
                    "semantic_proposal_schema": "tmcp-semantic-proposal-v0.1",
                }
            ),
        },
        "catalog": {
            "routing_golden_digest": stable_digest(dict(routing_golden)),
            "behavioral_fixtures_digest": stable_digest(dict(behavioral_fixtures)),
        },
        "fixture_workspaces": fixture_records,
        "routing_requests": routing_requests,
        "behavioral_requests": behavioral_requests,
    }
    identity = _plan_identity(plan)
    plan["run_manifest_digest"] = stable_digest(identity)
    plan["run_manifest_id"] = "benchmark-run-" + stable_digest(identity, 20)
    artifacts["benchmark-run-plan.json"] = _json_text(plan)
    return plan, artifacts


def validate_benchmark_run_plan(
    plan: Mapping[str, Any],
    *,
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
) -> None:
    """Fail closed when a plan is stale, malformed, or detached from its catalog."""

    expected, _artifacts = build_benchmark_preparation(
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    if dict(plan) != expected:
        raise ValueError(
            "Benchmark run plan does not match the supplied fixture and routing catalog."
        )
