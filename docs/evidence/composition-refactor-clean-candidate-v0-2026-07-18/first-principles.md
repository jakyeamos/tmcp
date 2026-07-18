# Refactor-clean first principles for fixture review

Source: `/Users/jakyeamos/skills/engineering/refactor-clean/SKILL.md` at
`sha256:90709ad4daf33b34ded487de2a5e666e130969c1abb431306efc20d3388000d0`.

This is a reviewer-facing summary, not a replacement source bundle. Any later
campaign must pin and archive the full source text it supplies to runners.

The skill asks an agent to replace a sedimented shape with the simpler shape the
codebase would want if designed today. Its central standard is one concept owner
with clear consumers, rather than a parallel compatibility layer beside the
problem.

A sound refactor plan should:

- identify the duplicated concept, every current owner, and every affected
  consumer before proposing new machinery;
- choose the natural home for the concept, then route old call sites to it;
- delete or collapse stale paths in the same change when feasible, allowing a
  bridge only at an external boundary or as a named, short-lived migration seam
  with a removal condition; and
- verify behavior through consumer surfaces that use the owner, rather than only
  through a new owner module or a second, drifting re-derivation.

The skill also rejects sunk-cost reasoning, dev-only compatibility by default,
and placeholder evidence that masks the relevant behavior. When the graph does
not establish a consumer or external boundary, a plan must preserve that
uncertainty rather than inventing ownership facts.
