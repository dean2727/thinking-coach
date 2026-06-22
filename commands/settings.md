---
description: View or edit Mirror settings, models, schedules, and output paths
argument-hint: "[key value]"
allowed-tools: Bash
---

View or update Mirror settings:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src" python3 "${CLAUDE_PLUGIN_ROOT}/src/mirror/cli.py" settings $ARGUMENTS
```

Examples:
- `/mirror:settings`
- `/mirror:settings llm.default_provider ollama`
- `/mirror:settings coach_insights.schedule.enabled true`
