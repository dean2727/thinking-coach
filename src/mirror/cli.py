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
from .cleanup import run_cleanup
from .coach import coach_from_store
from .digest import DigestRunner
from .insights_writer import report_to_markdown, write_report
from .memory_store import InMemoryStore, Mem0Store, goal_record
from .paths import friendly_project_label, list_claude_projects
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


def goal_text_from_args(args: argparse.Namespace) -> str:
    parts = ([args.id] if args.id else []) + list(args.text or [])
    return " ".join(parts).strip()


def cmd_goals(args: argparse.Namespace) -> int:
    state = MirrorState()
    if args.action == "list":
        for goal in state.goals(active_only=False):
            print(f"{goal.id}\t{'active' if goal.active else 'archived'}\t{goal.text}")
        return 0

    if args.action == "add":
        text = goal_text_from_args(args)
        if not text:
            print("Usage: mirror goals add <text>", file=sys.stderr)
            return 1
        goal = Goal(id=str(uuid.uuid4())[:8], text=text)
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

    if not args.id:
        print(f"Usage: mirror goals {args.action} <id> [text]", file=sys.stderr)
        return 1

    goals = {goal.id: goal for goal in state.goals(active_only=False)}
    goal = goals.get(args.id)
    if not goal:
        print("Goal not found", file=sys.stderr)
        return 1
    if args.action == "edit":
        text = " ".join(args.text or []).strip()
        if not text:
            print("Usage: mirror goals edit <id> <text>", file=sys.stderr)
            return 1
        goal.text = text
    elif args.action == "remove":
        goal.active = False
    state.save_goal(goal)
    print("Updated goal", goal.id)
    return 0


async def cmd_digest_async(args: argparse.Namespace) -> int:
    state = MirrorState()
    store = build_store(state)
    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(use_llm=False), user_id=user_id())
    stats = await runner.digest()
    print(json.dumps(stats.__dict__, indent=2))
    return 0


def normalize_seed_argv(argv: list[str]) -> list[str]:
    # Claude project folders start with "-Users-...". Rewrite bare selectors so argparse
    # does not treat them as flags. Use --project=VALUE when VALUE starts with "-".
    if not argv or argv[0] != "seed":
        return argv
    rest = argv[1:]
    if not rest or rest[0] in ("--list", "-h", "--help") or rest[0] in ("--project", "-p"):
        return argv
    if rest[0] == "--":
        if len(rest) >= 2:
            return _seed_with_project(rest[1], rest[2:])
        return argv
    return _seed_with_project(rest[0], rest[1:])


def _seed_with_project(selector: str, tail: list[str]) -> list[str]:
    if selector.startswith("-"):
        return [f"seed", f"--project={selector}", *tail]
    return ["seed", "--project", selector, *tail]


def project_choices(projects: list[Path]) -> list[dict[str, object]]:
    choices = []
    for idx, project in enumerate(projects, start=1):
        choices.append(
            {
                "index": idx,
                "name": project.name,
                "label": friendly_project_label(project.name),
                "transcripts": len(list(project.glob("*.jsonl"))),
            }
        )
    return choices


def resolve_project(projects: list[Path], selector: str) -> Path | None:
    # Accept a 1-based list index, folder name, friendly label, or unique substring.
    if selector.isdigit():
        idx = int(selector) - 1
        return projects[idx] if 0 <= idx < len(projects) else None
    for project in projects:
        if project.name == selector or friendly_project_label(project.name) == selector:
            return project
    matches = [
        project
        for project in projects
        if selector in project.name or selector in friendly_project_label(project.name)
    ]
    return matches[0] if len(matches) == 1 else None


def seed_result_payload(project: Path, stats) -> dict:
    payload = {
        "project": project.name,
        "label": friendly_project_label(project.name),
        **stats.__dict__,
    }
    if stats.sessions_seen and stats.memories_written == 0 and stats.sessions_up_to_date == stats.sessions_seen:
        payload["status"] = "up_to_date"
        payload["message"] = (
            "All transcripts in this project were already digested; memories are in storage. "
            "Nothing new to process."
        )
    elif stats.memories_written > 0:
        payload["status"] = "seeded"
    elif stats.sessions_seen == 0:
        payload["status"] = "empty"
        payload["message"] = "No top-level .jsonl transcripts found in this project folder."
    else:
        payload["status"] = "completed"
    return payload


async def cmd_seed_async(args: argparse.Namespace) -> int:
    projects = list_claude_projects()
    if not projects:
        print("No Claude Code projects found under ~/.claude/projects/", file=sys.stderr)
        return 1

    if args.list or not args.project:
        if args.project is None and not args.list and sys.stdin.isatty():
            selected = prompt_for_project(projects)
            if selected is None:
                print("No project selected.", file=sys.stderr)
                return 1
        else:
            print(json.dumps(project_choices(projects), indent=2))
            return 0
    else:
        selected = resolve_project(projects, args.project)
        if selected is None:
            print(f"Could not resolve project: {args.project}", file=sys.stderr)
            return 1

    state = MirrorState()
    store = build_store(state)
    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(use_llm=False), user_id=user_id())
    stats = await runner.seed(selected, force=args.force)
    print(json.dumps(seed_result_payload(selected, stats), indent=2))
    return 0


def prompt_for_project(projects: list[Path]) -> Path | None:
    print("Select a Claude Code project to mine into Mirror memory:\n")
    for choice in project_choices(projects):
        print(f"  {choice['index']}. {choice['label']} ({choice['transcripts']} transcripts)")
    choice = input("\nProject number (or blank to cancel): ").strip()
    if not choice:
        return None
    return resolve_project(projects, choice)


def cmd_cleanup(args: argparse.Namespace) -> int:
    state = MirrorState()
    store = build_store(state)
    stats = run_cleanup(
        state,
        store,
        user_id(),
        orphans=args.orphans,
        session_id=args.session,
        dry_run=args.dry_run,
    )
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
    goals.add_argument("id", nargs="?", help="goal id for edit/remove; first text token for add")
    goals.add_argument("text", nargs=argparse.REMAINDER, help="remaining goal text")
    goals.set_defaults(func=cmd_goals)

    digest = sub.add_parser("digest")
    digest.set_defaults(async_func=cmd_digest_async)

    seed = sub.add_parser("seed", help="Mine an existing ~/.claude/projects/<project> into memory")
    seed.add_argument(
        "--project",
        "-p",
        dest="project",
        metavar="SELECTOR",
        help="1-based index, friendly label, folder name, or unique substring",
    )
    seed.add_argument("--list", action="store_true", help="list available projects and exit")
    seed.add_argument("--force", action="store_true", help="re-process all transcripts even if already digested")
    seed.set_defaults(async_func=cmd_seed_async)

    cleanup = sub.add_parser("cleanup", help="Remove broken memory links and optional orphan Chroma rows")
    cleanup.add_argument(
        "--orphans",
        action="store_true",
        help="delete Chroma memories not referenced by memory_links or goals",
    )
    cleanup.add_argument("--session", metavar="SESSION_ID", help="clear all memories for one session")
    cleanup.add_argument("--dry-run", action="store_true", help="report what would be removed without deleting")
    cleanup.set_defaults(func=cmd_cleanup)

    coach = sub.add_parser("coach")
    coach.add_argument("--save", action="store_true")
    coach.set_defaults(func=cmd_coach)

    import_cmd = sub.add_parser("import-claude-export")
    import_cmd.add_argument("path")
    import_cmd.set_defaults(async_func=cmd_import_async)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = normalize_seed_argv(list(argv) if argv is not None else sys.argv[1:])
    args = parser.parse_args(argv)
    if hasattr(args, "async_func"):
        return asyncio.run(args.async_func(args))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
