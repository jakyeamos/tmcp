# Invocation admission rollout

TMCP's broad-invocation candidate is **always-on host-side admission**, not
always-on packet injection. The v0.7 rollout has two sequential phases:

1. Shadow admission records what TMCP would do while exposing no TMCP packet to
   the model.
2. A randomized paired canary compares normal Codex routing with TMCP-admitted
   substitution. On accepted tasks, the packet replaces normal full-skill
   loading. On bypassed tasks, normal Codex routing proceeds unchanged.

The preregistered machine-readable contract is
`examples/workflows/invocation-admission-rollout-v0.7.json`. Atom-level packet
composition is excluded; it may enter a later canary only after independent
validation.

## Required host evidence

Write one JSON object per line. Every trace must identify `run_id`, `task_id`,
`stratum`, `human_expected_action`, `human_label_blinded`,
`review_or_audit_task`, `trace_source: "codex-host"`, provider, model, and
`fresh_context: true`.

The `provider_metrics` object must contain exact host measurements for:

- wall time;
- input and output tokens;
- model and tool round trips;
- skill-read calls and their input tokens; and
- model-visible TMCP round trips.

Packet characters and self-reported timing are not accepted as substitutes.
Shadow traces must use `admission.mode: "shadow"`, inject no packet, and report
the automatic `recommended_action`.

Canary traces also include `pair_id`, `pair_order`, and `arm`. The baseline arm
is `normal-codex-routing`. The experimental arm is
`tmcp-admitted-substitution`; composed runs require `routing.mode:
"substitution"` with zero normal or supplemental full-skill loads. Bypassed
runs require `routing.mode: "normal_after_bypass"`.

Canary judgments are a separate JSONL corpus containing exactly:
`run_id`, `judge_blinded`, `pass`, `weighted_score`,
`verification_quality_score`, `irrelevant_constraint_count`, and
`unsafe_or_unjustified_action_count`.

## Score the rollout

Before shadow scoring, aggregate one redacted v0.11 attribution-availability receipt per attempted
turn:

```bash
python3 scripts/score_invocation_admission_rollout.py readiness \
  --traces /absolute/path/attribution-availability.jsonl \
  --output /absolute/path/attribution-readiness-report.json
```

The readiness report classifies `complete-zero`, `complete-exact`, and `unavailable` outcomes. Any
unavailable turn blocks `shadow_score_eligible`. Even 100% coverage leaves `promotion_authorized`
and `canary_authorized` false: the existing v0.7 shadow scorer must still validate complete provider
traces, and a passed shadow remains the prerequisite for canary scoring. Availability receipts do
not change the v0.7 preregistration or its required-provider-metrics contract.

```bash
python3 scripts/score_invocation_admission_rollout.py shadow \
  --traces /absolute/path/shadow-traces.jsonl \
  --output /absolute/path/shadow-report.json

python3 scripts/score_invocation_admission_rollout.py canary \
  --traces /absolute/path/canary-traces.jsonl \
  --judgments /absolute/path/canary-judgments.jsonl \
  --shadow-report /absolute/path/shadow-report.json \
  --output /absolute/path/canary-report.json
```

The scorer fails closed on incomplete provider metrics, unblinded labels or
judgments, mismatched pairs, provider/model drift within a pair, additive TMCP
routing, packet injection during shadowing, a model-visible TMCP round trip, or
an absent/failed shadow prerequisite. Promotion additionally requires quality,
safety, routing precision, audit leakage, irrelevant constraints, wall time,
tokens, model/tool round trips, and skill-read economics to pass together.
