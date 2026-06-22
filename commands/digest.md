---
description: Process new Claude Code transcripts into Mirror memories
argument-hint: "[--root PATH] [--no-scan]"
allowed-tools: Bash
---

Run Mirror digestion with optional arguments:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src" python3 "${CLAUDE_PLUGIN_ROOT}/src/mirror/cli.py" digest $ARGUMENTS
```
