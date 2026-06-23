from mirror.memory_store import chroma_metadata, goal_record
from mirror.schema import Goal, MemoryType, MirrorType


def test_chroma_metadata_drops_none_and_serializes_lists():
    metadata = {
        "memory_type": "factual",
        "active": True,
        "dimension": None,
        "practice": None,
        "topics": ["debugging", "hypothesis"],
        "count": 3,
    }
    cleaned = chroma_metadata(metadata)
    assert "dimension" not in cleaned
    assert "practice" not in cleaned
    assert cleaned["active"] is True
    assert cleaned["topics"] == "debugging, hypothesis"
    assert cleaned["count"] == 3


def test_goal_record_metadata_is_chroma_compatible():
    goal = Goal(id="g1", text="State one hypothesis before debugging")
    record = goal_record(goal, user_id="user-1")
    cleaned = chroma_metadata(record.metadata)
    assert all(value is not None and not isinstance(value, list) for value in cleaned.values())
    assert cleaned["mirror_type"] == MirrorType.GOAL.value
    assert cleaned["memory_type"] == MemoryType.FACTUAL.value
    assert cleaned["goal_id"] == "g1"
