---
description: Import a Claude.ai data export into Mirror memory
argument-hint: "PATH_TO_EXPORT_FOLDER"
allowed-tools: Bash
---

Import a Claude.ai export folder:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src" python3 "${CLAUDE_PLUGIN_ROOT}/src/mirror/cli.py" import-claude-export "$ARGUMENTS"
```
