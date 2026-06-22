from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .analysis import Analyzer
from .memory_store import MemoryStore, assimilation_record, observation_record, session_summary_record
from .schema import SourceKind, ToolSequence, TranscriptSlice, Turn
from .state import MirrorState
from .transcript import parse_ts, text_from_content


EXPECTED_CONVERSATION_KEYS = {"uuid", "name", "chat_messages"}
EXPECTED_MESSAGE_KEYS = {"uuid", "sender", "content", "created_at"}


def schema_fingerprint(conversations: list[dict[str, Any]]) -> dict[str, list[str]]:
    conversation_keys = sorted({key for conv in conversations for key in conv.keys()})
    message_keys = sorted({key for conv in conversations for msg in conv.get("chat_messages", []) for key in msg.keys()})
    content_types = sorted(
        {
            block.get("type")
            for conv in conversations
            for msg in conv.get("chat_messages", [])
            for block in msg.get("content", [])
            if isinstance(block, dict) and block.get("type")
        }
    )
    return {"conversation_keys": conversation_keys, "message_keys": message_keys, "content_types": content_types}


def load_conversations(export_dir: Path) -> list[dict[str, Any]]:
    path = export_dir / "conversations.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("conversations.json must contain a JSON array")
    return data


def conversation_to_slice(conversation: dict[str, Any]) -> TranscriptSlice:
    session_id = str(conversation.get("uuid") or conversation.get("name") or "claude-export")
    turns: list[Turn] = []
    for msg in conversation.get("chat_messages", []):
        sender = msg.get("sender")
        role = "user" if sender == "human" else "assistant" if sender == "assistant" else "system"
        text = msg.get("text") or text_from_content(msg.get("content"))
        if not text:
            continue
        turns.append(
            Turn(
                uuid=msg.get("uuid"),
                role=role,
                text=text,
                timestamp=parse_ts(msg.get("created_at")),
            )
        )
    return TranscriptSlice(
        session_id=session_id,
        transcript_path=f"claude-export:{session_id}",
        project_path=conversation.get("name"),
        source=SourceKind.CLAUDE_AI_EXPORT,
        start_line=0,
        end_line=len(turns),
        last_uuid=turns[-1].uuid if turns else None,
        turns=turns,
        tool_sequence=ToolSequence(),
    )


async def import_claude_export(export_dir: Path, *, state: MirrorState, store: MemoryStore, user_id: str) -> int:
    conversations = load_conversations(export_dir)
    fingerprint = schema_fingerprint(conversations)
    missing_conv = EXPECTED_CONVERSATION_KEYS - set(fingerprint["conversation_keys"])
    missing_msg = EXPECTED_MESSAGE_KEYS - set(fingerprint["message_keys"])
    if missing_conv or missing_msg:
        state.record_digest_error(None, str(export_dir), f"Claude export schema drift: missing {missing_conv} {missing_msg}")

    analyzer = Analyzer(use_llm=False)
    imported = 0
    for conv in conversations:
        slice_ = conversation_to_slice(conv)
        if slice_.is_empty:
            continue
        result = await analyzer.analyze(slice_, active_goals=[goal.text for goal in state.goals(active_only=True)])
        records = [session_summary_record(result.summary, user_id=user_id, source=SourceKind.CLAUDE_AI_EXPORT)]
        records.extend(observation_record(obs, user_id=user_id, session_id=slice_.session_id) for obs in result.observations)
        records.extend(assimilation_record(sig, user_id=user_id) for sig in result.assimilation_signals)
        for idx, record in enumerate(records):
            mem0_id = store.add_record(record, user_id=user_id, run_id=slice_.session_id if record.memory_type.value == "episodic" else None)
            state.record_memory_link(f"export:{slice_.session_id}:{idx}", mem0_id, record.mirror_type.value, slice_.session_id)
        imported += 1
    return imported
