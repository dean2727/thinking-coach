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


def list_claude_projects() -> list[Path]:
    # Each subdirectory of ~/.claude/projects/ is one project's transcript folder.
    root = claude_projects_dir()
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)


def friendly_project_label(folder_name: str) -> str:
    # "-Users-deanorenstein-Documents-projects-hud" -> "projects-hud"
    for prefix in ("-Users-", "-users-"):
        if folder_name.startswith(prefix):
            remainder = folder_name[len(prefix) :]
            if "Documents-" in remainder:
                remainder = remainder.split("Documents-", 1)[1]
            return remainder
    return folder_name


def coaching_sessions_dir() -> Path:
    return Path.home() / ".claude" / "coaching-sessions"


def expand_plugin_path(value: str) -> Path:
    return Path(value.replace("${CLAUDE_PLUGIN_DATA}", str(plugin_data_dir()))).expanduser()
