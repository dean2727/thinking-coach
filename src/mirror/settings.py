from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-latest"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class SpecialistModel(BaseModel):
    provider: Literal["claude", "ollama"] = "claude"
    model: str = DEFAULT_CLAUDE_MODEL

    @property
    def model_ref(self) -> str:
        return f"{self.provider}/{self.model}"


class ScheduleSettings(BaseModel):
    enabled: bool = False
    cadence: str | None = None


class CoachInsightSettings(BaseModel):
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    output_dir: str = "~/.claude/coaching-sessions"
    save_manual_reports: bool = False

    def expanded_output_dir(self) -> Path:
        return Path(self.output_dir).expanduser()


class LLMSettings(BaseModel):
    default_provider: Literal["claude", "ollama"] = "claude"
    claude_api_key_env: str = "ANTHROPIC_API_KEY"
    claude_default_model: str = DEFAULT_CLAUDE_MODEL
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    specialists: dict[str, SpecialistModel] = Field(default_factory=dict)

    def specialist(self, name: str) -> SpecialistModel:
        if name in self.specialists:
            return self.specialists[name]
        if self.default_provider == "ollama":
            return SpecialistModel(provider="ollama", model="llama3.1:8b")
        return SpecialistModel(provider="claude", model=self.claude_default_model)


class ConcurrencySettings(BaseModel):
    max_session_workers: int = Field(default=4, ge=1)
    max_global_llm_calls: int = Field(default=4, ge=1)


class MirrorSettings(BaseModel):
    storage_mode: Literal["local_chroma", "mem0_cloud"] = "local_chroma"
    chroma_path: str = "${CLAUDE_PLUGIN_DATA}/chroma"
    mem0_api_key_env: str = "MEM0_API_KEY"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    concurrency: ConcurrencySettings = Field(default_factory=ConcurrencySettings)
    digest_schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    coach_insights: CoachInsightSettings = Field(default_factory=CoachInsightSettings)
    onboarded: bool = False

    @classmethod
    def defaults(cls) -> "MirrorSettings":
        return cls(
            llm=LLMSettings(
                specialists={
                    "prompt_intent": SpecialistModel(),
                    "verification_assimilation": SpecialistModel(),
                    "topic_depth": SpecialistModel(),
                    "goal_alignment": SpecialistModel(),
                    "memory_synthesis": SpecialistModel(),
                    "coach": SpecialistModel(),
                }
            )
        )
