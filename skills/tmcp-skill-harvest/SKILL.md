---
name: tmcp-skill-harvest
description: Use TMCP to harvest local skills, AGENTS/CLAUDE rules, editor rules, repository workflow docs, and process instructions into reusable skill packets.
status: stable
---

# TMCP Skill Harvest

Use this skill when the user asks to harvest skills, extract reusable agent behavior, compile a skill packet, inspect local instructions, turn process docs into reusable workflow material, or compare behavior across skill/rule files.

This is a discovery and packet-compilation workflow. Do not use it for direct feature implementation unless the user explicitly asks to apply the harvested packet.

## Workflow

1. Identify the smallest useful source set: `SKILL.md`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, `.github`, `README.md`, `docs`, `planning`, `workflows`, and relevant markdown process docs.
2. Invoke TMCP through MCP tools when exposed:
   - `tmcp_harvest_skills` for source nodes, behavior atoms, redaction summaries, warnings, and packet seed.
   - `tmcp_explain` when a task-specific packet is also needed.
3. If MCP tools are not exposed, use the CLI from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs harvest "<source-path>" --objective "Harvest reusable skill behavior" --write-artifacts
```

4. Preserve redaction behavior and report warnings as evidence.
5. Keep the packet focused; avoid sweeping unrelated docs into the harvest.

## Output Contract

Produce or cite:

- Harvest source paths and skipped/missing-source warnings.
- Redaction summary.
- Behavior atoms and source tiers.
- Packet seed and recommended next use.
