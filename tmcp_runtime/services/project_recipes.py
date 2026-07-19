"""Explicit project-local composition recipe promotion orchestration."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any, Protocol

from tmcp_runtime.domain.composition_planning import compile_semantic_composition
from tmcp_runtime.domain.composition_phase_bindings import (
    PhaseCapsuleBindingError,
    validate_phase_capsule_binding,
)
from tmcp_runtime.domain.composition_declared_dependencies import (
    declared_dependency_closure_is_well_formed,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.composition_runtime_capsules import (
    RuntimeCapsuleError,
    validate_runtime_capsule,
)
from tmcp_runtime.domain.harvest_nodes import content_digest_for, normalized_source_content
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
    try:
        validate_phase_capsule_binding(
            plan.get("phase_capsule_binding"),
            composition_plan=plan,
        )
    except PhaseCapsuleBindingError as exc:
        raise ValueError("Composition plan phase-capsule binding is invalid.") from exc
    try:
        validate_runtime_capsule(
            plan.get("runtime_capsule"), composition_plan=plan
        )
    except RuntimeCapsuleError as exc:
        raise ValueError("Composition plan runtime capsule is invalid.") from exc
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

    projection = {
        "composition_plan_id": str(plan["composition_plan_id"]),
        "graph_digest": _graph_digest(plan),
        "phase_capsule_binding": deepcopy(
            validate_phase_capsule_binding(
                plan.get("phase_capsule_binding"),
                composition_plan=plan,
            )
        ),
        "runtime_capsule": deepcopy(
            validate_runtime_capsule(
                plan.get("runtime_capsule"), composition_plan=plan
            )
        ),
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
    proposal_coverage = plan.get("proposal_coverage")
    if isinstance(proposal_coverage, Mapping):
        projection["proposal_coverage"] = deepcopy(dict(proposal_coverage))
    return projection


def _proposal_coverage_for_rehydrate(
    projection: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Keep the host coverage input distinct from compiler-derived coverage."""

    raw_coverage = projection.get("proposal_coverage")
    if not isinstance(raw_coverage, Mapping):
        raise ValueError(
            "Project recipe lacks immutable proposal coverage; run fresh prepare, "
            "compose, verify, and explicitly re-promote before reactivation."
        )
    values: dict[str, list[str]] = {}
    for field in ("facets", "unresolved_gaps"):
        raw_items = raw_coverage.get(field) or []
        if not isinstance(raw_items, list) or any(
            not isinstance(item, str) for item in raw_items
        ):
            raise ValueError("Project recipe proposal coverage is malformed.")
        values[field] = deepcopy(raw_items)
    return values


def _require_rehydratable_seed_closure(
    projection: Mapping[str, Any],
    hints: Mapping[str, Any],
) -> None:
    """Keep pre-closure reviewed seed recipes readable but safely inert."""

    selected_ids = {
        str(role.get("node_id") or "")
        for role in projection.get("skill_roles", [])
        if isinstance(role, Mapping)
    }
    selected_seed_ids = {
        str(seed.get("id") or "")
        for seed in hints.get("scoped_seeds", [])
        if isinstance(seed, Mapping)
    }.intersection(selected_ids)
    if selected_seed_ids and not declared_dependency_closure_is_well_formed(
        hints.get("declared_dependency_closure")
    ):
        raise ValueError(
            "Project recipe uses legacy scoped-seed metadata without a declared "
            "dependency closure; run fresh prepare, compose, verify, and explicitly "
            "re-promote before reactivation."
        )


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
    phase_capsule_binding = validate_phase_capsule_binding(
        plan.get("phase_capsule_binding"),
        composition_plan=plan,
    )
    eligibility = dict(promotion_eligibility)
    if not isinstance(created_at, str) or not created_at.strip():
        raise ValueError("Project recipe promotion requires created_at.")
    if eligibility.get("eligible") is not True:
        raise ValueError("Only eligible composition recipes may be promoted.")
    if str(eligibility.get("recipe_id") or "") != identifier:
        raise ValueError("Promotion eligibility recipe_id does not match the recipe.")
    if str(eligibility.get("graph_digest") or "") != graph_digest:
        raise ValueError("Promotion eligibility graph_digest does not match the plan.")
    if (
        str(eligibility.get("phase_capsule_binding_digest") or "")
        != phase_capsule_binding["binding_digest"]
    ):
        raise ValueError(
            "Promotion eligibility phase-capsule binding does not match the plan."
        )
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


def _validated_recipe_runtime_capsule(
    record: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Any], dict[str, Any]]:
    """Return the closed stored recipe capsule only when it matches its binding."""

    if record.get("schema") != PROJECT_COMPOSITION_RECIPE_SCHEMA:
        raise ValueError("Project recipe record has an unsupported schema.")
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
    try:
        binding = validate_phase_capsule_binding(projection.get("phase_capsule_binding"))
    except PhaseCapsuleBindingError as exc:
        raise ValueError("Project recipe phase-capsule binding is malformed.") from exc
    if (
        binding["composition_plan_id"] != str(record.get("composition_plan_id") or "")
        or binding["graph_digest"] != str(record.get("graph_digest") or "")
    ):
        raise ValueError("Project recipe phase-capsule binding is stale or malformed.")
    try:
        capsule = validate_runtime_capsule(projection.get("runtime_capsule"))
    except RuntimeCapsuleError as exc:
        raise ValueError("Project recipe runtime capsule is malformed.") from exc
    if any(
        capsule[capsule_field] != binding[binding_field]
        for capsule_field, binding_field in (
            ("composition_plan_id", "composition_plan_id"),
            ("composition_plan_digest", "composition_plan_digest"),
            ("preflight_id", "preflight_id"),
            ("compiler_phase", "compiler_phase"),
            ("graph_digest", "graph_digest"),
            ("phase_capsule_binding_digest", "binding_digest"),
        )
    ):
        raise ValueError("Project recipe runtime capsule is stale or malformed.")
    return projection, binding, capsule


def _fresh_slice_matches_descriptor(
    source_slice: Mapping[str, Any], descriptor: Mapping[str, Any]
) -> bool:
    """Match fresh evidence to a closed capsule descriptor, never its locator."""

    content = source_slice.get("content")
    if not isinstance(content, str) or not normalized_source_content(content):
        return False
    if content_digest_for(content) != descriptor["slice_digest"]:
        return False
    atoms = source_slice.get("behavior_atoms")
    if not isinstance(atoms, list) or atoms != descriptor["behavior_atoms"]:
        return False
    return all(
        source_slice.get(field) == descriptor[field]
        for field in (
            "source_role",
            "source_digest",
            "slice_digest",
            "char_start",
            "char_end",
            "relative_path",
        )
    )


def _fresh_alias_source_is_consistent(
    source_slice: Mapping[str, Any], descriptor: Mapping[str, Any]
) -> bool:
    """Allow other chunks only when they belong to the same closed source."""

    content = source_slice.get("content")
    atoms = source_slice.get("behavior_atoms")
    if (
        not isinstance(content, str)
        or not normalized_source_content(content)
        or content_digest_for(content) != source_slice.get("slice_digest")
        or not isinstance(atoms, list)
    ):
        return False
    return all(
        source_slice.get(field) == descriptor[field]
        for field in ("source_role", "source_digest", "relative_path", "behavior_atoms")
    )


def _replay_preflight_with_recipe_aliases(
    preflight: Mapping[str, Any], runtime_capsule: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Restore original node and slice identities for one content-bound rename.

    A reviewed recipe owns graph node identifiers, while a fresh harvest may
    assign new locators after a checkout or root relocation.  The closed
    runtime capsule supplies the only permitted alias evidence.  We fail closed
    for duplicate candidates, changed content, or a fresh source that would
    collide with a different original graph node.
    """

    raw_slices = preflight.get("candidate_source_slices")
    if not isinstance(raw_slices, list) or any(
        not isinstance(item, Mapping) for item in raw_slices
    ):
        raise ValueError("Project recipe current source slices are malformed.")
    fresh_slices = [dict(item) for item in raw_slices]
    aliases: list[dict[str, str]] = []
    alias_by_fresh_id: dict[str, str] = {}
    descriptor_by_fresh_id: dict[str, Mapping[str, Any]] = {}
    owners_by_fresh_id: dict[str, str] = {}

    for descriptor in runtime_capsule["cited_source_slices"]:
        matches = [
            source_slice
            for source_slice in fresh_slices
            if _fresh_slice_matches_descriptor(source_slice, descriptor)
        ]
        original_node_id = str(descriptor["original_node_id"])
        exact = [
            source_slice
            for source_slice in matches
            if str(source_slice.get("source_node_id") or "") == original_node_id
        ]
        if len(exact) == 1:
            match = exact[0]
        elif len(exact) > 1 or len(matches) > 1:
            raise ValueError("Project recipe cited source aliases are ambiguous.")
        elif not matches:
            raise ValueError("Project recipe is stale for current cited source slices.")
        else:
            match = matches[0]
        fresh_node_id = str(match.get("source_node_id") or "").strip()
        if not fresh_node_id:
            raise ValueError("Project recipe current source slices are malformed.")
        previous_owner = owners_by_fresh_id.get(fresh_node_id)
        if previous_owner is not None and previous_owner != original_node_id:
            raise ValueError("Project recipe cited source aliases are ambiguous.")
        owners_by_fresh_id[fresh_node_id] = original_node_id
        if fresh_node_id != original_node_id:
            alias_by_fresh_id[fresh_node_id] = original_node_id
            descriptor_by_fresh_id.setdefault(fresh_node_id, descriptor)

    for fresh_node_id, original_node_id in alias_by_fresh_id.items():
        descriptor = descriptor_by_fresh_id[fresh_node_id]
        for source_slice in fresh_slices:
            node_id = str(source_slice.get("source_node_id") or "").strip()
            if node_id == fresh_node_id and not _fresh_alias_source_is_consistent(
                source_slice, descriptor
            ):
                raise ValueError("Project recipe is stale for current cited source slices.")
            if node_id == original_node_id:
                raise ValueError("Project recipe cited source aliases are ambiguous.")
        aliases.append(
            {"from_node_id": fresh_node_id, "to_node_id": original_node_id}
        )

    replay = deepcopy(dict(preflight))
    replay_slices = replay.get("candidate_source_slices")
    if not isinstance(replay_slices, list):
        raise ValueError("Project recipe current source slices are malformed.")
    for source_slice in replay_slices:
        if not isinstance(source_slice, dict):
            raise ValueError("Project recipe current source slices are malformed.")
        original_node_id = alias_by_fresh_id.get(
            str(source_slice.get("source_node_id") or "").strip()
        )
        if not original_node_id:
            continue
        source_slice["source_node_id"] = original_node_id
        source_slice["slice_id"] = "slice-" + stable_digest(
            [
                source_slice.get("source_digest"),
                source_slice.get("slice_digest"),
                source_slice.get("char_start"),
                source_slice.get("char_end"),
                original_node_id,
            ],
            20,
        )
    return replay, sorted(
        aliases, key=lambda item: (item["from_node_id"], item["to_node_id"])
    )


def _binding_identity_matches(
    current: Mapping[str, Any], stored: Mapping[str, Any]
) -> bool:
    """Compare compiler-owned identity, excluding location-derived accounting."""

    return all(
        current.get(field) == stored.get(field)
        for field in (
            "composition_plan_id",
            "composition_plan_digest",
            "preflight_id",
            "compiler_phase",
            "graph_digest",
            "recipe_digest",
        )
    )


def _runtime_capsule_identity_matches(
    current: Mapping[str, Any], stored: Mapping[str, Any]
) -> bool:
    """Preserve the source-bound capsule while allowing aliased accounting."""

    return all(
        current.get(field) == stored.get(field)
        for field in (
            "composition_plan_id",
            "composition_plan_digest",
            "preflight_id",
            "compiler_phase",
            "graph_digest",
            "objective_digest",
            "task_identity_digest",
            "preparation_controls",
            "preparation_controls_digest",
            "cited_source_slices",
        )
    )


def rehydrate_project_recipe_for_preflight(
    record: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    current_phase: str | None = None,
) -> dict[str, Any]:
    """Revalidate a stored recipe against current source slices and graph identity."""

    if preflight.get("schema") != "tmcp-composition-preflight-v0.1":
        raise ValueError(
            "Project recipe load requires a current composition preflight."
        )
    projection, stored_phase_capsule_binding, stored_runtime_capsule = (
        _validated_recipe_runtime_capsule(record)
    )
    stored_handoff_contracts = projection.get("handoff_contracts")
    preflight_id = str(preflight.get("preflight_id") or "").strip()
    if not preflight_id:
        raise ValueError("Project recipe load requires current preflight identity.")
    compiler_phase = str(stored_runtime_capsule["compiler_phase"])
    replay_preflight, source_aliases = _replay_preflight_with_recipe_aliases(
        preflight,
        stored_runtime_capsule,
    )
    stored_seed_hints = projection.get("scoped_seed_graph_hints")
    if not isinstance(stored_seed_hints, Mapping):
        raise ValueError("Project recipe scoped seed graph hints are malformed.")
    _require_rehydratable_seed_closure(projection, stored_seed_hints)
    # Scoped seed IDs and their source-backed citation locators are graph
    # inputs. Reuse the reviewed projection after restoring the original slice
    # IDs above; fresh harvest metadata is evidence, never an opportunity to
    # alter seed transitions, receipts, or routing affinity during rehydrate.
    replay_preflight["scoped_seed_graph_hints"] = deepcopy(dict(stored_seed_hints))
    proposal_coverage = _proposal_coverage_for_rehydrate(projection)
    proposal = {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": preflight_id,
        # Revalidate at the capsule's immutable compiler phase. A later runtime
        # phase is evidence-driven state and must be advanced by the runtime
        # gate evaluator, not used to manufacture a new reviewed binding.
        "current_phase": compiler_phase,
        "task_model": deepcopy(dict(projection["task_model"])),
        "skill_roles": deepcopy(list(projection["skill_roles"])),
        "relationships": deepcopy(list(projection["typed_edges"])),
        "coverage": proposal_coverage,
        "trust": "advisory_untrusted",
    }
    compiled = compile_semantic_composition(
        proposal,
        replay_preflight,
        current_phase=compiler_phase,
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
    try:
        current_phase_capsule_binding = validate_phase_capsule_binding(
            plan.get("phase_capsule_binding"),
            composition_plan=plan,
        )
    except PhaseCapsuleBindingError as exc:
        raise ValueError("Project recipe did not compile a valid phase binding.") from exc
    if not _binding_identity_matches(
        current_phase_capsule_binding, stored_phase_capsule_binding
    ):
        raise ValueError("Project recipe phase-capsule binding is stale or malformed.")
    try:
        current_runtime_capsule = validate_runtime_capsule(
            plan.get("runtime_capsule"), composition_plan=plan
        )
    except RuntimeCapsuleError as exc:
        raise ValueError("Project recipe did not compile a valid runtime capsule.") from exc
    if not _runtime_capsule_identity_matches(
        current_runtime_capsule, stored_runtime_capsule
    ):
        raise ValueError("Project recipe runtime capsule is stale or malformed.")
    return {
        "semantic_proposal": proposal,
        "composition_plan": deepcopy(dict(plan)),
        "composition_preflight": replay_preflight,
        "compiler_phase": compiler_phase,
        "requested_runtime_phase": str(current_phase or "").strip(),
        "aliases": source_aliases,
        "source_aliases": source_aliases,
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
        phase_capsule_binding = validate_phase_capsule_binding(
            plan.get("phase_capsule_binding"),
            composition_plan=plan,
        )
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
            phase_capsule_binding=phase_capsule_binding,
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

    def load_runtime_capsule(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Read one explicit recipe's validated controls before current preflight."""

        recipe_id = _recipe_id(arguments.get("recipe_id"))
        store = self._open_store(
            _project_path(arguments.get("project_path")), recipe_id
        )
        snapshot = store.load_record()
        _projection, _binding, capsule = _validated_recipe_runtime_capsule(
            snapshot.record
        )
        return deepcopy(capsule)

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
