# Codex provider telemetry integration

Status: the repository-side ingestion seam is executable; a scorer-ready v0.7 trace remains
blocked on two Codex-host counters. This does not authorize an always-on rollout.

## Discovered boundary

Codex Desktop/Core already writes provider-native turn evidence to an explicit rollout JSONL:

- `session_meta`: provider, session identity, host origin, and CLI version;
- `turn_context`: turn identity and model;
- `task_started` / `task_complete`: turn-keyed boundaries and host-recorded duration;
- `token_count`: per-response and cumulative provider token usage;
- `function_call` / `custom_tool_call` plus matching outputs: model-visible tool round trips;
  the authoritative tool name is retained with the call ID.

The TMCP MCP process does not receive these fields. Its `tools/call` boundary receives only the tool
name and arguments, so MCP-side timing or token estimates cannot legitimately replace host metrics.
The current local hook configuration contains command guards and compaction lifecycle hooks, but no
configured post-turn provider telemetry callback. The local logs database and process registry are not
equivalent: neither supplies the complete, turn-keyed v0.7 contract.

## Executable repository seam

`scripts/extract_codex_rollout_metrics.py` reads one explicitly named rollout and one turn ID. It does
not discover sessions or retain prompt, response, reasoning, tool argument, or tool output content. It
extracts and cross-checks:

- `wall_time_ms` from `task_complete.duration_ms`;
- `input_tokens` and `output_tokens` from the sum of provider `last_token_usage` records, checked
  against the cumulative-token delta;
- `model_round_trips` from provider token events;
- `tool_round_trips` from deduplicated call/output pairs;
- `tmcp_model_visible_round_trips` from deduplicated paired calls whose exact authoritative
  name is a public TMCP tool name;
- provider and model identity from host metadata.

Raw `extract_turn()` output without a host observation remains intentionally `status: incomplete`
and `scorer_ready: false` for inspection. The terminal finalization seam and CLI reject a completed
rollout that has no `codex-tmcp-host-observation-v0.1` companion with the explicit
`unavailable-attribution` disposition. It is not accepted by
`score_invocation_admission_rollout.py`, and missing companion evidence is never synthesized as
zero; the two missing counters are the Codex-host-owned skill-read counters.

### Exact TMCP tool-name predicate

The extractor imports `PUBLIC_TOOL_NAMES` from `tmcp_runtime.api.registry`, which is the canonical
public contract built from `tmcp_runtime/api/tool_schemas.py`. The current exact set is:

```text
expert_rubric_review_plan
tmcp_compose_packet
tmcp_doctor
tmcp_evaluate_skills
tmcp_explain
tmcp_harvest_skills
tmcp_promote_harvest
tmcp_recommend_workflows
tmcp_record_receipt
tmcp_runtime_next
tmcp_status
```

The predicate is exact set membership (`tool_name in TMCP_TOOL_NAMES`). CLI aliases, names that merely
contain `tmcp`, shell commands, filenames, prose, timing, and analyst-authored fields are not inputs
to the counter. Identical repeated or cached call/output records collapse by call ID; conflicting
duplicates, malformed names, mismatched output types, unmatched calls, and orphan outputs fail closed.
The extractor retains only call IDs and authoritative names, never tool arguments or output content.

Example:

```sh
python3 scripts/extract_codex_rollout_metrics.py \
  --rollout /absolute/path/to/rollout.jsonl \
  --turn-id replace-with-codex-turn-id
```

Once Codex emits the companion host observation, the adapter can merge it without allowing that file
to override rollout-owned provider, model, timing, token, or tool metrics:

```sh
python3 scripts/extract_codex_rollout_metrics.py \
  --rollout /absolute/path/to/rollout.jsonl \
  --turn-id replace-with-codex-turn-id \
  --host-observation examples/workflows/codex-tmcp-host-observation-v0.1.json
```

## Required host integration

Owner surface: the Codex Desktop/Core experiment coordinator and context assembler, at the same trust
boundary that writes rollout events.

Event timing:

1. Before context assembly, assign the preregistered run/pair ID and randomized policy arm.
2. At admission, record the policy decision and whether normal routing, shadow-only evaluation,
   substitution, or bypass was applied.
3. During context assembly, count actual full-skill reads and their input tokens. Do not infer these
   from shell commands or file names.
4. At the model/tool dispatcher, emit authoritative tool-call names and call IDs in the rollout;
   the repository adapter derives the TMCP-specific round-trip counter from paired records.
5. After `task_complete`, atomically emit `codex-tmcp-host-observation-v0.1`, keyed to the same session
   and turn IDs as the rollout.

The required host-only counters are:

- `skill_read_calls`;
- `skill_read_input_tokens`.

`tmcp_model_visible_round_trips` remains in the v0.1 observation example for backward compatibility.
When present, the merger requires exact equality with the rollout-derived value; when absent, the
rollout-derived value remains authoritative. The observation cannot replace it.

The observation must also carry actual admission and routing state, including
`normal_full_skill_load_count`, `supplemental_full_skill_load_count`, and `packet_injected`, so the
existing scorer can reject supplementation and shadow injection. The merger preserves the normal /
substitution distinction and rejects inconsistent packet-injection state or supplemental full-skill
loads. Human labels and canary arm metadata come from the preregistered experiment coordinator; they
are not provider metrics.

The current repository boundary models Codex Core skill-read evidence as the two required scalar host
counters only. It does not simulate full-skill tokenization or deduplicate host context records.
Structured duplicate, cached, truncated, or invalid skill-read records are rejected as outside this
schema boundary and must be resolved by Codex Core at the context-assembly owner boundary.

Concrete unblock: Codex Desktop/Core must expose a structured post-turn export or add an equivalent
host-owned rollout event with the fields in
`examples/workflows/codex-tmcp-host-observation-v0.1.json`. A repository script, MCP server, shell
timer, command parser, local process registry, or analyst-authored substitute is not sufficient.

## Rollout order

1. Preserve the v0.7 admission and negation-routing work.
2. Add the host-owned observation at the Codex boundary above.
3. Run shadow mode and extract complete traces.
4. Only if every preregistered shadow gate passes, run the randomized paired substitution canary.
5. Keep the behavioral-atoms slice isolated. Its preregistered pilot stopped at preflight because four
   complete skills collapsed into six generic atoms, domain semantics were lost, some skill pairs
   became atom-identical, and proposed transplant contrasts were invalid. No provider outcome cells
   ran, so it supplies no quality or economics evidence for always-on admission.
6. Resume atom research only after domain-preserving typed semantics, semantic-equivalence checks,
   preregistered causal hypotheses, and a valid provider runner exist. Revalidate it independently
   before considering reconciliation with the v0.7 base.
7. Consider always-on admission only after executed provider traces pass; executable machinery alone
   is not rollout evidence.
