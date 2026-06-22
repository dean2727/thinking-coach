---
description: Configure Mirror storage, models, schedules, and goals
argument-hint: ""
allowed-tools: Bash
---

Run Mirror onboarding:

```bash
python3 -m uv run --project "${CLAUDE_PLUGIN_ROOT}" mirror onboard
```

Then guide the user to add goals with `/mirror:goals add <goal>`, and remind them they can change models and schedules with `/mirror:settings`.
