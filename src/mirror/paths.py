from __future__ import annotations

import os
from pathlib import Path


def plugin_data_dir() -> Path:
    raw = os.environ.get("CLAUDE_PLUGIN_DATA")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".claude" / "plugins" / "data" / "mirror"


def state_db_path() -> Path:
    return plugin_data_dir() / "mirror.db"


def claude_projects_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def coaching_sessions_dir() -> Path:
    return Path.home() / ".claude" / "coaching-sessions"


def expand_plugin_path(value: str) -> Path:
    return Path(value.replace("${CLAUDE_PLUGIN_DATA}", str(plugin_data_dir()))).expanduser()
