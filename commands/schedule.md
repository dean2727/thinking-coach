---
description: Configure Mirror digestion or coach insight schedules
argument-hint: "digest|coach true|false [cadence]"
allowed-tools: Bash
---

Configure Mirror schedules:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror schedule $ARGUMENTS
```

Examples:
- `/mirror:schedule digest true "0 * * * *"`
- `/mirror:schedule coach false`
