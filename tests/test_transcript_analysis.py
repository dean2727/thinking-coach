from pathlib import Path

import pytest

from mirror.analysis import Analyzer
from mirror.schema import ObservableVerification
from mirror.transcript import parse_transcript


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_transcript_drops_compaction_and_tracks_tools():
    slice_ = parse_transcript(FIXTURES / "sample_session.jsonl")

    assert slice_.session_id == "sample_session"
    assert [turn.uuid for turn in slice_.turns] == ["u1", "a1", "u2"]
    assert slice_.tool_sequence.names == ["Edit"]
    assert slice_.tool_sequence.files == ["auth/middleware.py"]
    assert not slice_.tool_sequence.ran_tests
    assert slice_.end_line == 4


def test_parse_transcript_respects_watermark():
    slice_ = parse_transcript(FIXTURES / "sample_session.jsonl", start_line=2)

    assert [turn.uuid for turn in slice_.turns] == ["u2"]
    assert slice_.start_line == 2
    assert slice_.end_line == 4


@pytest.mark.asyncio
async def test_analysis_flags_no_observable_verification_and_orientation_question():
    slice_ = parse_transcript(FIXTURES / "sample_session.jsonl")
    result = await Analyzer().analyze(slice_)

    assert result.summary.cognition_order == "delegate_first"
    assert any(obs.observable_verification == ObservableVerification.ABSENT for obs in result.observations)
    assert result.assimilation_signals
    assert result.assimilation_signals[0].signal_strength == "weak"


@pytest.mark.asyncio
async def test_analysis_detects_present_verification_when_read_and_tests_follow_edit():
    slice_ = parse_transcript(FIXTURES / "verified_session.jsonl")
    result = await Analyzer().analyze(slice_)

    assert any(obs.observable_verification == ObservableVerification.PRESENT for obs in result.observations)
    assert result.summary.cognition_order == "understand_then_build"
