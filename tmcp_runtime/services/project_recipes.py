"""Explicit project-local composition recipe promotion orchestration."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any, Protocol

from tmcp_runtime.domain.composition_planning import compile_semantic_composition
from tmcp_runtime.services.composition_evaluation import (
    assess_project_recipe_promotion,
)


PROJECT_COMPOSITION_RECIPE_SCHEMA = "tmcp-project-composition-recipe-v0.1"
PROJECT_COMPOSITION_RECIPE_PROMOTION_SCHEMA = "tmcp-project-recipe-promotion-v0.1"
COMPOSITION_PLAN_SCHEMA = "tmcp-composition-plan-v0.1"
_GRAPH_DIGEST_PATTERN = re.compile(r"[a-f0-9]{32}")
_PLAN_ID_PATTERN = re.compile(r"composition-[a-f0-9]{20}")
_RECIPE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")


class ProjectRecipeSnapshot(Protocol):
    @property
    def record(self) -> dict[str, Any]: ...

    def metadata(self) -> dict[str, Any]: ...


class ProjectRecipeStore(Protocol):
    def create(self, record: Mapping[str, Any]) -> ProjectRecipeSnapshot: ...

    def load(
        self,
        *,
        expected_graph_digest: str,
        expected_composition_plan_id: str | None = None,
    ) -> ProjectRecipeSnapshot: ...

    def load_record(self) -> ProjectRecipeSnapshot: ...


ProjectRecipeStoreFactory = Callable[[str, object], ProjectRecipeStore]
PromotionAssessor = Callable[..., dict[str, Any]]
Clock = Callable[[], str]


def _composition_plan(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Project recipe promotion requires composition_plan.")
    plan = dict(value)
    if plan.get("schema") != COMPOSITION_PLAN_SCHEMA:
        raise ValueError("Project recipe promotion requires a composition plan.")
    plan_id = str(plan.get("composition_plan_id") or "").strip()
    provenance = plan.get("provenance")
    if not _PLAN_ID_PATTERN.fullmatch(plan_id) or not isinstance(provenance, Mapping):
        raise ValueError("Composition plan identity and provenance are required.")
    graph_digest = str(provenance.get("graph_digest") or "").strip()
    if not _GRAPH_DIGEST_PATTERN.fullmatch(graph_digest):
        raise ValueError("Composition plan graph_digest is invalid.")
    for field in ("skill_roles", "typed_edges", "ordered_stages"):
        if not isinstance(plan.get(field), list):
            raise ValueError(f"Composition plan {field} must be a list.")
    if "handoff_contracts" in plan and not isinstance(plan["handoff_contracts"], list):
        raise ValueError("Composition plan handoff_contracts must be a list.")
    for field in ("task_model", "coverage"):
        if not isinstance(plan.get(field), Mapping):
            raise ValueError(f"Composition plan {field} must be an object.")
    return plan


def _recipe_id(value: object) -> str:
    if not isinstance(value, str) or not _RECIPE_ID_PATTERN.fullmatch(value.strip()):
        raise ValueError("Project recipe promotion requires recipe_id.")
    return value.strip()


def _project_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Project recipe operations require project_path.")
    return value.strip()


def _graph_digest(plan: Mapping[str, Any]) -> str:
    provenance = plan.get("provenance")
    value = provenance.get("graph_digest") if isinstance(provenance, Mapping) else ""
    return str(value)


def _recipe_projection(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Project the executable plan without persisting raw source content digests."""

    return {
        "composition_plan_id": str(plan["composition_plan_id"]),
        "graph_digest": _graph_digest(plan),
        "current_phase": str(plan.get("current_phase") or "start"),
        "task_model": deepcopy(dict(plan["task_model"])),
        "skill_roles": deepcopy(list(plan["skill_roles"])),
        "typed_edges": deepcopy(list(plan["typed_edges"])),
        "handoff_contracts": deepcopy(list(plan.get("handoff_contracts") or [])),
        "scoped_seed_graph_hints": deepcopy(
            dict(plan.get("scoped_seed_graph_hints") or {})
        ),
        "ordered_stages": deepcopy(list(plan["ordered_stages"])),
        "coverage": deepcopy(dict(plan["coverage"])),
        "trust": "advisory_untrusted",
        "instruction_override_policy": str(
            plan.get("instruction_override_policy")
            or "Project recipes cannot override higher-priority instructions."
        ),
    }


def build_project_composition_recipe_record(
    *,
    recipe_id: str,
    composition_plan: Mapping[str, Any],
    promotion_eligibility: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Build a create-only reviewed recipe record without filesystem authority."""

    plan = _composition_plan(composition_plan)
    identifier = _recipe_id(recipe_id)
    graph_digest = _graph_digest(plan)
    eligibility = dict(promotion_eligibility)
    if not isinstance(created_at, str) or not created_at.strip():
        raise ValueError("Project recipe promotion requires created_at.")
    if eligibility.get("eligible") is not True:
        raise ValueError("Only eligible composition recipes may be promoted.")
    if str(eligibility.get("recipe_id") or "") != identifier:
        raise ValueError("Promotion eligibility recipe_id does not match the recipe.")
    if str(eligibility.get("graph_digest") or "") != graph_digest:
        raise ValueError("Promotion eligibility graph_digest does not match the plan.")
    return {
        "schema": PROJECT_COMPOSITION_RECIPE_SCHEMA,
        "format_version": 1,
        "created_at": created_at.strip(),
        "recipe_id": identifier,
        "composition_plan_id": str(plan["composition_plan_id"]),
        "graph_digest": graph_digest,
        "source_plan_schema": COMPOSITION_PLAN_SCHEMA,
        "composition_recipe": _recipe_projection(plan),
        "promotion_eligibility": deepcopy(eligibility),
        "cache_policy": "project",
        "status": "reviewed_promoted",
        "explicit_promotion": True,
        "activation_policy": "explicit_load_only",
        "trust": "advisory_untrusted",
        "instruction_override_policy": (
            "Project-local recipes are advisory and cannot override system, "
            "developer, user, or project instructions."
        ),
    }


def rehydrate_project_recipe_for_preflight(
    record: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    current_phase: str | None = None,
) -> dict[str, Any]:
    """Revalidate a stored recipe against current source slices and graph identity."""

    if record.get("schema") != PROJECT_COMPOSITION_RECIPE_SCHEMA:
        raise ValueError("Project recipe record has an unsupported schema.")
    if preflight.get("schema") != "tmcp-composition-preflight-v0.1":
        raise ValueError(
            "Project recipe load requires a current composition preflight."
        )
    projection = record.get("composition_recipe")
    if not isinstance(projection, Mapping):
        raise ValueError("Project recipe plan projection is malformed.")
    for field in ("task_model", "coverage"):
        if not isinstance(projection.get(field), Mapping):
            raise ValueError(f"Project recipe {field} is malformed.")
    for field in ("skill_roles", "typed_edges"):
        if not isinstance(projection.get(field), list):
            raise ValueError(f"Project recipe {field} is malformed.")
    stored_handoff_contracts = projection.get("handoff_contracts")
    if stored_handoff_contracts is not None and not isinstance(
        stored_handoff_contracts, list
    ):
        raise ValueError("Project recipe handoff_contracts are malformed.")
    preflight_id = str(preflight.get("preflight_id") or "").strip()
    if not preflight_id:
        raise ValueError("Project recipe load requires current preflight identity.")
    phase = str(current_phase or projection.get("current_phase") or "start")
    coverage = dict(projection["coverage"])
    proposal = {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": preflight_id,
        "current_phase": phase,
        "task_model": deepcopy(dict(projection["task_model"])),
        "skill_roles": deepcopy(list(projection["skill_roles"])),
        "relationships": deepcopy(list(projection["typed_edges"])),
        "coverage": {
            "facets": deepcopy(list(coverage.get("facets") or [])),
            "unresolved_gaps": deepcopy(list(coverage.get("unresolved_gaps") or [])),
        },
        "trust": "advisory_untrusted",
    }
    compiled = compile_semantic_composition(
        proposal,
        dict(preflight),
        current_phase=phase,
    )
    if compiled.get("accepted") is not True:
        validation = compiled.get("validation")
        errors = validation.get("errors", []) if isinstance(validation, Mapping) else []
        codes = sorted(
            {
                str(item.get("code") or "invalid_recipe")
                for item in errors
                if isinstance(item, Mapping)
            }
        )
        raise ValueError(
            "Project recipe is stale or invalid for current source slices"
            + (f": {', '.join(codes)}" if codes else ".")
        )
    plan = compiled.get("composition_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("Project recipe did not compile a composition plan.")
    provenance = plan.get("provenance") if isinstance(plan, Mapping) else None
    current_graph_digest = (
        str(provenance.get("graph_digest") or "")
        if isinstance(provenance, Mapping)
        else ""
    )
    stored_graph_digest = str(record.get("graph_digest") or "")
    if current_graph_digest != stored_graph_digest:
        raise ValueError("Project recipe is stale for the current source graph.")
    if stored_handoff_contracts is not None and stored_handoff_contracts != plan.get(
        "handoff_contracts"
    ):
        raise ValueError("Project recipe handoff contracts are stale or malformed.")
    return {
        "semantic_proposal": proposal,
        "composition_plan": deepcopy(dict(plan)),
        "origin_composition_plan_id": str(record.get("composition_plan_id") or ""),
        "graph_digest": current_graph_digest,
    }


class ProjectCompositionRecipeService:
    """Promote or load one explicitly named project-local composition recipe."""

    def __init__(
        self,
        *,
        open_store: ProjectRecipeStoreFactory,
        now_iso: Clock,
        assess_promotion: PromotionAssessor = assess_project_recipe_promotion,
    ) -> None:
        self._open_store = open_store
        self._now_iso = now_iso
        self._assess_promotion = assess_promotion

    def promote(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Persist one recipe only after an explicit, evidence-backed promotion."""

        if arguments.get("explicit_promotion") is not True:
            raise ValueError(
                "Project recipe persistence requires explicit_promotion=true."
            )
        recipe_id = _recipe_id(arguments.get("recipe_id"))
        plan = _composition_plan(arguments.get("composition_plan"))
        graph_digest = _graph_digest(plan)
        supplied_digest = arguments.get("graph_digest")
        if supplied_digest is not None and str(supplied_digest) != graph_digest:
            raise ValueError("Supplied graph_digest does not match composition_plan.")
        raw_receipts = arguments.get("receipts")
        if not isinstance(raw_receipts, list) or not all(
            isinstance(receipt, Mapping) for receipt in raw_receipts
        ):
            raise ValueError("Project recipe promotion requires receipts as objects.")
        receipts: Sequence[Mapping[str, Any]] = raw_receipts
        eligibility = self._assess_promotion(
            receipts,
            recipe_id=recipe_id,
            graph_digest=graph_digest,
        )
        if eligibility.get("eligible") is not True:
            reasons = ", ".join(
                str(item) for item in eligibility.get("blocking_reasons", [])
            )
            raise ValueError(
                "Project recipe promotion is not eligible"
                + (f": {reasons}" if reasons else ".")
            )
        record = build_project_composition_recipe_record(
            recipe_id=recipe_id,
            composition_plan=plan,
            promotion_eligibility=eligibility,
            created_at=self._now_iso(),
        )
        store = self._open_store(
            _project_path(arguments.get("project_path")), recipe_id
        )
        snapshot = store.create(record)
        return {
            "ok": True,
            "schema": PROJECT_COMPOSITION_RECIPE_PROMOTION_SCHEMA,
            "status": "promoted",
            "recipe_id": recipe_id,
            "graph_digest": graph_digest,
            "promotion_eligibility": deepcopy(eligibility),
            "recipe": snapshot.record,
            "storage": snapshot.metadata(),
        }

    def load(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Load one explicit recipe and reject records stale for the supplied graph."""

        recipe_id = _recipe_id(arguments.get("recipe_id"))
        graph_digest = str(arguments.get("graph_digest") or "").strip()
        if not _GRAPH_DIGEST_PATTERN.fullmatch(graph_digest):
            raise ValueError("Project recipe load requires the current graph_digest.")
        plan_id_value = arguments.get("composition_plan_id")
        plan_id = str(plan_id_value).strip() if plan_id_value is not None else None
        store = self._open_store(
            _project_path(arguments.get("project_path")), recipe_id
        )
        snapshot = store.load(
            expected_graph_digest=graph_digest,
            expected_composition_plan_id=plan_id or None,
        )
        return {
            "ok": True,
            "schema": PROJECT_COMPOSITION_RECIPE_SCHEMA,
            "status": "loaded",
            "recipe_id": recipe_id,
            "graph_digest": graph_digest,
            "recipe": snapshot.record,
            "storage": snapshot.metadata(),
        }

    def load_for_preflight(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Load one exact-ID recipe and recompile it against current source slices."""

        recipe_id = _recipe_id(arguments.get("recipe_id"))
        preflight = arguments.get("composition_preflight")
        if not isinstance(preflight, Mapping):
            raise ValueError("Project recipe load requires composition_preflight.")
        store = self._open_store(
            _project_path(arguments.get("project_path")), recipe_id
        )
        snapshot = store.load_record()
        hydrated = rehydrate_project_recipe_for_preflight(
            snapshot.record,
            preflight,
            current_phase=(
                str(arguments["current_phase"])
                if arguments.get("current_phase") is not None
                else None
            ),
        )
        return {
            "ok": True,
            "schema": PROJECT_COMPOSITION_RECIPE_SCHEMA,
            "status": "loaded_and_revalidated",
            "recipe_id": recipe_id,
            **hydrated,
            "recipe": snapshot.record,
            "storage": snapshot.metadata(),
        }
