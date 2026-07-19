# Host Policy: Compositional Routing

Use this experimental host policy behind natural-language prompting. Users
should experience one task flow: describe the work and receive the agent's
progress and outcome. They should not need to request TMCP, select skills, or
manage compiler passes.

```text
if request is trivial conversation or a simple status reply:
    answer directly
elif request is multi-step, tool-using, high-stakes, or skill-relevant:
    packet = run_host_composition(
        arguments,
        source_nodes=harvested_source_nodes,
        propose_semantics=host_propose_semantics,
    )
    if packet.composition_plan is valid:
        agent executes packet.composition_plan active stage
        agent does not advance past unmet entry, exit, or verification gates
    else:
        host repairs the internal composition diagnostics; rejected elements
        stay inactive and the host never silently downgrades to legacy compose
```

## Host-only compiler details

`run_host_composition` is native host-local orchestration, not another TMCP
user-facing tool. For an in-process host that has already harvested source
nodes, call
`tmcp_runtime.services.host_composition.run_host_composition(arguments,
source_nodes=harvested_source_nodes, propose_semantics=host_propose_semantics)`.
The runner prepares once from that exact cache-free source snapshot, calls
`host_propose_semantics(intake.host_input())` with only the bounded preflight,
then validates and composes the proposal against the same frozen intake. TMCP
validates provenance, precedence, cycles, and conflicts before emitting the
plan. Keep those protocol hops inside the host; they are not a sequence for
users to perform.

The native runner never invokes tools, writes receipts, advances stages, or
promotes recipes. `prepare_host_composition(arguments,
source_nodes=...)` and `compose_host_composition(intake, proposal)` remain
available only when a native host needs to own the callback boundary itself;
their exact signatures take the arguments mapping and a keyword-only source
snapshot, not separate positional objective/scope/phase values.

Public MCP and CLI integrations use the portable compatibility flow instead:
call `tmcp_prepare_composition`, have the host build a cited
`tmcp-semantic-proposal-v0.1`, then call `tmcp_compose_packet` with that
proposal. Those are separate public calls, so they cannot preserve a native
in-memory frozen source snapshot across the boundary; compose re-harvests and
validates its current input. Do not describe that portable flow as
`run_host_composition`, and do not add a public callback field merely to mimic
the native runner.

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
