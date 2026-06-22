---
description: Process new Claude Code transcripts into Mirror memories
argument-hint: "[--root PATH] [--no-scan]"
allowed-tools: Bash
---

Run Mirror digestion with optional arguments:

```bash
python3 -m uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror digest $ARGUMENTS
```
