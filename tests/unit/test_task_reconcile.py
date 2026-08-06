"""Pure-logic tests for the `comonteur:reconcile` task script — timeline.toml validation
(assembly *and* shot title/notes, formerly `narrative.toml`/`ingest_narrative.py`) and
anchor→frame resolution (SPEC.md §5.2/§5.3/§10 M4).

Ported from cli/src/timeline.rs's #[cfg(test)] module when the Rust CLI was dissolved into
mise tasks. This is the logic that lost the Rust compiler, so it carries the most coverage.

Named test_task_reconcile.py to stay distinct from test_reconcile.py, which covers
addon/comonteur/reconcile.py — the Blender-side consumer of this script's JSON output.
"""

from pathlib import Path
from typing import Any

import pytest
from _tasks import load

pytestmark = pytest.mark.task

timeline = load("reconcile")


def word(w: str, start: float, end: float) -> dict[str, Any]:
    return {"word": w, "start": start, "end": end}


def scene_shot(
    shot_id: str,
    start: int | None = None,
    anchor: dict[str, Any] | None = None,
    duration: int | None = 90,
    overlay_of: str | None = None,
    title: str = "test title",
) -> dict[str, Any]:
    return {
        "id": shot_id,
        "title": title,
        "source": {
            "kind": "scene",
            "blend": "shots/shot-01.blend",
            "scene": "GEN_hook",
        },
        "start": start,
        "anchor": anchor,
        "duration": duration,
        "in": None,
        "transition": None,
        "overlay_of": overlay_of,
    }


def doc_with(
    shots: list[dict[str, Any]],
    audio: list[dict[str, Any]] | None = None,
    background: list[dict[str, Any]] | None = None,
) -> dict:
    return {
        "fps": 30,
        "resolution": [1920, 1080],
        "shots": shots,
        "audio": audio or [],
        "background": background or [],
    }


def bg_entry(
    bg_id: str,
    source: dict[str, Any] | None = None,
    start: int | None = None,
    anchor: dict[str, Any] | None = None,
    duration: int | None = 90,
) -> dict[str, Any]:
    return {
        "id": bg_id,
        "source": source or {"kind": "color", "value": "#1a1a1a"},
        "start": start,
        "anchor": anchor,
        "duration": duration,
    }


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


def test_resolve_shifts_transitioned_shot_earlier_and_extends_duration() -> None:
    # 0.5s @ 30fps = 15 frames — the shot must start 15 frames before its authored cut
    # point and last 15 frames longer, so it overlaps the previous shot for the crossfade.
    shot = scene_shot("shot-02", start=90, duration=120)
    shot["transition"] = {"type": "crossfade", "duration": 0.5}
    resolved = timeline.resolve(doc_with([shot]), None, 30)["shots"][0]
    assert resolved["start_frame"] == 75
    assert resolved["duration_frames"] == 135


def test_resolve_shot_without_transition_is_unshifted() -> None:
    shot = scene_shot("shot-01", start=90, duration=120)
    resolved = timeline.resolve(doc_with([shot]), None, 30)["shots"][0]
    assert resolved["start_frame"] == 90
    assert resolved["duration_frames"] == 120


def test_resolve_transition_shift_composes_with_anchor() -> None:
    transcript = [word("data", 1.0, 1.4)]
    anchor = {"word": "data", "occurrence": 1, "offset": 0.0}
    shot = scene_shot("shot-02", anchor=anchor, duration=120)
    shot["transition"] = {"type": "crossfade", "duration": 0.5}
    resolved = timeline.resolve(doc_with([shot]), transcript, 30)["shots"][0]
    # anchor resolves to 1.0s * 30fps = 30, shifted 15 frames earlier by the transition
    assert resolved["start_frame"] == 15
    assert resolved["duration_frames"] == 135


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


def test_resolve_defaults_encode_when_absent() -> None:
    doc = doc_with([scene_shot("shot-01", start=0)])
    resolved = timeline.resolve(doc, None, 30)
    assert resolved["video_codec"] == "H265"
    assert resolved["video_container"] is None
    assert resolved["audio_codec"] is None


def test_resolve_passes_through_encode_when_given() -> None:
    doc = doc_with([scene_shot("shot-01", start=0)])
    doc["encode"] = {"video_codec": "AV1", "video_container": "WEBM", "audio_codec": "OPUS"}
    resolved = timeline.resolve(doc, None, 30)
    assert resolved["video_codec"] == "AV1"
    assert resolved["video_container"] == "WEBM"
    assert resolved["audio_codec"] == "OPUS"


def test_load_parses_real_toml(tmp_path: Path) -> None:
    path = tmp_path / "timeline.toml"
    path.write_text(
        'fps = 30\nresolution = [1920, 1080]\n\n[[shots]]\nid = "shot-01"\n'
        'title = "Hook"\n'
        'source = {kind = "scene", blend = "shots/shot-01.blend", '
        'scene = "GEN_hook"}\n'
        "start = 0\nduration = 90\n"
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


def test_overlay_of_shot_needs_no_start_or_duration() -> None:
    doc = doc_with(
        [
            scene_shot("shot-01", start=0, duration=90),
            scene_shot("overlay-01", duration=None, overlay_of="shot-01"),
        ]
    )
    assert timeline.validate(doc) == []


def test_overlay_of_unknown_target_errors() -> None:
    doc = doc_with([scene_shot("overlay-01", duration=None, overlay_of="does-not-exist")])
    assert any("not a known shot id" in e for e in timeline.validate(doc))


def test_overlay_of_self_reference_errors() -> None:
    doc = doc_with([scene_shot("shot-01", duration=None, overlay_of="shot-01")])
    assert any("cannot reference itself" in e for e in timeline.validate(doc))


def test_overlay_of_cycle_errors() -> None:
    doc = doc_with(
        [
            scene_shot("a", duration=None, overlay_of="b"),
            scene_shot("b", duration=None, overlay_of="a"),
        ]
    )
    assert any("forms a cycle" in e for e in timeline.validate(doc))


def test_overlay_of_both_start_and_anchor_errors() -> None:
    anchor = {"word": "hi", "occurrence": 1, "offset": 0.0}
    doc = doc_with(
        [
            scene_shot("shot-01", start=0, duration=90),
            scene_shot("overlay-01", start=0, anchor=anchor, duration=None, overlay_of="shot-01"),
        ]
    )
    assert any("only one of" in e for e in timeline.validate(doc))


def test_resolve_overlay_inherits_start_and_duration_from_target() -> None:
    doc = doc_with(
        [
            scene_shot("shot-01", start=10, duration=90),
            scene_shot("overlay-01", duration=None, overlay_of="shot-01"),
        ]
    )
    resolved = timeline.resolve(doc, None, 30)
    target = next(s for s in resolved["shots"] if s["id"] == "shot-01")
    overlay = next(s for s in resolved["shots"] if s["id"] == "overlay-01")
    assert overlay["start_frame"] == target["start_frame"] == 10
    assert overlay["duration_frames"] == target["duration_frames"] == 90
    assert overlay["overlay_of"] == "shot-01"


def test_resolve_overlay_explicit_start_and_duration_override_inheritance() -> None:
    doc = doc_with(
        [
            scene_shot("shot-01", start=10, duration=90),
            scene_shot("overlay-01", start=20, duration=30, overlay_of="shot-01"),
        ]
    )
    overlay = timeline.resolve(doc, None, 30)["shots"][1]
    assert overlay["start_frame"] == 20
    assert overlay["duration_frames"] == 30


def test_resolve_overlay_of_overlay_chains_inheritance() -> None:
    doc = doc_with(
        [
            scene_shot("shot-01", start=10, duration=90),
            scene_shot("overlay-a", duration=None, overlay_of="shot-01"),
            scene_shot("overlay-b", duration=None, overlay_of="overlay-a"),
        ]
    )
    resolved = timeline.resolve(doc, None, 30)
    overlay_b = next(s for s in resolved["shots"] if s["id"] == "overlay-b")
    assert overlay_b["start_frame"] == 10
    assert overlay_b["duration_frames"] == 90


# Shot title (formerly narrative.toml/ingest_narrative.py — absorbed here since nothing
# ever derived one file from the other, so nothing caught the two shot lists drifting apart).


def test_missing_title_errors() -> None:
    doc = doc_with([scene_shot("shot-01", start=0, title="  ")])
    assert any("empty `title`" in e for e in timeline.validate(doc))


def test_non_positive_target_duration_errors() -> None:
    shot = scene_shot("shot-01", start=0)
    shot["target_duration"] = 0
    assert any("target_duration" in e for e in timeline.validate(doc_with([shot])))


def test_notes_must_be_a_string() -> None:
    shot = scene_shot("shot-01", start=0)
    shot["notes"] = 123
    assert any("`notes` must be a string" in e for e in timeline.validate(doc_with([shot])))


def test_doc_level_notes_must_be_a_string() -> None:
    doc = doc_with([scene_shot("shot-01", start=0)])
    doc["notes"] = 123
    assert any("`notes` must be a string" in e for e in timeline.validate(doc))


def test_notes_content_is_preserved_verbatim() -> None:
    shot = scene_shot("shot-01", start=0)
    shot["notes"] = "beat: anxiety | persuasion: Pain validation\nlink: https://example.com"
    doc = doc_with([shot])
    doc["notes"] = "doc-level creative direction"
    assert timeline.validate(doc) == []
    assert doc["shots"][0]["notes"] == shot["notes"]
    assert doc["notes"] == "doc-level creative direction"


def test_shot_with_no_source_is_a_valid_title_only_stub() -> None:
    doc = doc_with([{"id": "shot-99", "title": "Not built yet.", "target_duration": 5.0}])
    assert timeline.validate(doc) == []


def test_title_only_stub_is_excluded_from_resolved_output() -> None:
    doc = doc_with(
        [
            scene_shot("shot-01", start=0),
            {"id": "shot-99", "title": "Not built yet.", "target_duration": 5.0},
        ]
    )
    resolved = timeline.resolve(doc, None, 30)
    assert [s["id"] for s in resolved["shots"]] == ["shot-01"]


# `[[background]]` — sequential, non-overlapping segments on a channel below all shots.


def test_background_absent_resolves_to_empty_list() -> None:
    doc = doc_with([scene_shot("shot-01", start=0)])
    assert timeline.resolve(doc, None, 30)["background"] == []


def test_valid_background_list_has_no_errors() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[bg_entry("bg-01", start=0, duration=90)],
    )
    assert timeline.validate(doc) == []


def test_background_empty_id_errors() -> None:
    doc = doc_with([scene_shot("shot-01", start=0)], background=[bg_entry("", start=0)])
    assert any("empty `id`" in e for e in timeline.validate(doc))


def test_background_duplicate_id_errors() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[
            bg_entry("bg-01", start=0, duration=90),
            bg_entry("bg-01", start=90),
        ],
    )
    assert any("duplicate id" in e for e in timeline.validate(doc))


def test_background_id_colliding_with_shot_id_errors() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[bg_entry("shot-01", start=0)],
    )
    assert any("collides with a shot/audio id" in e for e in timeline.validate(doc))


def test_background_missing_duration_on_non_last_entry_errors() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[
            bg_entry("bg-01", start=0, duration=None),
            bg_entry("bg-02", start=90, duration=90),
        ],
    )
    assert any("duration is required" in e for e in timeline.validate(doc))


def test_background_last_entry_may_omit_duration() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[
            bg_entry("bg-01", start=0, duration=90),
            bg_entry("bg-02", start=90, duration=None),
        ],
    )
    assert timeline.validate(doc) == []


def test_background_out_of_order_start_errors() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[
            bg_entry("bg-01", start=90, duration=30),
            bg_entry("bg-02", start=0, duration=30),
        ],
    )
    assert any("before the previous entry" in e for e in timeline.validate(doc))


def test_background_unknown_source_kind_errors() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[bg_entry("bg-01", source={"kind": "solid"}, start=0)],
    )
    assert any("unknown source.kind" in e for e in timeline.validate(doc))


def test_background_color_requires_hex_value() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[bg_entry("bg-01", source={"kind": "color", "value": "red"}, start=0)],
    )
    assert any("must be `#rrggbb`" in e for e in timeline.validate(doc))


def test_background_all_kinds_are_valid() -> None:
    kinds = [
        {"kind": "color", "value": "#00ff00"},
        {"kind": "image", "path": "assets/bg.png"},
        {"kind": "movie", "path": "assets/bg.mp4"},
        {"kind": "scene", "blend": "shots/bg.blend", "scene": "GEN_bg"},
    ]
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[
            bg_entry(f"bg-{i}", source=k, start=i * 30, duration=30) for i, k in enumerate(kinds)
        ],
    )
    assert timeline.validate(doc) == []


def test_resolve_background_color_converts_hex_to_float_rgb() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[bg_entry("bg-01", source={"kind": "color", "value": "#ff0000"}, start=0)],
    )
    resolved = timeline.resolve(doc, None, 30)["background"][0]
    assert resolved["source"]["value"] == [1.0, 0.0, 0.0]


def test_resolve_background_last_entry_fills_to_frame_end() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0, duration=300)],
        background=[bg_entry("bg-01", start=0, duration=None)],
    )
    resolved = timeline.resolve(doc, None, 30)["background"][0]
    assert resolved["start_frame"] == 0
    assert resolved["duration_frames"] == 300


def test_resolve_background_passes_through_non_color_kinds() -> None:
    doc = doc_with(
        [scene_shot("shot-01", start=0)],
        background=[
            bg_entry(
                "bg-01",
                source={"kind": "scene", "blend": "shots/bg.blend", "scene": "GEN_bg"},
                start=0,
                duration=90,
            )
        ],
    )
    resolved = timeline.resolve(doc, None, 30)["background"][0]
    assert resolved["source"] == {"kind": "scene", "blend": "shots/bg.blend", "scene": "GEN_bg"}
