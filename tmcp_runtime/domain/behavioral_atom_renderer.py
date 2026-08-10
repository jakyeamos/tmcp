"""Rendering boundary for compiled behavioral atoms."""

from __future__ import annotations

from tmcp_runtime.domain.behavioral_atom_types import (
    CompileResult,
    RenderRecord,
    TypedAtom,
    _unique,
)


def render_atoms(
    result: CompileResult,
    *,
    target: str = "packet",
    token_budget: int | None = None,
) -> CompileResult:
    """Render selected internal records into only an approved string boundary."""

    if target not in {"packet", "receipt", "advisory_trace"}:
        raise ValueError(f"Forbidden typed atom rendering target: {target}")
    budget = result.token_budget if token_budget is None else max(0, int(token_budget))
    records: list[RenderRecord] = []
    used = 0
    stops = list(result.stops)
    selected: list[TypedAtom] = []
    for atom in result.selected:
        if target not in atom.rendering_boundary.renderable_to:
            raise ValueError(
                f"Typed atom {atom.full_id} cannot render to target: {target}"
            )
        cost = atom.estimated_token_cost.maximum
        if used + cost > budget:
            stops.append("budget.rendered_atoms_exceed_budget")
            break
        selected.append(atom)
        used += cost
        records.append(
            RenderRecord(
                atom_id=atom.full_id,
                target=target,
                text=atom.full_id,
                token_cost=cost,
            )
        )
    if len(selected) != len(result.selected):
        return CompileResult(
            schema=result.schema,
            version=result.version,
            decision="hold_for_evidence",
            status="blocked",
            selected=tuple(selected),
            applicability=result.applicability,
            stops=_unique(stops),
            missing=_unique((*result.missing, "render-token-budget")),
            legacy_projection=result.legacy_projection,
            total_token_cost=used,
            token_budget=budget,
            render_records=tuple(records),
            deferred=result.deferred,
        )
    return CompileResult(
        schema=result.schema,
        version=result.version,
        decision=result.decision,
        status=result.status,
        selected=tuple(selected),
        applicability=result.applicability,
        stops=result.stops,
        missing=result.missing,
        legacy_projection=result.legacy_projection,
        total_token_cost=used,
        token_budget=budget,
        render_records=tuple(records),
        deferred=result.deferred,
    )


__all__ = ["render_atoms"]
