from mirror.cli import main
from mirror.state import MirrorState


def test_goals_add_accepts_quoted_text(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    monkeypatch.setenv("MIRROR_DRY_RUN", "1")

    assert main(["goals", "add", "State one hypothesis before asking Claude to debug"]) == 0

    goals = MirrorState(tmp_path / "mirror.db").goals(active_only=True)
    assert len(goals) == 1
    assert goals[0].text == "State one hypothesis before asking Claude to debug"


def test_goals_add_accepts_unquoted_words(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    monkeypatch.setenv("MIRROR_DRY_RUN", "1")

    assert main(["goals", "add", "State", "one", "hypothesis"]) == 0

    goals = MirrorState(tmp_path / "mirror.db").goals(active_only=True)
    assert goals[0].text == "State one hypothesis"


def test_module_entrypoint(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))

    assert main(["status"]) == 0
