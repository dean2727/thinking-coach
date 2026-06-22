from __future__ import annotations

import os
import uuid
from typing import Any, Protocol

from .paths import expand_plugin_path
from .schema import (
    AssimilationSignal,
    Goal,
    MemoryRecord,
    MemoryType,
    MirrorType,
    Observation,
    SessionSummary,
    SourceKind,
    Topic,
    base_metadata,
)
from .settings import MirrorSettings


class MemoryStore(Protocol):
    def add_record(self, record: MemoryRecord, *, user_id: str, run_id: str | None = None) -> str | None: ...
    def search(self, query: str, *, user_id: str, limit: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...
    def update(self, memory_id: str, text: str) -> bool: ...
    def delete(self, memory_id: str) -> bool: ...


class InMemoryStore:
    """Small test/dry-run store with the same shape as the mem0 adapters."""

    def __init__(self) -> None:
        self.records: dict[str, MemoryRecord] = {}

    def add_record(self, record: MemoryRecord, *, user_id: str, run_id: str | None = None) -> str:
        memory_id = str(uuid.uuid4())
        self.records[memory_id] = record
        return memory_id

    def search(self, query: str, *, user_id: str, limit: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        terms = query.lower().split()
        results: list[dict[str, Any]] = []
        for memory_id, record in self.records.items():
            if filters:
                skip = False
                for key, value in filters.items():
                    if record.metadata.get(key) != value:
                        skip = True
                        break
                if skip:
                    continue
            haystack = record.text.lower()
            score = sum(1 for term in terms if term in haystack)
            if score or not terms:
                results.append({"id": memory_id, "memory": record.text, "metadata": record.metadata, "score": score})
        return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]

    def update(self, memory_id: str, text: str) -> bool:
        record = self.records.get(memory_id)
        if not record:
            return False
        self.records[memory_id] = record.model_copy(update={"text": text})
        return True

    def delete(self, memory_id: str) -> bool:
        return self.records.pop(memory_id, None) is not None


class Mem0Store:
    def __init__(self, settings: MirrorSettings) -> None:
        self.settings = settings
        self.client = self._build_client(settings)

    def _build_client(self, settings: MirrorSettings) -> Any:
        if settings.storage_mode == "mem0_cloud":
            from mem0 import MemoryClient  # type: ignore

            api_key = os.environ.get(settings.mem0_api_key_env)
            if not api_key:
                raise RuntimeError(f"{settings.mem0_api_key_env} is not set")
            return MemoryClient(api_key=api_key)

        from mem0 import Memory  # type: ignore

        chroma_path = expand_plugin_path(settings.chroma_path)
        chroma_path.mkdir(parents=True, exist_ok=True)
        config = {
            "vector_store": {
                "provider": "chromadb",
                "config": {
                    "collection_name": "mirror_memory",
                    "path": str(chroma_path),
                },
            }
        }
        return Memory.from_config(config)

    def add_record(self, record: MemoryRecord, *, user_id: str, run_id: str | None = None) -> str | None:
        result = self.client.add(record.text, user_id=user_id, run_id=run_id, metadata=record.metadata, infer=record.infer)
        return extract_mem0_id(result)

    def search(self, query: str, *, user_id: str, limit: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        merged = {"user_id": user_id, "mirror_namespace": "mirror"}
        if filters:
            merged.update(filters)
        try:
            return list(self.client.search(query, filters=merged, top_k=limit, rerank=True))
        except TypeError:
            return list(self.client.search(query, user_id=user_id, limit=limit))

    def update(self, memory_id: str, text: str) -> bool:
        if not hasattr(self.client, "update"):
            return False
        self.client.update(memory_id=memory_id, data=text)
        return True

    def delete(self, memory_id: str) -> bool:
        if not hasattr(self.client, "delete"):
            return False
        self.client.delete(memory_id=memory_id)
        return True


def extract_mem0_id(result: Any) -> str | None:
    if isinstance(result, dict):
        if result.get("id"):
            return str(result["id"])
        if result.get("results") and isinstance(result["results"], list) and result["results"]:
            first = result["results"][0]
            if isinstance(first, dict) and first.get("id"):
                return str(first["id"])
    if isinstance(result, list) and result and isinstance(result[0], dict) and result[0].get("id"):
        return str(result[0]["id"])
    return None


def observation_record(observation: Observation, *, user_id: str, session_id: str | None = None) -> MemoryRecord:
    metadata = base_metadata(
        memory_type=MemoryType.FACTUAL,
        mirror_type=MirrorType.OBSERVATION,
        user_id=user_id,
        session_id=session_id,
        topics=observation.topics,
        extra={
            "dimension": observation.dimension.value,
            "valence": observation.valence.value,
            "prompt_intent": observation.prompt_intent.value,
            "cognition_order": observation.cognition_order.value,
            "observable_verification": observation.observable_verification.value,
            "cognitive_effort": observation.cognitive_effort.value,
            "inference_confidence": observation.inference_confidence.value,
            "inference_basis": observation.inference_basis,
            "source_uuids": observation.source_uuids,
        },
    )
    text = f"{observation.dimension.value}: {observation.claim}\nEvidence: {observation.evidence}"
    return MemoryRecord(text=text, memory_type=MemoryType.FACTUAL, mirror_type=MirrorType.OBSERVATION, infer=True, metadata=metadata)


def assimilation_record(signal: AssimilationSignal, *, user_id: str) -> MemoryRecord:
    metadata = base_metadata(
        memory_type=MemoryType.FACTUAL,
        mirror_type=MirrorType.ASSIMILATION_SIGNAL,
        user_id=user_id,
        session_id=signal.related_session_id,
        extra={
            "assimilation_signal": signal.signal_strength.value,
            "related_files": signal.related_files,
            "source_uuids": signal.source_uuids,
            "inference_confidence": signal.inference_confidence.value,
            "inference_basis": signal.inference_basis,
        },
    )
    text = f"Assimilation signal: {signal.later_question}"
    return MemoryRecord(text=text, memory_type=MemoryType.FACTUAL, mirror_type=MirrorType.ASSIMILATION_SIGNAL, infer=True, metadata=metadata)


def session_summary_record(summary: SessionSummary, *, user_id: str, source: SourceKind = SourceKind.CLAUDE_CODE) -> MemoryRecord:
    metadata = base_metadata(
        memory_type=MemoryType.EPISODIC,
        mirror_type=MirrorType.SESSION_SUMMARY,
        user_id=user_id,
        session_id=summary.session_id,
        topics=summary.topics,
        source=source,
        extra={"cognition_order": summary.cognition_order.value, "source_uuids": summary.source_uuids},
    )
    questions = "; ".join(summary.questions[:5])
    text = f"Session {summary.session_id}: {summary.intent}"
    if questions:
        text += f"\nQuestions: {questions}"
    return MemoryRecord(text=text, memory_type=MemoryType.EPISODIC, mirror_type=MirrorType.SESSION_SUMMARY, infer=False, metadata=metadata)


def topic_record(topic: Topic, *, user_id: str) -> MemoryRecord:
    metadata = base_metadata(
        memory_type=MemoryType.SEMANTIC,
        mirror_type=MirrorType.TOPIC,
        user_id=user_id,
        topics=[topic.name],
        extra={"aliases": topic.aliases, "depth_trend": topic.depth_trend},
    )
    text = f"Topic: {topic.name}; aliases: {', '.join(topic.aliases)}; depth trend: {topic.depth_trend}"
    return MemoryRecord(text=text, memory_type=MemoryType.SEMANTIC, mirror_type=MirrorType.TOPIC, infer=True, metadata=metadata)


def goal_record(goal: Goal, *, user_id: str) -> MemoryRecord:
    metadata = base_metadata(
        memory_type=MemoryType.FACTUAL,
        mirror_type=MirrorType.GOAL,
        user_id=user_id,
        extra={
            "goal_id": goal.id,
            "active": goal.active,
            "dimension": goal.dimension.value if goal.dimension else None,
            "practice": goal.practice,
        },
    )
    text = f"Goal: {goal.text}"
    return MemoryRecord(text=text, memory_type=MemoryType.FACTUAL, mirror_type=MirrorType.GOAL, infer=True, metadata=metadata)
