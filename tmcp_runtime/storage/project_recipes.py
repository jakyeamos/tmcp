"""Secure, explicit project-local composition recipe persistence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tmcp_runtime.domain.composition_phase_bindings import (
    PhaseCapsuleBindingError,
    validate_phase_capsule_binding,
)
from tmcp_runtime.safety import (
    collect_harvest_roots,
    redact_json_value,
    redact_path,
    read_json_input,
)
from tmcp_runtime.storage.project_recipe_promotion_validation import (
    PHASE_CAPSULE_BOUND as _PHASE_CAPSULE_BOUND,
    PHASE_CAPSULE_LEGACY_UNBOUND as _PHASE_CAPSULE_LEGACY_UNBOUND,
    PROJECT_RECIPE_PROMOTION_SCHEMA,
    legacy_promotion_is_readable as _legacy_promotion_is_readable,
    phase_capsule_binding_status as _phase_capsule_binding_status,
    promotion_is_valid as _promotion_is_valid,
)
from tmcp_runtime.storage.artifacts import AtomicArtifactStore
from tmcp_runtime.storage.cache_policy import cache_json_is_bounded
from tmcp_runtime.storage.project_recipe_runtime_capsules import (
    RUNTIME_CAPSULE_BOUND as _RUNTIME_CAPSULE_BOUND,
    RUNTIME_CAPSULE_LEGACY_UNBOUND as _RUNTIME_CAPSULE_LEGACY_UNBOUND,
    RecipeRuntimeCapsuleError,
    recipe_runtime_capsule_hash_paths,
    recipe_runtime_capsule_sha256_literals,
    recipe_runtime_capsule_status,
    restore_recipe_runtime_capsule_digests,
)


PROJECT_COMPOSITION_RECIPE_SCHEMA = "tmcp-project-composition-recipe-v0.1"
PROJECT_COMPOSITION_RECIPE_FORMAT_VERSION = 1
COMPOSITION_PLAN_SCHEMA = "tmcp-composition-plan-v0.1"
MAX_PROJECT_RECIPE_BYTES = 524_288
MAX_PROJECT_RECIPE_DEPTH, MAX_PROJECT_RECIPE_NODES = 48, 4_096

_RECIPE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
_RECIPE_KEY_PATTERN = re.compile(r"recipe-[a-f0-9]{32}")
_GRAPH_DIGEST_PATTERN = re.compile(r"[a-f0-9]{32}")
_PLAN_ID_PATTERN = re.compile(r"composition-[a-f0-9]{20}")
_DIGEST_64_RE = re.compile(r"[a-f0-9]{64}")

_RECIPE_HASH_PATHS: tuple[tuple[str | int, ...], ...] = (
    (
        "composition_recipe",
        "phase_capsule_binding",
        "composition_plan_digest",
    ),
    (
        "composition_recipe",
        "phase_capsule_binding",
        "context_accounting_digest",
    ),
    (
        "composition_recipe",
        "phase_capsule_binding",
        "preflight_capsule_digest",
    ),
    ("composition_recipe", "phase_capsule_binding", "binding_digest"),
    (
        "composition_recipe",
        "phase_capsule_binding",
        "phase_capsule_trace",
        "*",
        "capsule_digest",
    ),
    (
        "composition_recipe",
        "phase_capsule_binding",
        "phase_capsule_trace",
        "*",
        "incoming_handoff_digests",
        "*",
    ),
    *recipe_runtime_capsule_hash_paths(),
    ("promotion_eligibility", "phase_capsule_binding_digest"),
)


class ProjectRecipeError(ValueError):
    """Raised when a project recipe violates its explicit local boundary."""


@dataclass(frozen=True)
class ProjectRecipeSnapshot:
    """One validated and redacted project-local composition recipe."""

    path: Path
    display_path: str
    key: str
    record: dict[str, Any]
    phase_capsule_binding_status: str
    runtime_capsule_status: str

    def metadata(self) -> dict[str, Any]:
        return {
            "record_schema": PROJECT_COMPOSITION_RECIPE_SCHEMA,
            "key": self.key,
            "path": self.display_path,
            "recipe_id": self.record.get("recipe_id"),
            "graph_digest": self.record.get("graph_digest"),
            "state_effect": "project_local_write",
            "activation_policy": "explicit_load_only",
            "phase_capsule_binding_status": self.phase_capsule_binding_status,
            "runtime_capsule_status": self.runtime_capsule_status,
            "activation_eligibility": (
                "verified_runtime_capsule_binding"
                if self.phase_capsule_binding_status == _PHASE_CAPSULE_BOUND
                and self.runtime_capsule_status == _RUNTIME_CAPSULE_BOUND
                else (
                    "blocked_runtime_capsule_unbound"
                    if self.phase_capsule_binding_status == _PHASE_CAPSULE_BOUND
                    else "blocked_legacy_unbound"
                )
            ),
        }


def _recipe_id(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise ProjectRecipeError("recipe_id must be a non-empty opaque identifier.")
    identifier = value.strip()
    if not _RECIPE_ID_PATTERN.fullmatch(identifier):
        raise ProjectRecipeError(
            "recipe_id must use 1-80 letters, numbers, dots, underscores, or hyphens."
        )
    safe_identifier, redactions = redact_json_value(identifier, enabled=True)
    if safe_identifier != identifier or redactions:
        raise ProjectRecipeError("recipe_id must not contain sensitive material.")
    return identifier


def _recipe_key(recipe_id: str) -> str:
    digest = hashlib.sha256(recipe_id.encode()).hexdigest()[:32]
    return f"recipe-{digest}"


def _literal_digest(
    literals: Mapping[tuple[str | int, ...], str],
    path: tuple[str | int, ...],
) -> str | None:
    value = literals.get(path)
    return value if isinstance(value, str) and _DIGEST_64_RE.fullmatch(value) else None


def _recipe_sha256_literals(
    source: Mapping[str, Any],
) -> dict[tuple[str | int, ...], str]:
    """Return the closed set of persistable compiler digests from memory.

    Creation receives a compiler record in memory, while loading receives this
    same projection from ``read_json_input``.  Keeping both paths in the same
    closed location set prevents source prose or arbitrary digest-shaped fields
    from escaping redaction.
    """

    literals: dict[tuple[str | int, ...], str] = {}

    def add(path: tuple[str | int, ...], value: object) -> None:
        if isinstance(value, str) and _DIGEST_64_RE.fullmatch(value):
            literals[path] = value

    source_recipe = source.get("composition_recipe")
    source_binding = (
        source_recipe.get("phase_capsule_binding")
        if isinstance(source_recipe, Mapping)
        else None
    )
    if isinstance(source_binding, Mapping):
        binding_prefix = ("composition_recipe", "phase_capsule_binding")
        for key in (
            "composition_plan_digest",
            "context_accounting_digest",
            "preflight_capsule_digest",
            "binding_digest",
        ):
            add((*binding_prefix, key), source_binding.get(key))
        trace = source_binding.get("phase_capsule_trace")
        if isinstance(trace, list):
            for stage_index, stage in enumerate(trace):
                if not isinstance(stage, Mapping):
                    continue
                stage_prefix = (*binding_prefix, "phase_capsule_trace", stage_index)
                add((*stage_prefix, "capsule_digest"), stage.get("capsule_digest"))
                handoffs = stage.get("incoming_handoff_digests")
                if isinstance(handoffs, list):
                    for handoff_index, digest in enumerate(handoffs):
                        add(
                            (*stage_prefix, "incoming_handoff_digests", handoff_index),
                            digest,
                        )

    if isinstance(source_recipe, Mapping):
        literals.update(recipe_runtime_capsule_sha256_literals(source_recipe))

    source_promotion = source.get("promotion_eligibility")
    if isinstance(source_promotion, Mapping):
        add(
            ("promotion_eligibility", "phase_capsule_binding_digest"),
            source_promotion.get("phase_capsule_binding_digest"),
        )
    return literals


def _restore_phase_capsule_binding_digests(
    literals: Mapping[tuple[str | int, ...], str], payload: dict[str, Any]
) -> int:
    """Restore compiler-issued digest fields after content redaction.

    These fields are fixed-length hashes validated again by the recipe loader;
    retaining them is necessary for the stored receipt binding to remain
    verifiable.  Source prose and bridge instructions are never restored.
    """

    safe_recipe = payload.get("composition_recipe")
    if not isinstance(safe_recipe, dict):
        return 0
    safe_binding = safe_recipe.get("phase_capsule_binding")
    if not isinstance(safe_binding, dict):
        return 0
    restored = 0
    binding_prefix = ("composition_recipe", "phase_capsule_binding")
    for key in (
        "composition_plan_digest",
        "context_accounting_digest",
        "preflight_capsule_digest",
        "binding_digest",
    ):
        value = _literal_digest(literals, (*binding_prefix, key))
        if value is not None:
            if safe_binding.get(key) != value:
                safe_binding[key] = value
                restored += 1
    safe_trace = safe_binding.get("phase_capsule_trace")
    if isinstance(safe_trace, list):
        for stage_index, safe_stage in enumerate(safe_trace):
            if not isinstance(safe_stage, dict):
                continue
            stage_prefix = (*binding_prefix, "phase_capsule_trace", stage_index)
            capsule_digest = _literal_digest(literals, (*stage_prefix, "capsule_digest"))
            if capsule_digest is not None and safe_stage.get("capsule_digest") != capsule_digest:
                safe_stage["capsule_digest"] = capsule_digest
                restored += 1
            safe_handoffs = safe_stage.get("incoming_handoff_digests")
            if not isinstance(safe_handoffs, list):
                continue
            restored_handoffs: list[str] = []
            for handoff_index in range(len(safe_handoffs)):
                digest = _literal_digest(
                    literals,
                    (*stage_prefix, "incoming_handoff_digests", handoff_index),
                )
                if digest is None:
                    restored_handoffs = []
                    break
                restored_handoffs.append(digest)
            if restored_handoffs and safe_handoffs != restored_handoffs:
                safe_stage["incoming_handoff_digests"] = restored_handoffs
                restored += len(restored_handoffs)
    return restored


def _restore_promotion_binding_digest(
    literals: Mapping[tuple[str | int, ...], str], payload: dict[str, Any]
) -> int:
    safe_promotion = payload.get("promotion_eligibility")
    if not isinstance(safe_promotion, dict):
        return 0
    value = _literal_digest(
        literals,
        ("promotion_eligibility", "phase_capsule_binding_digest"),
    )
    if value is None:
        return 0
    if safe_promotion.get("phase_capsule_binding_digest") == value:
        return 0
    safe_promotion["phase_capsule_binding_digest"] = value
    return 1


def _restore_fixed_schema_literals(
    payload: dict[str, Any],
    *,
    sha256_literals: Mapping[tuple[str | int, ...], str] | None = None,
) -> int:
    """Restore only fixed, non-secret literals redacted as false positives."""

    promotion = payload.get("promotion_eligibility")
    restored = 0
    if isinstance(promotion, dict):
        redacted_schema, _ = redact_json_value(
            PROJECT_RECIPE_PROMOTION_SCHEMA,
            enabled=True,
        )
        if promotion.get("schema") == redacted_schema:
            promotion["schema"] = PROJECT_RECIPE_PROMOTION_SCHEMA
            restored += 1
    if sha256_literals is not None:
        restored += _restore_phase_capsule_binding_digests(sha256_literals, payload)
        restored += restore_recipe_runtime_capsule_digests(sha256_literals, payload)
        restored += _restore_promotion_binding_digest(sha256_literals, payload)
    return restored


def _project_root(project_path: str | Path) -> Path:
    path = Path(project_path).expanduser()
    if not path.is_absolute():
        raise ProjectRecipeError("project_path must be absolute for project recipes.")
    roots, warnings = collect_harvest_roots([path], follow_symlinks=False)
    if warnings:
        raise ProjectRecipeError(
            "Could not validate project path for project recipe: "
            f"{redact_path('; '.join(warnings))}"
        )
    if len(roots) != 1 or roots[0].kind != "directory":
        raise ProjectRecipeError(
            "project_path must be one real directory for project recipes."
        )
    return roots[0].logical_path


def _json_is_bounded(value: object) -> bool:
    if not cache_json_is_bounded(
        value,
        maximum_nodes=MAX_PROJECT_RECIPE_NODES,
        maximum_depth=MAX_PROJECT_RECIPE_DEPTH,
    ):
        return False
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (MemoryError, RecursionError, TypeError, ValueError):
        return False
    return len(encoded.encode("utf-8")) <= MAX_PROJECT_RECIPE_BYTES


def _recipe_projection_structure_is_valid(
    value: object,
    *,
    plan_id: str,
    graph_digest: str,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        value.get("composition_plan_id") == plan_id
        and value.get("graph_digest") == graph_digest
        and isinstance(value.get("current_phase"), str)
        and bool(str(value.get("current_phase")).strip())
        and isinstance(value.get("task_model"), Mapping)
        and isinstance(value.get("skill_roles"), list)
        and isinstance(value.get("typed_edges"), list)
        and isinstance(value.get("ordered_stages"), list)
        and isinstance(value.get("coverage"), Mapping)
        and (
            value.get("runtime_capsule") is None
            or isinstance(value.get("runtime_capsule"), Mapping)
        )
        and value.get("trust") == "advisory_untrusted"
        and isinstance(value.get("instruction_override_policy"), str)
        and bool(str(value.get("instruction_override_policy")).strip())
    )


def _record_snapshot(
    path: Path,
    payload: dict[str, Any],
    *,
    expected_recipe_id: str,
    expected_key: str,
    expected_graph_digest: str,
    expected_composition_plan_id: str | None = None,
    allow_legacy_unbound: bool = False,
    allow_legacy_runtime_capsule: bool = False,
) -> ProjectRecipeSnapshot:
    if not _json_is_bounded(payload):
        raise ProjectRecipeError("Project recipe exceeds supported JSON boundaries.")
    if payload.get("schema") != PROJECT_COMPOSITION_RECIPE_SCHEMA:
        raise ProjectRecipeError("Project recipe has an unsupported schema.")
    if payload.get("format_version") != PROJECT_COMPOSITION_RECIPE_FORMAT_VERSION:
        raise ProjectRecipeError("Project recipe has an unsupported format version.")
    if (
        not isinstance(payload.get("created_at"), str)
        or not str(payload["created_at"]).strip()
    ):
        raise ProjectRecipeError("Project recipe is missing created_at.")

    recipe_id = payload.get("recipe_id")
    key = payload.get("recipe_key")
    plan_id = payload.get("composition_plan_id")
    graph_digest = payload.get("graph_digest")
    if recipe_id != expected_recipe_id or key != expected_key:
        raise ProjectRecipeError("Project recipe identity does not match its key.")
    if key != _recipe_key(expected_recipe_id) or not _RECIPE_KEY_PATTERN.fullmatch(
        str(key)
    ):
        raise ProjectRecipeError("Project recipe has an invalid opaque key.")
    if (
        not isinstance(plan_id, str)
        or not _PLAN_ID_PATTERN.fullmatch(plan_id)
        or not isinstance(graph_digest, str)
        or not _GRAPH_DIGEST_PATTERN.fullmatch(graph_digest)
    ):
        raise ProjectRecipeError("Project recipe plan identity is invalid.")
    if graph_digest != expected_graph_digest:
        raise ProjectRecipeError("Project recipe is stale for the current graph.")
    if (
        expected_composition_plan_id is not None
        and plan_id != expected_composition_plan_id
    ):
        raise ProjectRecipeError("Project recipe does not match the composition plan.")
    if (
        payload.get("source_plan_schema") != COMPOSITION_PLAN_SCHEMA
        or payload.get("cache_policy") != "project"
        or payload.get("status") != "reviewed_promoted"
        or payload.get("explicit_promotion") is not True
        or payload.get("activation_policy") != "explicit_load_only"
        or payload.get("trust") != "advisory_untrusted"
        or not isinstance(payload.get("instruction_override_policy"), str)
        or not str(payload.get("instruction_override_policy")).strip()
    ):
        raise ProjectRecipeError("Project recipe policy metadata is invalid.")
    if not _recipe_projection_structure_is_valid(
        payload.get("composition_recipe"),
        plan_id=plan_id,
        graph_digest=graph_digest,
    ):
        raise ProjectRecipeError("Project recipe plan projection is malformed.")
    projection = payload.get("composition_recipe")
    assert isinstance(projection, Mapping)
    promotion = payload.get("promotion_eligibility")
    phase_capsule_status = _phase_capsule_binding_status(projection, promotion)
    runtime_capsule_status = _RUNTIME_CAPSULE_LEGACY_UNBOUND
    if phase_capsule_status == _PHASE_CAPSULE_BOUND:
        try:
            phase_capsule_binding = validate_phase_capsule_binding(
                projection.get("phase_capsule_binding")
            )
        except PhaseCapsuleBindingError as exc:
            raise ProjectRecipeError(
                "Project recipe phase-capsule binding is invalid."
            ) from exc
        if (
            phase_capsule_binding["composition_plan_id"] != plan_id
            or phase_capsule_binding["graph_digest"] != graph_digest
        ):
            raise ProjectRecipeError("Project recipe phase-capsule binding is stale.")
        if not _promotion_is_valid(
            promotion,
            recipe_id=expected_recipe_id,
            graph_digest=graph_digest,
            phase_capsule_binding=phase_capsule_binding,
        ):
            raise ProjectRecipeError("Project recipe promotion evidence is invalid.")
        try:
            runtime_capsule_status = recipe_runtime_capsule_status(
                projection,
                phase_capsule_binding,
                allow_legacy=allow_legacy_runtime_capsule,
            )
        except RecipeRuntimeCapsuleError as exc:
            raise ProjectRecipeError(f"Project recipe {exc}") from exc
    elif phase_capsule_status == _PHASE_CAPSULE_LEGACY_UNBOUND:
        if not allow_legacy_unbound:
            raise ProjectRecipeError(
                "Project recipe phase-capsule binding is required for new records."
            )
        if not _legacy_promotion_is_readable(
            promotion,
            recipe_id=expected_recipe_id,
            graph_digest=graph_digest,
        ):
            raise ProjectRecipeError("Project recipe legacy promotion metadata is invalid.")
        if "runtime_capsule" in projection:
            raise ProjectRecipeError(
                "Project recipe runtime capsule cannot outlive phase provenance."
            )
    else:
        raise ProjectRecipeError(
            "Project recipe phase-capsule binding is incomplete or downgraded."
        )
    summary = payload.get("redaction_summary")
    if not isinstance(summary, Mapping) or not all(
        isinstance(key, str)
        and not isinstance(count, bool)
        and isinstance(count, int)
        and count >= 0
        for key, count in summary.items()
    ):
        raise ProjectRecipeError("Project recipe redaction metadata is invalid.")
    return ProjectRecipeSnapshot(
        path=path,
        display_path=redact_path(path),
        key=expected_key,
        record=dict(payload),
        phase_capsule_binding_status=phase_capsule_status,
        runtime_capsule_status=runtime_capsule_status,
    )


@dataclass(frozen=True)
class ProjectCompositionRecipeStore:
    """A create-only recipe record addressed by one explicit opaque identifier."""

    project_root: Path
    recipe_id: str
    key: str
    path: Path

    @classmethod
    def open(
        cls,
        project_path: str | Path,
        recipe_id: object,
    ) -> ProjectCompositionRecipeStore:
        root = _project_root(project_path)
        identifier = _recipe_id(recipe_id)
        key = _recipe_key(identifier)
        return cls(
            project_root=root,
            recipe_id=identifier,
            key=key,
            path=root / ".tmcp" / "composition-recipes" / key / "recipe.json",
        )

    def create(self, record: Mapping[str, Any]) -> ProjectRecipeSnapshot:
        candidate = dict(record)
        candidate["recipe_key"] = self.key
        candidate["redaction_summary"] = {}
        _record_snapshot(
            self.path,
            candidate,
            expected_recipe_id=self.recipe_id,
            expected_key=self.key,
            expected_graph_digest=str(candidate.get("graph_digest") or ""),
        )
        try:
            redacted, redactions = redact_json_value(candidate, enabled=True)
        except (MemoryError, RecursionError) as exc:
            raise ProjectRecipeError("Could not redact project recipe safely.") from exc
        if not isinstance(redacted, dict):
            raise ProjectRecipeError("Project recipe must be a JSON object.")
        restored_literals = _restore_fixed_schema_literals(
            redacted,
            sha256_literals=_recipe_sha256_literals(candidate),
        )
        if restored_literals and redactions.get("long_high_entropy"):
            remaining = max(
                0, redactions["long_high_entropy"] - restored_literals
            )
            if remaining:
                redactions["long_high_entropy"] = remaining
            else:
                del redactions["long_high_entropy"]
        redacted["redaction_summary"] = redactions
        snapshot = _record_snapshot(
            self.path,
            redacted,
            expected_recipe_id=self.recipe_id,
            expected_key=self.key,
            expected_graph_digest=str(candidate["graph_digest"]),
        )
        recipes_root = self.path.parent.parent
        store = AtomicArtifactStore.explicit(recipes_root)
        with store.locked(f"{self.key}.lock"):
            AtomicArtifactStore.write_json_bundle(
                self.path.parent,
                {self.path.name: redacted},
            )
        return snapshot

    def load(
        self,
        *,
        expected_graph_digest: str,
        expected_composition_plan_id: str | None = None,
    ) -> ProjectRecipeSnapshot:
        if not _GRAPH_DIGEST_PATTERN.fullmatch(expected_graph_digest):
            raise ProjectRecipeError("A valid current graph digest is required.")
        hash_paths = _RECIPE_HASH_PATHS
        try:
            source = read_json_input(
                self.path,
                project_path=self.project_root,
                max_file_bytes=MAX_PROJECT_RECIPE_BYTES,
                preserve_sha256_paths=hash_paths,
            )
        except (MemoryError, RecursionError, ValueError) as exc:
            raise ProjectRecipeError(
                f"Could not load project recipe: {redact_path(str(exc))}"
            ) from exc
        _restore_fixed_schema_literals(
            source.payload,
            sha256_literals=source.preserved_sha256_literals,
        )
        return _record_snapshot(
            self.path,
            source.payload,
            expected_recipe_id=self.recipe_id,
            expected_key=self.key,
            expected_graph_digest=expected_graph_digest,
            expected_composition_plan_id=expected_composition_plan_id,
            allow_legacy_unbound=True,
            allow_legacy_runtime_capsule=True,
        )

    def load_record(self) -> ProjectRecipeSnapshot:
        """Load one exact-ID record for service-level preflight revalidation."""

        hash_paths = _RECIPE_HASH_PATHS
        try:
            source = read_json_input(
                self.path,
                project_path=self.project_root,
                max_file_bytes=MAX_PROJECT_RECIPE_BYTES,
                preserve_sha256_paths=hash_paths,
            )
        except (MemoryError, RecursionError, ValueError) as exc:
            raise ProjectRecipeError(
                f"Could not load project recipe: {redact_path(str(exc))}"
            ) from exc
        _restore_fixed_schema_literals(
            source.payload,
            sha256_literals=source.preserved_sha256_literals,
        )
        graph_digest = source.payload.get("graph_digest")
        if not isinstance(graph_digest, str):
            raise ProjectRecipeError("Project recipe plan identity is invalid.")
        return _record_snapshot(
            self.path,
            source.payload,
            expected_recipe_id=self.recipe_id,
            expected_key=self.key,
            expected_graph_digest=graph_digest,
            allow_legacy_unbound=True,
            allow_legacy_runtime_capsule=True,
        )
