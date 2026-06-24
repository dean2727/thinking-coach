from __future__ import annotations

from dataclasses import dataclass

from .memory_store import MemoryStore, normalize_search_results
from .state import MirrorState


@dataclass
class CleanupStats:
    broken_links_removed: int = 0
    orphan_memories_removed: int = 0
    session_links_removed: int = 0
    session_memories_removed: int = 0


def referenced_mem0_ids(state: MirrorState) -> set[str]:
    ids: set[str] = set()
    with state.connect() as conn:
        for row in conn.execute(
            "SELECT mem0_id FROM memory_links WHERE mem0_id IS NOT NULL AND mem0_id != ''"
        ):
            ids.add(row["mem0_id"])
        for row in conn.execute("SELECT mem0_id FROM goals WHERE mem0_id IS NOT NULL AND mem0_id != ''"):
            ids.add(row["mem0_id"])
    return ids


def broken_memory_links(state: MirrorState) -> list:
    with state.connect() as conn:
        return list(
            conn.execute(
                """
                SELECT local_id, mirror_type, session_id
                FROM memory_links
                WHERE mem0_id IS NULL OR mem0_id = ''
                ORDER BY local_id
                """
            )
        )


def list_all_memory_ids(store: MemoryStore, user_id: str) -> list[str]:
    if not hasattr(store, "client"):
        return []
    raw = store.client.get_all(filters={"user_id": user_id})
    return [str(item["id"]) for item in normalize_search_results(raw) if item.get("id")]


def clear_session_memories(state: MirrorState, store: MemoryStore, session_id: str) -> tuple[int, int]:
    links_removed = 0
    memories_removed = 0
    for link in state.memory_links_for_session(session_id):
        if link["mem0_id"]:
            store.delete(link["mem0_id"])
            memories_removed += 1
        state.delete_memory_link(link["local_id"])
        links_removed += 1
    return links_removed, memories_removed


def run_cleanup(
    state: MirrorState,
    store: MemoryStore,
    user_id: str,
    *,
    orphans: bool = False,
    session_id: str | None = None,
    dry_run: bool = False,
) -> CleanupStats:
    stats = CleanupStats()

    if session_id:
        links = state.memory_links_for_session(session_id)
        stats.session_links_removed = len(links)
        stats.session_memories_removed = sum(1 for link in links if link["mem0_id"])
        if not dry_run:
            clear_session_memories(state, store, session_id)
        return stats

    for link in broken_memory_links(state):
        stats.broken_links_removed += 1
        if not dry_run:
            state.delete_memory_link(link["local_id"])

    if orphans:
        referenced = referenced_mem0_ids(state)
        for memory_id in list_all_memory_ids(store, user_id):
            if memory_id in referenced:
                continue
            stats.orphan_memories_removed += 1
            if not dry_run:
                store.delete(memory_id)

    return stats
