---
description: Mine an existing Claude Code project's transcripts into Mirror memory
argument-hint: "[project] [--list]"
allowed-tools: Bash
---

Seed (backfill) Mirror memory from a project under `~/.claude/projects/`.

Unlike `/mirror:digest` (which only processes net-new, hook-queued sessions), seed mines every top-level transcript in a chosen project folder. Watermarks still apply, so re-running only ingests new lines.

First, list the available projects so the developer can choose:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror seed --list
```

Present the list and ask which project to mine. Then seed the chosen one (by folder name, list index, or a unique substring):

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror seed $ARGUMENTS
```
