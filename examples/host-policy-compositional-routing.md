# Host Policy: Compositional Routing

Use this experimental host policy behind natural-language prompting. Users
should experience one task flow: describe the work and receive the agent's
progress and outcome. They should not need to request TMCP, select skills, or
manage compiler passes.

```text
if request is trivial conversation or a simple status reply:
    answer directly
elif request is multi-step, tool-using, high-stakes, or skill-relevant:
    packet = host_compose_task(objective, scope, phase, runtime_context,
                               cache_policy="none")
    if packet.composition_plan is valid:
        agent executes packet.composition_plan active stage
        agent does not advance past unmet entry, exit, or verification gates
    else:
        host resolves the internal composition diagnostics; rejected elements
        stay inactive
```

## Host-only compiler details

`host_compose_task` is host-local orchestration, not another TMCP user-facing
tool. Internally it obtains bounded candidate evidence with
`tmcp_prepare_composition`, makes a cited `tmcp-semantic-proposal-v0.1`, and
passes it to `tmcp_compose_packet`. TMCP validates provenance, precedence,
cycles, and conflicts before emitting the plan. Keep those protocol hops inside
the host; they are not a sequence for users to perform.

Call `tmcp_runtime_next` with new reads, commands, failures, browser evidence,
verification results, or user redirects. Request a full recompile when the
skill graph, stage, gates, or obligations may change.

The host proposes semantics; TMCP validates and compiles; the agent executes.
Supporting references and evidence-only sources never become instructions. Use
`cache_policy=project` only for reviewed project-local recipes, and keep
promotion as a separate explicit action. Direct compose without a semantic
proposal remains the compatibility fallback when assisted composition is not
available.
