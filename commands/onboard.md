---
description: Configure Mirror storage, models, schedules, and goals
argument-hint: ""
allowed-tools: Bash
---

Run Mirror onboarding:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src" python3 "${CLAUDE_PLUGIN_ROOT}/src/mirror/cli.py" onboard
```

Then guide the user to add goals with `/mirror:goals add <goal>`, and remind them they can change models and schedules with `/mirror:settings`.
