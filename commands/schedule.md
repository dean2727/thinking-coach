---
description: Configure Mirror digestion or coach insight schedules
argument-hint: "digest|coach true|false [cadence]"
allowed-tools: Bash
---

Configure Mirror schedules:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src" python3 "${CLAUDE_PLUGIN_ROOT}/src/mirror/cli.py" schedule $ARGUMENTS
```

Examples:
- `/mirror:schedule digest true "0 * * * *"`
- `/mirror:schedule coach false`
