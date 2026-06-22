#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    payload = json.load(sys.stdin)
    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(plugin_root / "src"))

    from mirror.state import MirrorState

    state = MirrorState()
    event = payload.get("hook_event_name")

    if event == "SessionStart":
        if not state.load_settings().onboarded:
            print("Mirror is installed. Run /mirror:onboard to configure coaching goals, models, and storage.")
        return 0

    transcript_path = payload.get("transcript_path")
    session_id = payload.get("session_id")
    if transcript_path and session_id:
        try:
            mtime = Path(transcript_path).stat().st_mtime
        except OSError:
            mtime = None
        state.enqueue_session(session_id, transcript_path, mtime=mtime, reason=event or "hook")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
