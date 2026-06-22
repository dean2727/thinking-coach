from __future__ import annotations

import re

from .schema import TranscriptSlice


QUESTION_RE = re.compile(r"([^.!?\n]*\?)")
ORIENTATION_RE = re.compile(r"\b(where|why|what does|how does|where is|why did)\b", re.IGNORECASE)
DELEGATION_RE = re.compile(r"\b(fix|implement|build|add|make|write)\b", re.IGNORECASE)
HYPOTHESIS_RE = re.compile(r"\b(i think|my hypothesis|maybe|because|i suspect|likely)\b", re.IGNORECASE)


def user_text(slice_: TranscriptSlice) -> str:
    return "\n".join(turn.text for turn in slice_.turns if turn.role == "user")


def assistant_text(slice_: TranscriptSlice) -> str:
    return "\n".join(turn.text for turn in slice_.turns if turn.role == "assistant")


def extract_questions(text: str) -> list[str]:
    return [match.group(1).strip() for match in QUESTION_RE.finditer(text) if match.group(1).strip()]


def keyword_topics(text: str, limit: int = 6) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text.lower())
    stop = {"claude", "please", "could", "would", "should", "there", "about", "because", "implement", "function"}
    counts: dict[str, int] = {}
    for word in words:
        if word in stop:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def deterministic_features(slice_: TranscriptSlice) -> dict:
    u_text = user_text(slice_)
    a_text = assistant_text(slice_)
    questions = extract_questions(u_text)
    first_user = next((turn.text for turn in slice_.turns if turn.role == "user"), "")
    return {
        "questions": questions,
        "topics": keyword_topics(f"{u_text}\n{a_text}"),
        "first_user_prompt": first_user,
        "delegation_first": bool(DELEGATION_RE.search(first_user)) and not bool(HYPOTHESIS_RE.search(first_user)),
        "has_hypothesis_language": bool(HYPOTHESIS_RE.search(u_text)),
        "orientation_questions": [q for q in questions if ORIENTATION_RE.search(q)],
        "tool_names": slice_.tool_sequence.names,
        "files": slice_.tool_sequence.files,
        "ran_tests": slice_.tool_sequence.ran_tests,
        "read_after_edit": slice_.tool_sequence.read_after_edit,
        "had_edits": any(name in {"Edit", "Write", "MultiEdit", "NotebookEdit"} for name in slice_.tool_sequence.names),
    }
