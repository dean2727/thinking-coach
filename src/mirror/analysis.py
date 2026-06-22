from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .features import deterministic_features
from .llm_router import LLMRouter
from .schema import (
    AssimilationSignal,
    CognitionOrder,
    CognitiveEffort,
    Dimension,
    InferenceConfidence,
    ObservableVerification,
    Observation,
    PromptIntent,
    SessionSummary,
    TranscriptSlice,
    Valence,
)


SPECIALISTS = ("prompt_intent", "verification_assimilation", "topic_depth", "goal_alignment")


@dataclass
class AnalysisResult:
    summary: SessionSummary
    observations: list[Observation] = field(default_factory=list)
    assimilation_signals: list[AssimilationSignal] = field(default_factory=list)


class Analyzer:
    def __init__(self, router: LLMRouter | None = None, *, use_llm: bool = False) -> None:
        self.router = router
        self.use_llm = use_llm

    async def analyze(self, slice_: TranscriptSlice, active_goals: list[str] | None = None) -> AnalysisResult:
        features = deterministic_features(slice_)
        summary = heuristic_summary(slice_, features)
        observations = heuristic_observations(features, slice_)
        signals = heuristic_assimilation_signals(features, slice_)

        if self.use_llm and self.router and not slice_.is_empty:
            await self._run_specialists(slice_, features, active_goals or [])

        return AnalysisResult(summary=summary, observations=observations, assimilation_signals=signals)

    async def _run_specialists(self, slice_: TranscriptSlice, features: dict, active_goals: list[str]) -> None:
        # MVP: execute configured specialists for provenance/routing validation.
        # Their JSON synthesis is intentionally deferred until we have eval fixtures.
        evidence = {
            "session_id": slice_.session_id,
            "features": features,
            "active_goals": active_goals,
        }
        user = str(evidence)
        system = "Return concise JSON candidate observations. Use only transcript-visible evidence."
        await asyncio.gather(*(self.router.complete(name, system, user, max_tokens=500) for name in SPECIALISTS))


def heuristic_summary(slice_: TranscriptSlice, features: dict) -> SessionSummary:
    intent = "Claude Code session"
    if features["first_user_prompt"]:
        intent = features["first_user_prompt"].strip().splitlines()[0][:160]
    cognition_order = CognitionOrder.DELEGATE_FIRST if features["delegation_first"] else CognitionOrder.MIXED
    if features["has_hypothesis_language"] and not features["delegation_first"]:
        cognition_order = CognitionOrder.UNDERSTAND_THEN_BUILD
    source_uuids = [turn.uuid for turn in slice_.turns if turn.uuid]
    started = min((turn.timestamp for turn in slice_.turns if turn.timestamp), default=None)
    ended = max((turn.timestamp for turn in slice_.turns if turn.timestamp), default=None)
    return SessionSummary(
        session_id=slice_.session_id,
        intent=intent,
        questions=features["questions"],
        topics=features["topics"],
        cognition_order=cognition_order,
        started_at=started,
        ended_at=ended,
        source_uuids=source_uuids,
    )


def heuristic_observations(features: dict, slice_: TranscriptSlice) -> list[Observation]:
    observations: list[Observation] = []
    source_uuids = [turn.uuid for turn in slice_.turns if turn.uuid]
    topics = features["topics"]

    if features["delegation_first"]:
        observations.append(
            Observation(
                dimension=Dimension.COGNITIVE_OUTSOURCING,
                claim="The session appears to start with delegation before an explicit hypothesis or constraint statement.",
                evidence=features["first_user_prompt"][:240],
                valence=Valence.GAP,
                topics=topics,
                source_uuids=source_uuids[:3],
                prompt_intent=PromptIntent.DELEGATION,
                cognition_order=CognitionOrder.DELEGATE_FIRST,
                cognitive_effort=CognitiveEffort.CHECKING,
                inference_confidence=InferenceConfidence.MEDIUM,
                inference_basis=["delegation_first", "no_hypothesis_language"],
            )
        )

    if features["had_edits"]:
        if features["ran_tests"] and features["read_after_edit"]:
            verification = ObservableVerification.PRESENT
            valence = Valence.GROWTH
            claim = "The transcript shows observable verification after generated edits."
            basis = ["read_after_edit", "test_command_seen"]
        elif features["ran_tests"] or features["read_after_edit"]:
            verification = ObservableVerification.PARTIAL
            valence = Valence.NEUTRAL
            claim = "The transcript shows partial observable verification after generated edits."
            basis = ["partial_verification"]
        else:
            verification = ObservableVerification.ABSENT
            valence = Valence.GAP
            claim = "The transcript shows no observable in-Claude verification after generated edits."
            basis = ["no_observable_follow_up"]
        observations.append(
            Observation(
                dimension=Dimension.PROMPT_QUALITY,
                claim=claim,
                evidence=", ".join(features["tool_names"][-8:]),
                valence=valence,
                topics=topics,
                source_uuids=source_uuids[-3:],
                observable_verification=verification,
                inference_confidence=InferenceConfidence.MEDIUM,
                inference_basis=basis,
            )
        )

    if features["orientation_questions"]:
        observations.append(
            Observation(
                dimension=Dimension.TOPIC_DEPTH_REGRESSION,
                claim="Later orientation-style questions may indicate the topic or code path has not fully stuck yet.",
                evidence="; ".join(features["orientation_questions"][:3]),
                valence=Valence.GAP,
                topics=topics,
                source_uuids=source_uuids[-3:],
                prompt_intent=PromptIntent.EXPLAIN_REQUEST,
                cognitive_effort=CognitiveEffort.CHECKING,
                inference_confidence=InferenceConfidence.LOW,
                inference_basis=["orientation_question"],
            )
        )

    return observations


def heuristic_assimilation_signals(features: dict, slice_: TranscriptSlice) -> list[AssimilationSignal]:
    signals: list[AssimilationSignal] = []
    source_uuids = [turn.uuid for turn in slice_.turns if turn.uuid]
    for question in features["orientation_questions"][:2]:
        signals.append(
            AssimilationSignal(
                related_session_id=slice_.session_id,
                related_files=features["files"],
                later_question=question,
                signal_strength="weak",
                source_uuids=source_uuids[-3:],
                inference_confidence=InferenceConfidence.LOW,
                inference_basis=["later_where_or_why_question"],
            )
        )
    return signals
