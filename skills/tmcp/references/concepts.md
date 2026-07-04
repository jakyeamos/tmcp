# TMCP Concepts

TMCP turns scattered agent instructions into task-specific packets. It reads source material such as skills, docs, rules, and prompts; extracts reusable behavior; and compiles the smallest context bundle that helps an agent complete a task without dragging in unrelated instructions.

## Core Terms

- Source node: a skill, doc, rule, prompt, or other instruction file that can provide task-relevant behavior.
- Behavior atom: one reusable instruction or constraint extracted from a source node.
- Packet: the smallest relevant context bundle for a task.
- Workflow: a repeatable audit, planning, or remediation process over a packet.

## Model

TMCP follows this path:

```text
source nodes -> behavior atoms -> packets -> workflows
```

AIOS can store or accelerate parts of this flow when explicitly configured, but TMCP does not require AIOS and should not be framed as AIOS-first.
