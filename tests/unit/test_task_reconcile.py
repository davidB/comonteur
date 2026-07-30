"""Pure-logic tests for the `comonteur:reconcile` task script — timeline.yaml validation
and anchor→frame resolution (SPEC.md §5.2/§10 M4).

Ported from cli/src/timeline.rs's #[cfg(test)] module when the Rust CLI was dissolved into
mise tasks. This is the logic that lost the Rust compiler, so it carries the most coverage.

Named test_task_reconcile.py to stay distinct from test_reconcile.py, which covers
addon/comonteur/reconcile.py — the Blender-side consumer of this script's JSON output.
"""

from pathlib import Path
from typing import Any

import pytest
from _tasks import load

timeline = load("reconcile")


def word(w: str, start: float, end: float) -> dict[str, Any]:
    return {"word": w, "start": start, "end": end}


def scene_shot(
    shot_id: str,
    start: int | None = None,
    anchor: dict[str, Any] | None = None,
    duration: int = 90,
) -> dict[str, Any]:
    return {
        "id": shot_id,
        "source": {
            "kind": "scene",
            "blend": "compositions/frames/shot-01.blend",
            "scene": "GEN_hook",
        },
        "start": start,
        "anchor": anchor,
        "duration": duration,
        "in": None,
        "transition": None,
    }


def doc_with(shots: list[dict[str, Any]], audio: list[dict[str, Any]] | None = None) -> dict:
    return {"fps": 30, "resolution": [1920, 1080], "shots": shots, "audio": audio or []}


def test_valid_doc_has_no_errors() -> None:
    assert timeline.validate(doc_with([scene_shot("shot-01", start=0)])) == []


def test_empty_shots_errors() -> None:
    assert len(timeline.validate(doc_with([]))) == 1


def test_duplicate_shot_id_errors() -> None:
    doc = doc_with([scene_shot("shot-01", start=0), scene_shot("shot-01", start=90)])
    assert any("duplicate id" in e for e in timeline.validate(doc))


def test_both_start_and_anchor_set_errors() -> None:
    anchor = {"word": "hi", "occurrence": 1, "offset": 0.0}
    doc = doc_with([scene_shot("shot-01", start=0, anchor=anchor)])
    assert any("exactly one of" in e for e in timeline.validate(doc))


def test_neither_start_nor_anchor_set_errors() -> None:
    doc = doc_with([scene_shot("shot-01")])
    assert any("exactly one of" in e for e in timeline.validate(doc))


def test_non_positive_duration_errors() -> None:
    doc = doc_with([scene_shot("shot-01", start=0, duration=0)])
    assert any("duration" in e for e in timeline.validate(doc))


def test_anchor_occurrence_below_one_errors() -> None:
    anchor = {"word": "hi", "occurrence": 0, "offset": 0.0}
    doc = doc_with([scene_shot("shot-01", anchor=anchor)])
    assert any("occurrence must be >= 1" in e for e in timeline.validate(doc))


def test_duplicate_audio_id_errors() -> None:
    audio = [
        {"id": "vo", "path": "audio/a.wav", "start": 0, "anchor": None},
        {"id": "vo", "path": "audio/b.wav", "start": 10, "anchor": None},
    ]
    doc = doc_with([scene_shot("shot-01", start=0)], audio)
    assert any("audio[1]: duplicate id" in e for e in timeline.validate(doc))


def test_resolve_passes_through_absolute_start() -> None:
    doc = doc_with([scene_shot("shot-01", start=42)])
    assert timeline.resolve(doc, None, 30)["shots"][0]["start_frame"] == 42


def test_resolve_finds_nth_anchor_occurrence() -> None:
    transcript = [word("the", 0.0, 0.2), word("data", 0.2, 0.6), word("data", 1.0, 1.4)]
    anchor = {"word": "data", "occurrence": 2, "offset": -0.1}
    doc = doc_with([scene_shot("shot-01", anchor=anchor)])
    # second "data" starts at 1.0s, offset -0.1s -> 0.9s * 30fps = 27
    assert timeline.resolve(doc, transcript, 30)["shots"][0]["start_frame"] == 27


def test_resolve_anchor_match_is_case_insensitive() -> None:
    transcript = [word("Data", 0.5, 0.9)]
    anchor = {"word": "data", "occurrence": 1, "offset": 0.0}
    doc = doc_with([scene_shot("shot-01", anchor=anchor)])
    assert timeline.resolve(doc, transcript, 30)["shots"][0]["start_frame"] == 15


def test_resolve_fails_loudly_on_missing_anchor_word() -> None:
    transcript = [word("hello", 0.0, 0.2)]
    anchor = {"word": "observability", "occurrence": 1, "offset": 0.0}
    doc = doc_with([scene_shot("shot-01", anchor=anchor)])
    with pytest.raises(SystemExit, match="observability"):
        timeline.resolve(doc, transcript, 30)


def test_resolve_fails_loudly_on_missing_occurrence() -> None:
    transcript = [word("data", 0.0, 0.2)]
    anchor = {"word": "data", "occurrence": 3, "offset": 0.0}
    doc = doc_with([scene_shot("shot-01", anchor=anchor)])
    with pytest.raises(SystemExit, match="1 occurrence"):
        timeline.resolve(doc, transcript, 30)


def test_resolve_fails_loudly_on_missing_transcript() -> None:
    anchor = {"word": "data", "occurrence": 1, "offset": 0.0}
    doc = doc_with([scene_shot("shot-01", anchor=anchor)])
    with pytest.raises(SystemExit, match="no transcript"):
        timeline.resolve(doc, None, 30)


def test_resolve_converts_transition_seconds_to_frames() -> None:
    shot = scene_shot("shot-01", start=0)
    shot["transition"] = {"type": "crossfade", "duration": 0.5}
    resolved = timeline.resolve(doc_with([shot]), None, 30)["shots"][0]["transition"]
    assert resolved == {"type": "crossfade", "duration_frames": 15}


def test_round_half_away_from_zero_matches_rust() -> None:
    # Python's built-in round() is banker's rounding and would give 0 here; Rust's
    # f64::round rounds half away from zero. Frame numbers must match the old CLI.
    assert timeline._round_half_away(0.5) == 1
    assert timeline._round_half_away(1.5) == 2
    assert timeline._round_half_away(2.5) == 3
    assert timeline._round_half_away(-0.5) == -1


def test_resolve_audio_tracks() -> None:
    audio = [{"id": "vo", "path": "audio/vo.wav", "start": 12, "anchor": None}]
    resolved = timeline.resolve(doc_with([scene_shot("s", start=0)], audio), None, 30)
    assert resolved["audio"] == [{"id": "vo", "path": "audio/vo.wav", "start_frame": 12}]


def test_load_parses_real_yaml(tmp_path: Path) -> None:
    path = tmp_path / "timeline.yaml"
    path.write_text(
        "fps: 30\nresolution: [1920, 1080]\nshots:\n  - id: shot-01\n"
        "    source: {kind: scene, blend: compositions/frames/shot-01.blend, scene: GEN_hook}\n"
        "    start: 0\n    duration: 90\naudio: []\n"
    )
    doc = timeline.parse(path)
    assert len(doc["shots"]) == 1
    assert doc["shots"][0]["id"] == "shot-01"


def test_load_transcript_reads_words(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    path.write_text('{"words": [{"word": "hi", "start": 0.0, "end": 0.2}]}')
    assert timeline.load_transcript(path) == [{"word": "hi", "start": 0.0, "end": 0.2}]


def test_load_transcript_rejects_missing_words_array(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    path.write_text("{}")
    with pytest.raises(SystemExit, match="`words` array"):
        timeline.load_transcript(path)
