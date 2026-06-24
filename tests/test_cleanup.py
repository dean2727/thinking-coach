from mirror.cleanup import broken_memory_links, referenced_mem0_ids, run_cleanup
from mirror.memory_store import InMemoryStore
from mirror.state import MirrorState


def test_cleanup_removes_broken_links(tmp_path):
    state = MirrorState(db_path=tmp_path / "mirror.db")
    state.record_memory_link("good:0", "mem-1", "session_summary", "sess-a")
    state.record_memory_link("bad:0", None, "observation", "sess-b")
    state.record_memory_link("bad:1", "", "observation", "sess-b")

    stats = run_cleanup(state, InMemoryStore(), "test-user")
    assert stats.broken_links_removed == 2
    assert stats.orphan_memories_removed == 0
    assert broken_memory_links(state) == []
    assert referenced_mem0_ids(state) == {"mem-1"}


def test_cleanup_session(tmp_path):
    state = MirrorState(db_path=tmp_path / "mirror.db")
    store = InMemoryStore()
    store.records["mem-a"] = None  # type: ignore[assignment]
    store.records["mem-b"] = None  # type: ignore[assignment]
    state.record_memory_link("sess:0", "mem-a", "session_summary", "sess-1")
    state.record_memory_link("sess:1", "mem-b", "observation", "sess-1")
    state.record_memory_link("other:0", "mem-c", "session_summary", "sess-2")

    stats = run_cleanup(state, store, "test-user", session_id="sess-1")
    assert stats.session_links_removed == 2
    assert stats.session_memories_removed == 2
    assert state.memory_links_for_session("sess-1") == []
    assert state.memory_link("other:0") is not None


def test_cleanup_dry_run_leaves_state(tmp_path):
    state = MirrorState(db_path=tmp_path / "mirror.db")
    state.record_memory_link("bad:0", None, "observation", "sess-b")

    stats = run_cleanup(state, InMemoryStore(), "test-user", dry_run=True)
    assert stats.broken_links_removed == 1
    assert broken_memory_links(state) != []
