# Skill-evaluation campaign guidebook

This guidebook turns the first TMCP skill-evaluation campaign into reusable
operating rules. A rule is either an operational default, supported by a
dogfooded run, or a causal claim backed by a separately valid contrast. Do not
turn an operational rule into a corpus-wide recommendation by repetition alone.

## Before a launch

- Pin the source skill, fixtures, observable bars, cost bar, harness files, and
  runner/judge matrix in the plan. A plan that names only three reasoning efforts
  is a one-model configuration sweep, not independent-model confirmation.
- Run a remote schema preflight with a synthetic task before any campaign artifact
  leaves the machine. Local JSON-schema validity did not catch the earlier remote
  `const`/`enum` compatibility failure.
- Test baseline reliability before a smaller causal ablation. A positive relative
  lift cannot repair a control that is unreliable on a fixture family.
- Require a directness review for every observable: the event an O/S item grades
  must occur in the fixture prompt, not in an implied later turn.

## During a launch

- Give every runner and judge a fresh, isolated thread. Persist event streams,
  output digests, usage, and schema digests with the cell.
- Fail closed on malformed output or an incomplete stage. Archive it rather than
  treating a partial artifact as resumable.
- Retry only bounded, classified transient failures (capacity, rate limit,
  temporary service/network failure). Preserve every failed attempt and its
  backoff in a retry audit; contract failures are not retryable.
- Keep source artifacts immutable. A blind sidecar may adjudicate a narrow concern
  such as cost, but it must cover every trace and bind each source digest.

## Promotion rules

- Report raw and adjudicated safety/cost verdicts separately. Never rewrite the
  raw judge result after inspecting a result.
- Treat a same-model reasoning sweep as useful replication across configurations,
  not cross-model evidence. A declared cross-model claim requires independent
  runner models, complete fixture/repetition coverage per model, consistent effect
  direction, and a judge model outside the runner matrix.
- A baseline study measures intact-skill reliability only. It is a prerequisite for
  a later causal contrast, never promotion evidence by itself.
- Causal promotion requires the predeclared clustered analysis policy, reliability
  floors, complete provenance, complete cost sidecar where used, and no unresolved
  safety/cost regression.

## Anti-patterns observed in the dogfood

- **Execution-only schema validation.** It discovers service compatibility after
  the expensive cells have already started.
- **Post-redaction source binding.** Validating the digest after artifact redaction
  loses the identity it was meant to protect.
- **Unlogged manual capacity recovery.** It erases the distinction between a clean
  run and a resumed transient failure.
- **Microablating an unreliable baseline.** It gives a sharper causal answer to a
  question whose control behavior is still not dependable.
- **Calling configurations independent models.** Configuration replication and
  model replication answer different generalization questions.

The 2026-07-17 campaign is a source of these operational defaults. Its section
effect remains a held candidate because the historical plan did not preregister the
cluster/reliability contract and the intact control missed two fixture families.
