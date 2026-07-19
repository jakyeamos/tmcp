# Host Policy: Compositional Routing

Use this experimental host policy behind natural-language prompting. Users
should experience one task flow: describe the work and receive the agent's
progress and outcome. They should not need to request TMCP, select skills, or
manage compiler passes.

```text
if request is trivial conversation or a simple status reply:
    answer directly
elif request is multi-step, tool-using, high-stakes, or skill-relevant:
    intake = prepare_host_composition(objective, scope, phase, runtime_context,
                                      cache_policy="none")
    proposal = host_propose_semantics(intake.host_input())
    packet = compose_host_composition(intake, proposal)
    if packet.composition_plan is valid:
        agent executes packet.composition_plan active stage
        agent does not advance past unmet entry, exit, or verification gates
    else:
        host repairs the internal composition diagnostics; rejected elements
        stay inactive and the host never silently downgrades to legacy compose
```

## Host-only compiler details

`host_compose_task` is host-local orchestration, not another TMCP user-facing
tool. Internally it obtains bounded candidate evidence with
`tmcp_prepare_composition`, makes a cited `tmcp-semantic-proposal-v0.1`, and
passes it to `tmcp_compose_packet`. TMCP validates provenance, precedence,
cycles, and conflicts before emitting the plan. Keep those protocol hops inside
the host; they are not a sequence for users to perform.

For an in-process host with already-harvested source nodes, use
`tmcp_runtime.services.host_composition.prepare_host_composition` followed by
`compose_host_composition`. The intake freezes the exact cache-free arguments,
source snapshot, and preflight before the host sees bounded slices. Its
`host_input()` method exposes only that bounded preflight; composition rejects
any changed intake snapshot. The host's semantic callback belongs between the
two calls. The adapter never invokes tools, writes receipts, advances stages,
or promotes recipes.

Call `tmcp_runtime_next` with new reads, commands, failures, browser evidence,
verification results, or user redirects. Request a full recompile when the
skill graph, stage, gates, or obligations may change.

The host proposes semantics; TMCP validates and compiles; the agent executes.
Supporting references and evidence-only sources never become instructions. Use
`cache_policy=project` only for reviewed project-local recipes, and keep
promotion as a separate explicit action. Direct compose without a semantic
proposal is allowed only when assisted composition is unavailable, and the host
must mark that result as compatibility mode. `tmcp_explain --compose` is an
inspection/compatibility packet, not the substantial-task fallback because it
cannot carry a host semantic proposal.
