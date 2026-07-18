# Candidate skill campaign ledger

This is an evidence-aware intake ledger, not a launch order or a recommendation
to change skills. Read it with the promotion state in
[`docs/SKILL_WRITING_GUIDEBOOK.md`](../../SKILL_WRITING_GUIDEBOOK.md): every
current guidebook entry remains on hold. A row may identify the next admissible
research step, but cannot authorize a corpus rewrite or a behavioral claim.

The labels below are deliberately narrow:

- **evaluated, held** — a completed campaign exists, but it did not clear its
  promotion gates;
- **preregistered** — reviewed inputs and policy exist; no behavioral calls have
  been made;
- **packet-probed** — TMCP locally preserved a source/route contract only;
- **selection-only** — a source appeared in a local packet, but its important
  behavioral rule has not yet cleared the packet probe; and
- **candidate** — an inventory or static-review lead with no composition
  evidence.

| Target | State | Behavioral strength to test | Next admissible step |
| --- | --- | --- | --- |
| `/Users/jakyeamos/skills/authoring/eval-skills/SKILL.md` | Evaluated, held | Blind evaluation, defect-vs-bar diagnosis, full re-evaluation | Keep the completed baseline as a negative reliability gate; any v3 revision needs a separately reviewed campaign. |
| `/Users/jakyeamos/skills/engineering/explore-unknowns/SKILL.md` | Preregistered, causal launch blocked on baseline receipt | Stage-1 settled-ground opening, explicit assumptions, and user handoff | First produce and independently verify a compatible original-only baseline receipt that clears its floors; only then obtain fresh approval for the 72 runner and 72 primary-judge calls. |
| `/Users/jakyeamos/skills/engineering/refactor-clean/SKILL.md` | Preregistration-ready; no behavioral calls | One owner, stale-path removal, consumer verification | Create a separately preregistered behavioral plan from the six reviewed fixtures and obtain approval before any model call. |
| `/Users/jakyeamos/skills/engineering/write-docs/SKILL.md` | Packet-probed | Source-grounded documentation without code transcription | Independently review a real source-tree fixture and observable audience bar before deciding whether a behavioral plan is warranted. |
| `/Users/jakyeamos/.agents/skills/repo-behavior-spec-loop/SKILL.md` | Packet-probed | Canonical evidence state, source citations, audit checkpoints | Independently review audit-only and remediation-permitted fixtures before any behavioral plan. |
| `/Users/jakyeamos/.agents/skills/wizard/SKILL.md` | Packet-probed | Deterministic human handoff with secret/irreversibility safety | Independently review synthetic, no-write fixtures and a safety bar before deciding whether a behavioral study is warranted; never use a live secret or external account. |
| `/Users/jakyeamos/.codex/skills/fold-feature-branches/SKILL.md` | Packet-probed | Lossless branch integration, remote truth, and safe supersession | Independently review a synthetic repository fixture and a safety bar before deciding whether a behavioral study is warranted; never mutate a user branch during the probe. |
| `/Users/jakyeamos/.agents/skills/opencli-autofix/SKILL.md` | Packet-probed | Hard-stop repair, authoritative-file scope, retry budget, and issue approval | Independently review synthetic diagnostic fixtures and a safety bar before deciding whether a behavioral study is warranted; never run OpenCLI, modify an adapter, or file an issue during the probe. |

## Composition evidence and next gates

The local results in
[`tmcp-combination-probes.md`](tmcp-combination-probes.md) establish only packet
projection. They are not an ordering of live campaigns and do not measure an
agent artifact. The currently bounded composition work is:

| Composition surface | Evidence state | Exact claim boundary | Next gate |
| --- | --- | --- | --- |
| TMCP packet + `explore-unknowns` Stage-1 bundle | Preregistered, causal launch blocked on baseline receipt and bundle verification | `composition-study-efc0a2e36fb15c92` can test the delivery effect of the byte-pinned source bundle against the same packet. It does not test TMCP live selection, source adherence, or corpus quality. | Use `composition-explore-unknowns-v1-2026-07-17/baseline-launch.md` for the approval-gated 36-cell baseline; then independently verify its receipt and bundle-verification record before requesting the 72 runner/judge calls and separate cost rejudge. |
| TMCP compiler + `refactor-clean` | Preregistration-ready; no behavioral calls | The local packet preserves a consumer-surface verification gate and the exact source bundle is archived; ownership behavior and the stale-path outcome remain untested. | Create a separately preregistered behavioral plan from the six reviewed fixtures, then obtain approval before any model call. |
| TMCP compiler + `repo-behavior-spec-loop` | Packet-probed | The packet retained the canonical-ledger and audit-stop contract; no artifact outcome was measured. | Separate reviewed fixture set and preregistered behavioral plan. |
| TMCP compiler + `write-docs` | Packet-probed | The documentation source is cited for a source-grounded objective while generic implementation evidence does not activate frontend behavior. No documentation artifact outcome was measured. | Independently review a source-tree fixture and observable audience bar before any behavioral plan. |
| TMCP compiler + `wizard` | Packet-probed | The packet preserves irreversible-action confirmation and static-only wizard verification. No secret, external account, or wizard artifact was used. | Independently reviewed synthetic no-write fixtures, a safety bar, and a preregistered behavioral plan. |
| TMCP compiler + `fold-feature-branches` | Packet-probed | The packet preserves dirty/ambiguous branch protection plus remote-head and ancestry/patch-equivalence proof gates. No branch was fetched, merged, deleted, or changed. | Independently reviewed synthetic repository fixtures, a safety bar, and a preregistered behavioral plan. |
| TMCP compiler + `opencli-autofix` | Packet-probed | The rendered packet preserves hard-stop codes, adapter-only scope, retry budget, and issue-filing approval without activating UI checks from `BROWSER_CONNECT`. No OpenCLI command, adapter, or GitHub issue was touched. | Independently reviewed synthetic diagnostic fixtures, a safety bar, and a preregistered behavioral plan. |

Do not compare or rank these rows as if they shared an outcome measure. A pair
first needs a scoped packet contract, independently reviewed fixtures, runner and
judge isolation, repetitions, and a cost or safety bar where the task warrants
one. Even then, a result may support only the intervention specified in its plan;
it never promotes a pair to a corpus default from static or packet-level evidence.
