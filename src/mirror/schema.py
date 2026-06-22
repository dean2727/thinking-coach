from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Dimension(StrEnum):
    PROMPT_QUALITY = "prompt_quality"
    COGNITIVE_OUTSOURCING = "cognitive_outsourcing"
    TOPIC_DEPTH_REGRESSION = "topic_depth_regression"
    BLIND_SPOT = "blind_spot"
    ARTICULATION = "articulation"
    GROWTH_EDGE = "growth_edge"


class MemoryType(StrEnum):
    FACTUAL = "factual"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MirrorType(StrEnum):
    OBSERVATION = "observation"
    ASSIMILATION_SIGNAL = "assimilation_signal"
    SESSION_SUMMARY = "session_summary"
    TOPIC = "topic"
    GOAL = "goal"


class PromptIntent(StrEnum):
    SOLUTION_REQUEST = "solution_request"
    HINT_REQUEST = "hint_request"
    CRITIQUE_REQUEST = "critique_request"
    EXPLAIN_REQUEST = "explain_request"
    DELEGATION = "delegation"
    VERIFICATION = "verification"
    UNKNOWN = "unknown"


class CognitionOrder(StrEnum):
    UNDERSTAND_THEN_BUILD = "understand_then_build"
    DELEGATE_FIRST = "delegate_first"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ObservableVerification(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class AssimilationStrength(StrEnum):
    STRONG = "strong"
    WEAK = "weak"
    UNCLEAR = "unclear"


class InferenceConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CognitiveEffort(StrEnum):
    GENERATING = "generating"
    ANALYZING = "analyzing"
    CHECKING = "checking"
    INTEGRATING = "integrating"
    UNKNOWN = "unknown"


class Valence(StrEnum):
    GROWTH = "growth"
    GAP = "gap"
    NEUTRAL = "neutral"


class SourceKind(StrEnum):
    CLAUDE_CODE = "claude_code"
    CLAUDE_AI_EXPORT = "claude_ai_export"


class Turn(BaseModel):
    uuid: str | None = None
    role: Literal["user", "assistant", "system"]
    text: str = ""
    timestamp: datetime | None = None
    is_compact_summary: bool = False


class ToolEvent(BaseModel):
    uuid: str | None = None
    name: str
    input_summary: str | None = None
    timestamp: datetime | None = None


class ToolSequence(BaseModel):
    names: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    ran_tests: bool = False
    read_after_edit: bool = False


class TranscriptSlice(BaseModel):
    session_id: str
    transcript_path: str
    project_path: str | None = None
    git_branch: str | None = None
    source: SourceKind = SourceKind.CLAUDE_CODE
    start_line: int = 0
    end_line: int = 0
    last_uuid: str | None = None
    turns: list[Turn] = Field(default_factory=list)
    tool_events: list[ToolEvent] = Field(default_factory=list)
    tool_sequence: ToolSequence = Field(default_factory=ToolSequence)

    @property
    def is_empty(self) -> bool:
        return not self.turns and not self.tool_events


class SessionSummary(BaseModel):
    session_id: str
    intent: str
    questions: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    cognition_order: CognitionOrder = CognitionOrder.UNKNOWN
    started_at: datetime | None = None
    ended_at: datetime | None = None
    source_uuids: list[str] = Field(default_factory=list)


class Observation(BaseModel):
    dimension: Dimension
    claim: str
    evidence: str
    valence: Valence = Valence.NEUTRAL
    topics: list[str] = Field(default_factory=list)
    source_uuids: list[str] = Field(default_factory=list)
    prompt_intent: PromptIntent = PromptIntent.UNKNOWN
    cognition_order: CognitionOrder = CognitionOrder.UNKNOWN
    observable_verification: ObservableVerification = ObservableVerification.UNKNOWN
    cognitive_effort: CognitiveEffort = CognitiveEffort.UNKNOWN
    inference_confidence: InferenceConfidence = InferenceConfidence.LOW
    inference_basis: list[str] = Field(default_factory=list)


class AssimilationSignal(BaseModel):
    related_session_id: str | None = None
    related_files: list[str] = Field(default_factory=list)
    later_question: str
    signal_strength: AssimilationStrength = AssimilationStrength.UNCLEAR
    lag_days: float | None = None
    source_uuids: list[str] = Field(default_factory=list)
    inference_confidence: InferenceConfidence = InferenceConfidence.LOW
    inference_basis: list[str] = Field(default_factory=list)


class Topic(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    depth_trend: Literal["deepening", "stable", "regressing", "unknown"] = "unknown"


class TopicDepthSnapshot(BaseModel):
    topic_name: str
    ts: datetime = Field(default_factory=now_utc)
    depth_score: float = Field(ge=0.0, le=1.0)
    prompt_intent_ratio: dict[str, float] = Field(default_factory=dict)
    observable_verification_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class Goal(BaseModel):
    id: str
    text: str
    dimension: Dimension | None = None
    practice: str | None = None
    active: bool = True
    mem0_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class MemoryRecord(BaseModel):
    text: str
    memory_type: MemoryType
    mirror_type: MirrorType
    infer: bool
    metadata: dict[str, Any]
    source_model: str | None = None


class CoachingReport(BaseModel):
    generated_at: datetime = Field(default_factory=now_utc)
    title: str = "Mirror coaching report"
    growth_highlights: list[str] = Field(default_factory=list)
    growth_edges: list[str] = Field(default_factory=list)
    next_practice: str | None = None
    goal_status: list[str] = Field(default_factory=list)
    prompt_patterns: list[str] = Field(default_factory=list)
    evidence_limits: str = "This report only reflects evidence visible in stored Mirror memories."
    output_path: str | None = None


MIRROR_NAMESPACE = "mirror"
SCHEMA_VERSION = "1"


def base_metadata(
    *,
    memory_type: MemoryType,
    mirror_type: MirrorType,
    user_id: str,
    session_id: str | None = None,
    topics: list[str] | None = None,
    source: SourceKind = SourceKind.CLAUDE_CODE,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "memory_type": memory_type.value,
        "mirror_type": mirror_type.value,
        "mirror_namespace": MIRROR_NAMESPACE,
        "schema_version": SCHEMA_VERSION,
        "user_id": user_id,
        "source": source.value,
    }
    if session_id:
        metadata["session_id"] = session_id
    if topics:
        metadata["topics"] = topics
    if extra:
        metadata.update(extra)
    return metadata
