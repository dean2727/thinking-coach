from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import claude_projects_dir
from .schema import SourceKind, ToolEvent, ToolSequence, TranscriptSlice, Turn


TEST_HINTS = ("pytest", "npm test", "pnpm test", "yarn test", "cargo test", "go test", "swift test")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob", "LS"}


def parse_ts(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text" and block.get("text"):
            parts.append(str(block["text"]))
        elif block_type == "thinking":
            continue
    return "\n".join(parts).strip()


def tool_events_from_content(entry: dict[str, Any]) -> list[ToolEvent]:
    message = entry.get("message") or {}
    content = message.get("content")
    if not isinstance(content, list):
        return []
    events: list[ToolEvent] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        tool_input = block.get("input")
        events.append(
            ToolEvent(
                uuid=block.get("id") or entry.get("uuid"),
                name=str(block.get("name") or "unknown"),
                input_summary=summarize_tool_input(tool_input),
                timestamp=parse_ts(entry.get("timestamp")),
            )
        )
    return events


def summarize_tool_input(tool_input: Any) -> str | None:
    if tool_input is None:
        return None
    if isinstance(tool_input, str):
        return tool_input[:240]
    if isinstance(tool_input, dict):
        interesting = []
        for key in ("file_path", "path", "pattern", "command", "description"):
            if key in tool_input:
                interesting.append(f"{key}={tool_input[key]}")
        if interesting:
            return "; ".join(interesting)[:300]
        return json.dumps(tool_input, sort_keys=True)[:300]
    return str(tool_input)[:240]


def extract_files(tool_event: ToolEvent) -> list[str]:
    if not tool_event.input_summary:
        return []
    files: list[str] = []
    for token in tool_event.input_summary.replace(";", " ").split():
        if token.startswith("file_path=") or token.startswith("path="):
            _, value = token.split("=", 1)
            files.append(value.strip("'\""))
    return files


def build_tool_sequence(events: list[ToolEvent]) -> ToolSequence:
    names = [event.name for event in events]
    files: list[str] = []
    for event in events:
        files.extend(extract_files(event))
    ran_tests = any(
        event.name == "Bash" and event.input_summary and any(hint in event.input_summary for hint in TEST_HINTS)
        for event in events
    )
    edit_indices = [idx for idx, name in enumerate(names) if name in EDIT_TOOLS]
    read_indices = [idx for idx, name in enumerate(names) if name in READ_TOOLS]
    read_after_edit = bool(edit_indices and read_indices and max(read_indices) > min(edit_indices))
    return ToolSequence(names=names, files=sorted(set(files)), ran_tests=ran_tests, read_after_edit=read_after_edit)


def parse_transcript_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def turn_from_entry(entry: dict[str, Any]) -> Turn | None:
    entry_type = entry.get("type")
    if entry_type not in {"user", "assistant", "system"}:
        return None
    if entry.get("isCompactSummary"):
        return None
    if entry_type == "system" and entry.get("subtype") == "compact_boundary":
        return None
    message = entry.get("message") or {}
    text = text_from_content(message.get("content"))
    if not text and entry_type != "system":
        return None
    role = "user" if entry_type == "user" else "assistant" if entry_type == "assistant" else "system"
    return Turn(
        uuid=entry.get("uuid"),
        role=role,
        text=text,
        timestamp=parse_ts(entry.get("timestamp")),
        is_compact_summary=bool(entry.get("isCompactSummary")),
    )


def parse_transcript(path: Path, *, start_line: int = 0) -> TranscriptSlice:
    session_id = path.stem
    turns: list[Turn] = []
    tools: list[ToolEvent] = []
    last_uuid: str | None = None
    project_path: str | None = None
    git_branch: str | None = None
    end_line = start_line

    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if line_no <= start_line:
                continue
            end_line = line_no
            entry = parse_transcript_line(line)
            if not entry:
                continue
            last_uuid = entry.get("uuid") or last_uuid
            project_path = entry.get("cwd") or project_path
            git_branch = entry.get("gitBranch") or git_branch
            turn = turn_from_entry(entry)
            if turn:
                turns.append(turn)
            tools.extend(tool_events_from_content(entry))

    return TranscriptSlice(
        session_id=session_id,
        transcript_path=str(path),
        project_path=project_path,
        git_branch=git_branch,
        source=SourceKind.CLAUDE_CODE,
        start_line=start_line,
        end_line=end_line,
        last_uuid=last_uuid,
        turns=turns,
        tool_events=tools,
        tool_sequence=build_tool_sequence(tools),
    )


def find_transcripts(root: Path | None = None) -> list[Path]:
    root = root or claude_projects_dir()
    if not root.exists():
        return []
    return sorted(root.glob("**/*.jsonl"), key=lambda p: p.stat().st_mtime)
