from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .analysis import Analyzer
from .memory_store import (
    MemoryStore,
    assimilation_record,
    observation_record,
    session_summary_record,
)
from .schema import MemoryRecord, TranscriptSlice
from .state import MirrorState
from .transcript import find_transcripts, parse_transcript


@dataclass
class DigestStats:
    sessions_seen: int = 0
    sessions_processed: int = 0
    memories_written: int = 0
    errors: int = 0


# Stable keys for memory_links: scoped to a transcript line range so retries
# replace the same Chroma rows instead of creating duplicates.
def slice_local_id(session_id: str, start_line: int, end_line: int, mirror_type: str, index: int) -> str:
    return f"{session_id}:{start_line}-{end_line}:{mirror_type}:{index}"


def slice_link_prefix(session_id: str, start_line: int, end_line: int) -> str:
    return f"{session_id}:{start_line}-{end_line}:"


class DigestRunner:
    def __init__(self, *, state: MirrorState, store: MemoryStore, analyzer: Analyzer, user_id: str) -> None:
        self.state = state
        self.store = store
        self.analyzer = analyzer
        self.user_id = user_id

    async def digest(self, *, transcript_root: Path | None = None, include_scan: bool = True) -> DigestStats:
        candidates = self._candidate_paths(transcript_root=transcript_root, include_scan=include_scan)
        settings = self.state.load_settings()
        semaphore = asyncio.Semaphore(settings.concurrency.max_session_workers)
        stats = DigestStats(sessions_seen=len(candidates))

        async def run_one(path: Path) -> None:
            async with semaphore:
                try:
                    written = await self.digest_path(path)
                    stats.sessions_processed += 1
                    stats.memories_written += written
                except Exception as exc:  # pragma: no cover - covered by integration behavior
                    stats.errors += 1
                    self.state.record_digest_error(None, str(path), str(exc))

        await asyncio.gather(*(run_one(path) for path in candidates))
        return stats

    def _candidate_paths(self, *, transcript_root: Path | None, include_scan: bool) -> list[Path]:
        paths = {Path(row["transcript_path"]) for row in self.state.dirty_sessions()}
        if include_scan:
            paths.update(find_transcripts(transcript_root))
        return sorted(path for path in paths if path.exists())

    async def digest_path(self, path: Path) -> int:
        start_line, _ = self.state.watermark(str(path))
        chat_slice = parse_transcript(path, start_line=start_line)
        if chat_slice.is_empty:
            self.state.save_watermark(str(path), chat_slice.session_id, chat_slice.end_line, chat_slice.last_uuid)
            self.state.clear_dirty_session(chat_slice.session_id)
            return 0

        result = await self.analyzer.analyze(chat_slice, active_goals=[goal.text for goal in self.state.goals(active_only=True)])
        records: list[MemoryRecord] = [session_summary_record(result.summary, user_id=self.user_id)]
        records.extend(observation_record(obs, user_id=self.user_id, session_id=chat_slice.session_id) for obs in result.observations)
        records.extend(assimilation_record(sig, user_id=self.user_id) for sig in result.assimilation_signals)

        # Upsert each memory by slice-local id so interrupted digests can safely retry.
        type_counters: defaultdict[str, int] = defaultdict(int)
        kept_local_ids: set[str] = set()
        written = 0
        for record in records:
            mirror_type = record.mirror_type.value
            index = type_counters[mirror_type]
            type_counters[mirror_type] += 1
            local_id = slice_local_id(chat_slice.session_id, chat_slice.start_line, chat_slice.end_line, mirror_type, index)
            written += self._persist_record(chat_slice, local_id, record)
            kept_local_ids.add(local_id)

        # Drop Chroma rows left over from a partial write of this slice.
        self._prune_stale_slice_links(chat_slice, kept_local_ids)

        self.state.save_watermark(str(path), chat_slice.session_id, chat_slice.end_line, chat_slice.last_uuid)
        self.state.clear_dirty_session(chat_slice.session_id)
        return written

    def _persist_record(self, chat_slice: TranscriptSlice, local_id: str, record: MemoryRecord) -> int:
        # Reuse the existing mem0 id when possible; delete+add only if update fails.
        run_id = chat_slice.session_id if record.memory_type.value == "episodic" else None
        existing = self.state.memory_link(local_id)
        mem0_id: str | None

        if existing and existing["mem0_id"]:
            old_id = existing["mem0_id"]
            if self.store.update(old_id, record.text):
                mem0_id = old_id
            else:
                self.store.delete(old_id)
                mem0_id = self.store.add_record(record, user_id=self.user_id, run_id=run_id)
        else:
            mem0_id = self.store.add_record(record, user_id=self.user_id, run_id=run_id)

        self.state.record_memory_link(local_id, mem0_id, record.mirror_type.value, chat_slice.session_id)
        return 1

    def _prune_stale_slice_links(self, slice_, kept_local_ids: set[str]) -> None:
        # e.g. observation:3 written before an interrupt but absent on the next run.
        prefix = slice_link_prefix(slice_.session_id, slice_.start_line, slice_.end_line)
        for link in self.state.memory_links_with_prefix(prefix):
            local_id = link["local_id"]
            if local_id in kept_local_ids:
                continue
            if link["mem0_id"]:
                self.store.delete(link["mem0_id"])
            self.state.delete_memory_link(local_id)
