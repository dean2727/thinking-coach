from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .analysis import Analyzer
from .memory_store import (
    MemoryStore,
    assimilation_record,
    observation_record,
    session_summary_record,
)
from .schema import MemoryRecord
from .state import MirrorState
from .transcript import find_transcripts, parse_transcript


@dataclass
class DigestStats:
    sessions_seen: int = 0
    sessions_processed: int = 0
    memories_written: int = 0
    errors: int = 0


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
        slice_ = parse_transcript(path, start_line=start_line)
        if slice_.is_empty:
            self.state.save_watermark(str(path), slice_.session_id, slice_.end_line, slice_.last_uuid)
            self.state.clear_dirty_session(slice_.session_id)
            return 0

        result = await self.analyzer.analyze(slice_, active_goals=[goal.text for goal in self.state.goals(active_only=True)])
        records: list[MemoryRecord] = [session_summary_record(result.summary, user_id=self.user_id)]
        records.extend(observation_record(obs, user_id=self.user_id, session_id=slice_.session_id) for obs in result.observations)
        records.extend(assimilation_record(sig, user_id=self.user_id) for sig in result.assimilation_signals)

        written = 0
        for idx, record in enumerate(records):
            mem0_id = self.store.add_record(record, user_id=self.user_id, run_id=slice_.session_id if record.memory_type.value == "episodic" else None)
            self.state.record_memory_link(f"{slice_.session_id}:{idx}", mem0_id, record.mirror_type.value, slice_.session_id)
            written += 1

        self.state.save_watermark(str(path), slice_.session_id, slice_.end_line, slice_.last_uuid)
        self.state.clear_dirty_session(slice_.session_id)
        return written
