# TMCP Concepts

TMCP turns scattered agent instructions into task-specific packets. It reads source material such as skills, docs, rules, and prompts; extracts reusable behavior; and compiles the smallest context bundle that helps an agent complete a task without dragging in unrelated instructions.

## Compiler, Not Skill Loader

Slash commands are manual imports. TMCP is the compiler.

- The user describes work in natural language.
- TMCP infers `task_identity` and compiles an operating packet.
- The agent executes under `packet_markdown`.
- TMCP recompiles when files, failures, browser evidence, or phase changes alter the work.
- Receipts record what was used, skipped, and verified.

Skill names are provenance and graph nodes. They are not the default user interface.

## Core Terms

- Source node: a skill, doc, rule, prompt, or other instruction file that can provide task-relevant behavior.
- Behavior atom: one reusable instruction or constraint extracted from a source node.
- Packet: the smallest relevant context bundle for a task.
- Task identity: structured classification (`primary`, `active_routes`, `signals`) for what the work really is.
- Scoped packet seed: a curated compile recipe for a skill family and phase chain.
- Shortcut candidate: an advisory compiled view with `compiled_from` provenance; never the source of truth.
- Workflow: a repeatable audit, planning, or remediation process over a packet.

## Model

TMCP follows this path:

```text
user prompt
  -> task identity
  -> source nodes
  -> behavior atoms
  -> composed packet
  -> runtime recompile
  -> receipt
```

Legacy routed packets (`tmcp_explain`) still follow:

```text
source nodes -> behavior atoms -> packets -> workflows
```

AIOS can store or accelerate parts of this flow when explicitly configured, but TMCP does not require AIOS and should not be framed as AIOS-first.
