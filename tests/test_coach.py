from mirror.coach import build_coaching_report
from mirror.schema import Goal


def test_build_coaching_report_classifies_gap_and_growth():
    memories = [
        {"memory": "Delegation-first debugging.", "metadata": {"valence": "gap"}},
        {"memory": "Asked for critique before implementation.", "metadata": {"valence": "growth"}},
    ]
    goals = [Goal(id="g1", text="State one hypothesis before debugging")]

    report = build_coaching_report(memories=memories, goals=goals)

    assert "Delegation-first debugging." in report.growth_edges
    assert "Asked for critique before implementation." in report.growth_highlights
    assert report.goal_status == ["g1: State one hypothesis before debugging (active)"]
