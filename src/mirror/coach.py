from __future__ import annotations

from .memory_store import MemoryStore
from .schema import CoachingReport, Goal


def build_coaching_report(
    *,
    memories: list[dict],
    goals: list[Goal],
    title: str = "Mirror coaching report",
) -> CoachingReport:
    report = CoachingReport(title=title)
    growth: list[str] = []
    edges: list[str] = []

    for item in memories:
        text = str(item.get("memory") or item.get("text") or "")
        metadata = item.get("metadata") or {}
        valence = metadata.get("valence")
        if valence == "growth":
            growth.append(text)
        elif valence == "gap":
            edges.append(text)

    report.growth_highlights = growth[:2] or ["No clear growth highlight yet; run more digestion as sessions accumulate."]
    report.growth_edges = edges[:2] or ["No high-confidence growth edge yet."]
    report.goal_status = [f"{goal.id}: {goal.text} ({'active' if goal.active else 'archived'})" for goal in goals]
    report.next_practice = choose_next_practice(edges, goals)
    report.prompt_patterns = [
        "Before asking Claude to debug: state one hypothesis, one file you suspect, and one test that would falsify your guess.",
        "Ask for a hint or critique first when the goal is learning, then request implementation after you understand the tradeoff.",
    ]
    return report


def choose_next_practice(edges: list[str], goals: list[Goal]) -> str:
    if goals:
        return f"Pick one active goal and apply it in the next Claude Code session: {goals[0].text}"
    if edges:
        return "After Claude writes code, explain the change back in your own words before moving on."
    return "Use Mirror for a few sessions, then run /mirror:coach again for a stronger signal."


def coach_from_store(store: MemoryStore, *, user_id: str, goals: list[Goal], limit: int = 20) -> CoachingReport:
    memories = store.search(
        "recent prompt quality cognitive outsourcing verification assimilation topic depth",
        user_id=user_id,
        limit=limit,
        filters={"mirror_namespace": "mirror"},
    )
    return build_coaching_report(memories=memories, goals=goals)
