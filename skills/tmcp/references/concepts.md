# TMCP Concepts

TMCP turns scattered agent instructions into task-specific packets. It reads source material such as skills, docs, rules, and prompts; extracts reusable behavior; and compiles the smallest context bundle that helps an agent complete a task without dragging in unrelated instructions.

## Compiler, Not Skill Loader

Slash commands are manual imports. TMCP is the compiler.

- The user describes work in natural language.
- For substantial work, TMCP prepares bounded source slices and the host proposes source-backed semantics.
- TMCP validates the proposal and compiles a typed, staged operating packet.
- The agent executes under `packet_markdown`.
- TMCP recompiles when files, failures, browser evidence, or phase changes alter the work.
- Receipts record what was used, skipped, and verified.

Skill names are provenance and graph nodes. They are not the default user interface.

## Core Terms

- Source node: a skill, doc, rule, prompt, or other instruction file that can provide task-relevant behavior.
- Behavior atom: one reusable instruction or constraint extracted from a source node.
- Packet: the smallest relevant context bundle for a task.
- Task identity: structured classification (`primary`, `active_routes`, `signals`) for what the work really is.
- Semantic proposal: the host's advisory task model, skill roles, typed edges, gates, and citations; it has no authority until TMCP validates it.
- Typed-edge direction: `requires`, `consumes`, and `verifies` mean the `to` node runs before the `from` node; `precedes`, `enables`, and `produces` mean `from` runs before `to`; `complements` adds coverage without ordering; `conflicts_with` forbids same-phase activation. The preflight returns this mapping as `relationship_type_semantics`.
- Composition plan: TMCP's validated, ordered recipe with active/deferred stages, handoffs, coverage, diagnostics, and content/graph provenance.
- Source role: `governing_instruction`, `active_skill`, `supporting_reference`, or `evidence_only`. Only the first two can activate behavior.
- Scoped packet seed: a curated compile recipe for a skill family and phase chain.
- Shortcut candidate: an advisory compiled view with `compiled_from` provenance; never the source of truth.
- Workflow: a repeatable audit, planning, or remediation process over a packet.

## Model

TMCP follows this path:

```text
user prompt
  -> bounded composition preflight
  -> host semantic proposal
  -> validated typed skill graph
  -> staged composed packet
  -> runtime recompile
  -> receipt
```

Hosts apply this path invisibly to substantial multi-step, tool-using, high-stakes, or skill-relevant work. Trivial conversation and simple status replies bypass it. TMCP compiles; the agent performs tools and mutations under the active stage and its gates.

Composition is read-only and stateless by default. `cache_policy=project` opts into explicitly reviewed project-local recipes; `global` is a separate advisory opt-in. Neither receipts nor successful runs promote anything automatically.

Legacy routed packets (`tmcp_explain`) still follow:

```text
source nodes -> behavior atoms -> packets -> workflows
```

AIOS can store or accelerate parts of this flow when explicitly configured, but TMCP does not require AIOS and should not be framed as AIOS-first.
