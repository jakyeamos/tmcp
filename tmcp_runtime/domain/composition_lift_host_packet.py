"""Project an external lift-runner packet from a semantic composition plan.

The live compiler keeps deferred skill bodies out of the active packet.  The
host/evaluator campaign is deliberately outside the runtime, so it needs a
small, deterministic projection that preserves that same boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _text(value: object) -> str:
    return str(value or "").strip()


def source_node_ids_by_skill_id(
    plan: Mapping[str, object],
    skill_ids: Sequence[str],
    source_paths: Mapping[str, str],
) -> dict[str, str]:
    """Resolve fixture skill IDs to semantic-plan source node IDs.

    Fixture sources identify a skill by its relative path while composition
    plans identify the same source by a harvested node ID.  The runtime capsule
    is the content-bound bridge between those identities.  Direct matches are
    accepted for compact test/control plans; unresolved skills are omitted so a
    campaign cannot accidentally hydrate an unrelated source body.
    """

    capsule = _mapping(plan.get("runtime_capsule"))
    cited_slices = capsule.get("cited_source_slices") if capsule else None
    node_by_path: dict[str, str] = {}
    if isinstance(cited_slices, Sequence) and not isinstance(
        cited_slices, (str, bytes)
    ):
        for raw_slice in cited_slices:
            source_slice = _mapping(raw_slice)
            if source_slice is None:
                continue
            path = _text(source_slice.get("relative_path"))
            node_id = _text(source_slice.get("original_node_id"))
            if path and node_id:
                node_by_path[path] = node_id

    role_nodes: set[str] = set()
    raw_roles = plan.get("skill_roles")
    if isinstance(raw_roles, Sequence) and not isinstance(raw_roles, (str, bytes)):
        for raw_role in raw_roles:
            role = _mapping(raw_role)
            if role is not None:
                node_id = _text(role.get("node_id"))
                if node_id:
                    role_nodes.add(node_id)

    result: dict[str, str] = {}
    for skill_id in skill_ids:
        normalized_skill_id = _text(skill_id)
        if not normalized_skill_id:
            continue
        path = _text(source_paths.get(normalized_skill_id))
        node_id = node_by_path.get(path, "") if path else ""
        if not node_id and normalized_skill_id in role_nodes:
            node_id = normalized_skill_id
        if node_id:
            result[normalized_skill_id] = node_id
    return result


def project_external_skill_ids(
    plan: Mapping[str, object],
    ordered_skill_ids: Sequence[str],
    source_paths: Mapping[str, str],
    *,
    variant_id: str,
) -> tuple[list[str], list[str]]:
    """Return hydrated and deferred skill IDs for one campaign arm.

    ``naive_union`` intentionally retains every participating source body as
    its control condition.  Every semantic arm hydrates only active or
    governing roles; selected deferred roles remain visible through the bridge
    recipe but their bodies are not supplied to the host.
    """

    ordered = list(
        dict.fromkeys(_text(item) for item in ordered_skill_ids if _text(item))
    )
    if variant_id == "naive_union":
        return sorted(ordered), []

    node_by_skill = source_node_ids_by_skill_id(plan, ordered, source_paths)
    active_nodes: set[str] = set()
    raw_roles = plan.get("skill_roles")
    if isinstance(raw_roles, Sequence) and not isinstance(raw_roles, (str, bytes)):
        for raw_role in raw_roles:
            role = _mapping(raw_role)
            if role is None:
                continue
            activation = _text(role.get("activation"))
            source_role = _text(role.get("source_role"))
            node_id = _text(role.get("node_id"))
            if node_id and (
                activation == "active" or source_role == "governing_instruction"
            ):
                active_nodes.add(node_id)

    hydrated = [
        skill_id for skill_id in ordered if node_by_skill.get(skill_id) in active_nodes
    ]
    deferred = [skill_id for skill_id in ordered if skill_id not in hydrated]
    return hydrated, deferred
