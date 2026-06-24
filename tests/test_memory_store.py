from unittest.mock import MagicMock

from mirror.memory_store import (
    Mem0Store,
    chroma_metadata,
    extract_mem0_id,
    goal_record,
    normalize_search_results,
    observation_record,
)
from mirror.schema import (
    CognitionOrder,
    CognitiveEffort,
    Dimension,
    Goal,
    InferenceConfidence,
    MemoryType,
    MirrorType,
    ObservableVerification,
    Observation,
    PromptIntent,
    Valence,
)


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


def test_observation_record_stores_without_mem0_inference():
    observation = Observation(
        dimension=Dimension.COGNITIVE_OUTSOURCING,
        claim="Delegation before hypothesis.",
        evidence="Implement this for me.",
        valence=Valence.NEUTRAL,
        prompt_intent=PromptIntent.DELEGATION,
        cognition_order=CognitionOrder.DELEGATE_FIRST,
        observable_verification=ObservableVerification.ABSENT,
        cognitive_effort=CognitiveEffort.CHECKING,
        inference_confidence=InferenceConfidence.MEDIUM,
        inference_basis=["delegation_first"],
        topics=["debugging"],
        source_uuids=["u1"],
    )
    record = observation_record(observation, user_id="user-1", session_id="s1")
    assert record.infer is False


def test_extract_mem0_id_reads_results_list():
    assert extract_mem0_id({"results": [{"id": "abc-123"}]}) == "abc-123"
    assert extract_mem0_id({"results": []}) is None


def test_normalize_search_results_reads_mem0_payload():
    payload = {
        "results": [
            {"id": "1", "memory": "observation one", "metadata": {"valence": "gap"}},
            {"id": "2", "memory": "observation two", "metadata": {"valence": "growth"}},
        ]
    }
    items = normalize_search_results(payload)
    assert len(items) == 2
    assert items[0]["memory"] == "observation one"


def test_mem0_store_falls_back_when_infer_returns_empty():
    store = Mem0Store.__new__(Mem0Store)
    store.client = MagicMock()
    store.client.add.side_effect = [
        {"results": []},
        {"results": [{"id": "fallback-id"}]},
    ]
    from mirror.schema import MemoryRecord

    record = MemoryRecord(
        text="cognitive_outsourcing: claim\nEvidence: proof",
        memory_type=MemoryType.FACTUAL,
        mirror_type=MirrorType.OBSERVATION,
        infer=True,
        metadata={"mirror_namespace": "mirror"},
    )
    assert store.add_record(record, user_id="user-1") == "fallback-id"
    assert store.client.add.call_count == 2
    assert store.client.add.call_args_list[1].kwargs["infer"] is False
