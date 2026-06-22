from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from .analysis import Analyzer
from .claude_export import import_claude_export
from .coach import coach_from_store
from .digest import DigestRunner
from .insights_writer import report_to_markdown, write_report
from .memory_store import InMemoryStore, Mem0Store, goal_record
from .schema import Goal
from .state import MirrorState


def user_id() -> str:
    return os.environ.get("USER") or "local-user"


def build_store(state: MirrorState):
    settings = state.load_settings()
    if os.environ.get("MIRROR_DRY_RUN") == "1":
        return InMemoryStore()
    return Mem0Store(settings)


def cmd_onboard(args: argparse.Namespace) -> int:
    state = MirrorState()
    settings = state.load_settings()
    settings.onboarded = True
    state.save_settings(settings)
    print("Mirror is configured.")
    print("Default AI: Claude via ANTHROPIC_API_KEY. Persist it with:")
    print("  echo 'export ANTHROPIC_API_KEY=\"sk-ant-...\"' >> ~/.bashrc && source ~/.bashrc")
    print("Add goals with /mirror:goals add <text> or run: mirror goals add \"...\"")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = MirrorState()
    settings = state.load_settings()
    status = {
        "onboarded": settings.onboarded,
        "storage_mode": settings.storage_mode,
        "dirty_sessions": len(state.dirty_sessions()),
        "active_goals": len(state.goals(active_only=True)),
        "digest_schedule": settings.digest_schedule.model_dump(),
        "coach_insights": settings.coach_insights.model_dump(),
        "specialists": {name: model.model_dump() for name, model in settings.llm.specialists.items()},
    }
    print(json.dumps(status, indent=2))
    return 0


def cmd_settings(args: argparse.Namespace) -> int:
    state = MirrorState()
    settings = state.load_settings()
    if not args.key:
        print(settings.model_dump_json(indent=2))
        return 0
    data = settings.model_dump()
    set_nested(data, args.key.split("."), parse_value(args.value))
    state.save_settings(type(settings).model_validate(data))
    print("Updated setting", args.key)
    return 0


def cmd_storage(args: argparse.Namespace) -> int:
    state = MirrorState()
    settings = state.load_settings()
    if args.mode:
        settings.storage_mode = args.mode
        state.save_settings(settings)
    print(json.dumps({"storage_mode": settings.storage_mode, "chroma_path": settings.chroma_path}, indent=2))
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    state = MirrorState()
    settings = state.load_settings()
    if args.target == "digest":
        settings.digest_schedule.enabled = args.enabled
        settings.digest_schedule.cadence = args.cadence
    elif args.target == "coach":
        settings.coach_insights.schedule.enabled = args.enabled
        settings.coach_insights.schedule.cadence = args.cadence
    state.save_settings(settings)
    print(settings.model_dump_json(indent=2))
    return 0


def set_nested(data: dict, path: list[str], value) -> None:
    cur = data
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


def parse_value(value: str):
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        return value


def cmd_goals(args: argparse.Namespace) -> int:
    state = MirrorState()
    if args.action == "list":
        for goal in state.goals(active_only=False):
            print(f"{goal.id}\t{'active' if goal.active else 'archived'}\t{goal.text}")
        return 0

    if args.action == "add":
        goal = Goal(id=str(uuid.uuid4())[:8], text=args.text)
        state.save_goal(goal)
        try:
            store = build_store(state)
            mem0_id = store.add_record(goal_record(goal, user_id=user_id()), user_id=user_id())
            goal.mem0_id = mem0_id
            state.save_goal(goal)
        except Exception as exc:
            print(f"Saved goal locally; mem0 mirror failed: {exc}", file=sys.stderr)
        print(goal.id)
        return 0

    goals = {goal.id: goal for goal in state.goals(active_only=False)}
    goal = goals.get(args.id)
    if not goal:
        print("Goal not found", file=sys.stderr)
        return 1
    if args.action == "edit":
        goal.text = args.text
    elif args.action == "remove":
        goal.active = False
    state.save_goal(goal)
    print("Updated goal", goal.id)
    return 0


async def cmd_digest_async(args: argparse.Namespace) -> int:
    state = MirrorState()
    store = build_store(state)
    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(use_llm=False), user_id=user_id())
    stats = await runner.digest(transcript_root=Path(args.root).expanduser() if args.root else None, include_scan=not args.no_scan)
    print(json.dumps(stats.__dict__, indent=2))
    return 0


def cmd_coach(args: argparse.Namespace) -> int:
    state = MirrorState()
    store = build_store(state)
    report = coach_from_store(store, user_id=user_id(), goals=state.goals(active_only=True))
    print(report_to_markdown(report))
    if args.save or state.load_settings().coach_insights.save_manual_reports:
        path = write_report(report)
        print(f"\nSaved report: {path}")
    return 0


async def cmd_import_async(args: argparse.Namespace) -> int:
    state = MirrorState()
    store = build_store(state)
    count = await import_claude_export(Path(args.path).expanduser(), state=state, store=store, user_id=user_id())
    print(json.dumps({"imported_conversations": count}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mirror")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("onboard").set_defaults(func=cmd_onboard)
    sub.add_parser("status").set_defaults(func=cmd_status)

    settings = sub.add_parser("settings")
    settings.add_argument("key", nargs="?")
    settings.add_argument("value", nargs="?")
    settings.set_defaults(func=cmd_settings)

    storage = sub.add_parser("storage")
    storage.add_argument("mode", nargs="?", choices=["local_chroma", "mem0_cloud"])
    storage.set_defaults(func=cmd_storage)

    schedule = sub.add_parser("schedule")
    schedule.add_argument("target", choices=["digest", "coach"])
    schedule.add_argument("enabled", type=lambda value: value.lower() in {"1", "true", "yes", "on"})
    schedule.add_argument("cadence", nargs="?")
    schedule.set_defaults(func=cmd_schedule)

    goals = sub.add_parser("goals")
    goals.add_argument("action", choices=["list", "add", "edit", "remove"])
    goals.add_argument("id", nargs="?")
    goals.add_argument("text", nargs="?")
    goals.set_defaults(func=cmd_goals)

    digest = sub.add_parser("digest")
    digest.add_argument("--root")
    digest.add_argument("--no-scan", action="store_true")
    digest.set_defaults(async_func=cmd_digest_async)

    coach = sub.add_parser("coach")
    coach.add_argument("--save", action="store_true")
    coach.set_defaults(func=cmd_coach)

    import_cmd = sub.add_parser("import-claude-export")
    import_cmd.add_argument("path")
    import_cmd.set_defaults(async_func=cmd_import_async)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "async_func"):
        return asyncio.run(args.async_func(args))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
