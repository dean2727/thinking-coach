from pathlib import Path

import pytest

from mirror.analysis import Analyzer
from mirror.claude_export import import_claude_export, load_conversations, schema_fingerprint
from mirror.digest import DigestRunner, slice_local_id
from mirror.insights_writer import report_filename, write_report
from mirror.memory_store import InMemoryStore
from mirror.schema import CoachingReport, Goal, MemoryRecord, MemoryType, MirrorType
from mirror.state import MirrorState


FIXTURES = Path(__file__).parent / "fixtures"


def test_state_queue_watermark_and_goal_roundtrip(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    state.enqueue_session("s1", "/tmp/s1.jsonl", mtime=1.0, reason="Stop")
    assert len(state.dirty_sessions()) == 1

    state.save_watermark("/tmp/s1.jsonl", "s1", 4, "uuid-4")
    assert state.watermark("/tmp/s1.jsonl") == (4, "uuid-4")

    goal = Goal(id="g1", text="State one hypothesis before debugging")
    state.save_goal(goal)
    assert state.goals(active_only=True)[0].text == goal.text


@pytest.mark.asyncio
async def test_digest_writes_memories_and_updates_watermark(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    store = InMemoryStore()
    transcript = FIXTURES / "sample_session.jsonl"
    state.enqueue_session("sample_session", str(transcript), reason="test")

    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(), user_id="tester")
    stats = await runner.digest()

    assert stats.sessions_processed == 1
    assert stats.memories_written >= 2
    assert state.watermark(str(transcript))[0] == 4
    assert not state.dirty_sessions()


@pytest.mark.asyncio
async def test_digest_is_idempotent_with_watermark(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    store = InMemoryStore()
    transcript = FIXTURES / "sample_session.jsonl"
    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(), user_id="tester")

    await runner.digest_path(transcript)
    second = await runner.digest_path(transcript)

    assert second == 0


@pytest.mark.asyncio
async def test_digest_retry_replaces_not_duplicates(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    store = InMemoryStore()
    transcript = FIXTURES / "sample_session.jsonl"
    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(), user_id="tester")

    await runner.digest_path(transcript)
    count_after_first = len(store.records)

    state.save_watermark(str(transcript), "sample_session", 0, None)

    await runner.digest_path(transcript)

    assert len(store.records) == count_after_first


@pytest.mark.asyncio
async def test_digest_prunes_stale_slice_links(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    store = InMemoryStore()
    transcript = FIXTURES / "sample_session.jsonl"
    stale_local_id = slice_local_id("sample_session", 0, 4, MirrorType.OBSERVATION.value, 99)
    stale_mem0 = store.add_record(
        MemoryRecord(
            text="stale orphan",
            memory_type=MemoryType.FACTUAL,
            mirror_type=MirrorType.OBSERVATION,
            infer=False,
            metadata={"mirror_namespace": "mirror"},
        ),
        user_id="tester",
    )
    state.record_memory_link(stale_local_id, stale_mem0, MirrorType.OBSERVATION.value, "sample_session")

    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(), user_id="tester")
    await runner.digest_path(transcript)

    assert state.memory_link(stale_local_id) is None
    assert stale_mem0 not in store.records


@pytest.mark.asyncio
async def test_digest_only_processes_dirty_sessions(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    store = InMemoryStore()
    transcript = FIXTURES / "sample_session.jsonl"
    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(), user_id="tester")

    stats = await runner.digest()

    assert stats.sessions_seen == 0
    assert stats.memories_written == 0
    assert state.watermark(str(transcript)) == (0, None)


@pytest.mark.asyncio
async def test_seed_mines_project_dir_and_ignores_dirty_queue(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    store = InMemoryStore()
    transcript = FIXTURES / "sample_session.jsonl"
    state.enqueue_session("other", "/tmp/not-a-real-session.jsonl", reason="Stop")

    runner = DigestRunner(state=state, store=store, analyzer=Analyzer(), user_id="tester")
    stats = await runner.seed(FIXTURES)

    assert stats.sessions_seen >= 1
    assert stats.memories_written >= 2
    assert state.watermark(str(transcript))[0] == 4
    # seed does not touch the hook-enqueued dirty queue
    assert len(state.dirty_sessions()) == 1

    second = await runner.seed(FIXTURES)
    assert second.memories_written == 0
    assert second.sessions_up_to_date == second.sessions_seen


def test_seed_only_finds_top_level_transcripts(tmp_path):
    from mirror.transcript import find_top_level_transcripts

    (tmp_path / "a.jsonl").write_text("{}\n")
    nested = tmp_path / "subagents"
    nested.mkdir()
    (nested / "b.jsonl").write_text("{}\n")

    found = {p.name for p in find_top_level_transcripts(tmp_path)}
    assert found == {"a.jsonl"}


def test_insight_writer_uses_datetime_filename(tmp_path):
    report = CoachingReport(growth_highlights=["Used critique prompts"], growth_edges=["No observable verification"])
    path = write_report(report, tmp_path)

    assert path.name.endswith("_mirror-coach.md")
    assert report_filename(report.generated_at) == path.name
    assert "Evidence limits" in path.read_text()


def test_claude_export_fingerprint():
    conversations = load_conversations(FIXTURES)
    fingerprint = schema_fingerprint(conversations)

    assert "chat_messages" in fingerprint["conversation_keys"]
    assert "sender" in fingerprint["message_keys"]
    assert "text" in fingerprint["content_types"]


@pytest.mark.asyncio
async def test_claude_export_import_writes_memories(tmp_path):
    state = MirrorState(tmp_path / "mirror.db")
    store = InMemoryStore()

    count = await import_claude_export(FIXTURES, state=state, store=store, user_id="tester")

    assert count == 1
    assert store.records
