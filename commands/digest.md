---
description: Process net-new Claude Code transcripts into Mirror memories
allowed-tools: Bash
---

Run Mirror digestion over net-new, hook-enqueued sessions (`dirty_sessions`). This is what scheduled/cron digest uses.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror digest
```

To backfill an existing project's transcripts instead, use `/mirror:seed`.
