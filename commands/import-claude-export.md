---
description: Import a Claude.ai data export into Mirror memory
argument-hint: "PATH_TO_EXPORT_FOLDER"
allowed-tools: Bash
---

Import a Claude.ai export folder:

```bash
python3 -m uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror import-claude-export "$ARGUMENTS"
```
