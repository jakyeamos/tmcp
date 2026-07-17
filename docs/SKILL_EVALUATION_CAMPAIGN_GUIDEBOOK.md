# Skill-evaluation campaign guidebook

This guidebook turns the first TMCP skill-evaluation campaign into reusable
operating rules. A rule is either an operational default, supported by a
dogfooded run, or a causal claim backed by a separately valid contrast. Do not
turn an operational rule into a corpus-wide recommendation by repetition alone.

## Before a launch

- Pin the source skill, fixtures, observable bars, cost bar, harness files, and
  runner/judge matrix in the plan. Keep the actual first-principles text in an
  immutable input file and bind its path and digest in the run manifest. A hash
  without inspectable source text is not a replayable judge contract.
- Run a remote schema preflight with a synthetic task for every configured runner
  model and the separate judge before any campaign artifact leaves the machine.
  Local JSON-schema validity did not catch the earlier remote `const`/`enum`
  compatibility failure.
- Test baseline reliability before a smaller causal ablation. A positive relative
  lift cannot repair a control that is unreliable on a fixture family.
- Require a directness review for every observable: the event an O/S item grades
  must occur in the fixture prompt, not in an implied later turn. Record an
  independent review that also confirms every bar is expressible by the target
  skill before generating the campaign policy.
- The current planner needs paired original/ablated variants to construct its
  pattern fixtures. A baseline campaign may still execute original rows only;
  verify that the selected 36 cells are original before launch rather than
  weakening the plan contract.

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

## Composition checks

- Test a TMCP composition packet before treating a skill pair as a behavioral
  campaign candidate. The packet must retain the specialized source citations,
  required reads, stop conditions, and verification gates that define the pair.
- Treat pre-action language as negative routing evidence: “before implementing”
  or “stop before implementation” must not activate an implementation route.
  A route-selection probe can catch this cheaply before it contaminates a live
  behavioral campaign.
- Treat test fixtures as evidence-only sources during project-root composition.
  They may support a test or a review, but must not enter active instructions,
  citations, or declared reads unless a future protocol explicitly scopes them.
- Do not activate a specialized route from a generic verb such as “build” alone.
  Preserve a matched specialized control case so a routing fix cannot quietly
  weaken intended frontend or workflow behavior.
- Treat overloaded framework names as context-sensitive route evidence. “React
  components” may activate frontend routing; a user’s “reaction” or instruction
  to “react to” evidence may not.
- A packet-level pass proves only that routing and source projection held. It
  does not prove the pair changes agent behavior; that still requires approved
  golden cases, fresh blind runners, and separate judges.
- For a source-bundle composition contrast, bind both arms to the same packet,
  advisory receipt, task evidence, and base attachment. The treatment attachment
  must be exactly `control + source bundle`; pin the complete bundle plus every
  selected source path and digest in the plan and each trace. This can support
  only a **source-bundle delivery** claim, never an unobserved live-selection,
  adherence, or corpus-quality claim.

## Promotion rules

- Report raw and adjudicated safety/cost verdicts separately. Never rewrite the
  raw judge result after inspecting a result.
- Treat an original-only baseline as a reliability gate, not as an empty causal
  contrast. Its paired-causal score may correctly contain zero cells; report the
  baseline summary from the campaign receipt and keep the causal claim on hold.
- A policy-bound original-only report must expose its actual reliability,
  per-fixture and per-runner coverage, and raw plus condition-blind cost counts.
  Mark causal lift and all causal pattern claims not applicable rather than
  emitting zero-count contrast summaries that look like negative evidence.
- Do not interpret attachment-only activation or adherence heuristics without
  positive telemetry. When the protocol supplies an instruction attachment and
  records only the final artifact, a missing selection signal is
  **non-interpretable**, not evidence that the skill failed to activate or was
  ignored. Use explicit selection telemetry or an independently reviewed label
  before making an activation/adherence claim.
- Treat a same-model reasoning sweep as useful replication across configurations,
  not cross-model evidence. A declared cross-model claim requires distinct
  available model identifiers, complete fixture/repetition coverage per model,
  consistent effect direction, and a judge identifier outside the runner matrix.
  This is a model-identifier proxy, not proof of provider, weights, or training
  data independence.
- A baseline study measures intact-skill reliability only. It is a prerequisite for
  a later causal contrast, never promotion evidence by itself.
- Causal promotion requires the predeclared clustered analysis policy, reliability
  floors, complete provenance, complete cost sidecar where used, and no unresolved
  safety/cost regression. When a plan preregisters `complete_before_promotion`,
  the scorer must hold the claim until the sidecar covers the exact planned trace
  count; documenting the intent alone is insufficient.
- A preregistered cost sidecar is valid only when its launcher and scored payload
  bind back to the exact policy: trace count, model, effort, seed, cost-bar file
  digest, and blinded-process declaration. Do not accept a self-consistent
  rejudge that silently changed any of those inputs.
- Reject a composition trace from controlled analysis when its materialized
  source-bundle provenance differs from the preregistered matrix row. A valid
  runner manifest alone is not enough once a result is exported or reanalyzed.
- Before a source-bundle launch, independently regenerate the plan, compare it
  with the checked-in artifact, validate every input digest (including the
  advisory receipt and first-principles file), and explicitly check that live
  source paths still match their pinned digests. TMCP's source-bundle campaign
  launcher requires the study directory and records this preflight. It proves
  input integrity, not user approval or behavioral lift.

## Anti-patterns observed in the dogfood

- **Execution-only schema validation.** It discovers service compatibility after
  the expensive cells have already started.
- **Post-redaction source binding.** Validating the digest after artifact redaction
  loses the identity it was meant to protect.
- **Unlogged manual capacity recovery.** It erases the distinction between a clean
  run and a resumed transient failure.
- **Judge-bar provenance by hash alone.** It prevents reviewers from checking the
  standard that produced a result, particularly when a safety or cost rule was
  omitted from a summary.
- **Reading an attachment-only diagnostic as behavioral evidence.** A final
  artifact can show the task result without proving selection or adherence;
  absence of telemetry is not a false-negative activation finding.
- **Calling an original-only baseline a zero-cell causal failure.** It is neither
  a causal success nor failure. Its outcome is the preregistered reliability gate.
- **Erasing an invalid rejudge attempt on resume.** Preserve the rejected stage,
  then distinguish the valid replacement cell from a clean first-pass run.
- **Microablating an unreliable baseline.** It gives a sharper causal answer to a
  question whose control behavior is still not dependable.
- **Calling model identifiers independent models.** Identifier replication is
  operationally useful, but it cannot establish provider or training independence.
- **Treating a larger attachment as a pure selection effect.** A packet-plus-bundle
  result measures delivery of that exact pinned material, including any length or
  framing effect; without separate selection telemetry it cannot establish that
  TMCP selected or the runner followed a source independently.

The 2026-07-17 campaign is a source of these operational defaults. Its section
effect remains a held candidate because the historical plan did not preregister the
cluster/reliability contract. The later preregistered intact baseline likewise
holds: it cleared the aggregate floor but missed `claim_calibration` and
`regression_retest` at 2/6 each, and its independent cost sidecar found one
materially unnecessary iterative loop.
