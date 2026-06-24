import json
import os
import subprocess
import sys
from pathlib import Path

from mirror.cli import normalize_seed_argv, resolve_project, seed_result_payload
from mirror.digest import DigestStats
from mirror.paths import friendly_project_label


def test_normalize_seed_argv_rewrites_dash_prefixed_folder():
    assert normalize_seed_argv(["seed", "-Users-deanorenstein-Documents-projects-hud"]) == [
        "seed",
        "--project=-Users-deanorenstein-Documents-projects-hud",
    ]


def test_normalize_seed_argv_rewrites_bare_index():
    assert normalize_seed_argv(["seed", "3"]) == ["seed", "--project", "3"]


def test_normalize_seed_argv_leaves_explicit_project_flag():
    assert normalize_seed_argv(["seed", "--project", "hud"]) == ["seed", "--project", "hud"]


def test_normalize_seed_argv_rewrites_double_dash():
    assert normalize_seed_argv(["seed", "--", "3"]) == ["seed", "--project", "3"]


def test_friendly_project_label():
    assert friendly_project_label("-Users-deanorenstein-Documents-projects-hud") == "projects-hud"
    assert friendly_project_label("-Users-deanorenstein-Documents-academic-coding-stuff-Food-Finder") == (
        "academic-coding-stuff-Food-Finder"
    )


def test_resolve_project_by_label():
    projects = [Path("-Users-deanorenstein-Documents-projects-hud")]
    assert resolve_project(projects, "projects-hud") == projects[0]


def test_seed_result_payload_up_to_date():
    stats = DigestStats(sessions_seen=2, sessions_processed=2, sessions_up_to_date=2, memories_written=0)
    payload = seed_result_payload(Path("-Users-deanorenstein-Documents-projects-hud"), stats)
    assert payload["status"] == "up_to_date"
    assert "already digested" in payload["message"]


def test_mirror_seed_accepts_dash_prefixed_folder_name():
    result = subprocess.run(
        [sys.executable, "-m", "mirror", "seed", "-Users-deanorenstein-Documents-projects-hud"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "MIRROR_DRY_RUN": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["sessions_seen"] >= 0
