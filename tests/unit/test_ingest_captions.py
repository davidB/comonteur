"""Pure-logic tests for the `comonteur:ingest_captions` task script (SPEC.md §5.3).

Ported from cli/src/captions.rs's #[cfg(test)] module when the Rust CLI was dissolved into
mise tasks.
"""

from _tasks import load

captions = load("ingest_captions")


def test_normalize_words_handles_key_aliases() -> None:
    raw = [
        {"word": "hello", "start": 0.0, "end": 0.4},
        {"text": "world", "start_time": 0.4, "end_time": 0.9},
    ]
    assert captions.normalize_words(raw) == [
        {"word": "hello", "start": 0.0, "end": 0.4},
        {"word": "world", "start": 0.4, "end": 0.9},
    ]


def test_normalize_words_skips_entries_missing_fields() -> None:
    raw = [{"word": "orphan"}, {"word": "ok", "start": 1.0, "end": 1.2}]
    assert len(captions.normalize_words(raw)) == 1


def test_normalize_words_coerces_int_timings_to_float() -> None:
    words = captions.normalize_words([{"word": "hi", "start": 1, "end": 2}])
    assert words == [{"word": "hi", "start": 1.0, "end": 2.0}]
    assert isinstance(words[0]["start"], float)


def test_from_whisper_json_flattens_segments() -> None:
    doc = {
        "segments": [
            {
                "words": [
                    {"word": "hello", "start": 0.0, "end": 0.4},
                    {"word": "there", "start": 0.4, "end": 0.8},
                ]
            },
            {"words": [{"word": "world", "start": 1.0, "end": 1.5}]},
        ]
    }
    words = captions.from_whisper_json(doc)
    assert len(words) == 3
    assert words[2]["word"] == "world"


def test_from_whisper_json_tolerates_missing_segments() -> None:
    assert captions.from_whisper_json({}) == []


def test_from_timing_marks_accepts_top_level_array() -> None:
    assert len(captions.from_timing_marks([{"word": "hi", "start": 0.0, "end": 0.2}])) == 1


def test_from_timing_marks_accepts_words_wrapper() -> None:
    doc = {"words": [{"word": "hi", "start": 0.0, "end": 0.2}]}
    assert len(captions.from_timing_marks(doc)) == 1


def test_from_timing_marks_accepts_alignment_wrapper() -> None:
    doc = {"alignment": [{"text": "hi", "start_time": 0.0, "end_time": 0.2}]}
    assert len(captions.from_timing_marks(doc)) == 1


def test_from_timing_marks_returns_empty_on_unknown_shape() -> None:
    assert captions.from_timing_marks({"nope": []}) == []
