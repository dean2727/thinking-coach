---
description: Mine an existing Claude Code project's transcripts into Mirror memory
argument-hint: "[--list | --project SELECTOR]"
allowed-tools: Bash
---

Seed (backfill) Mirror memory from a project under `~/.claude/projects/`.

Unlike `/mirror:digest` (net-new hook-queued sessions only), seed mines every **top-level** `*.jsonl` in a chosen project folder. Watermarks apply: if transcripts were already digested, the run reports `status: up_to_date` with `memories_written: 0` (memories are already in storage).

## Step 1 — list projects

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror seed --list
```

Present the numbered list (`index`, `label`, `transcripts`) and ask which project to mine.

## Step 2 — seed the chosen project

**Always pass the selector with `--project`.** Project folder names start with `-Users-...` and will fail without `--project`.

```bash
# by list index (preferred)
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror seed --project 3

# re-process transcripts that were already digested (e.g. to backfill observations)
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror seed --project 3 --force

# by friendly label or unique substring
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror seed --project projects-hud
```

Do **not** run `mirror seed -Users-deanorenstein-...` (argparse treats it as a flag).

## Interpreting results

- `"status": "seeded"` + `memories_written > 0` — new memories written
- `"status": "up_to_date"` — transcripts already digested; memories already in Chroma
- `"status": "empty"` — no top-level `.jsonl` files in that project folder
