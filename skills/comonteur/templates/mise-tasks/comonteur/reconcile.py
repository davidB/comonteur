#!/usr/bin/env -S uv run --script
#MISE description="Resolve timeline.toml (anchors -> frames) into .comonteur/timeline.resolved.json"
#MISE dir="{{config_root}}"
#MISE sources=["timeline.toml", "audio/transcript.json"]
#MISE outputs=[".comonteur/timeline.resolved.json"]
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# Step 1 of assembly. Step 2 runs inside Blender: cmt.reconcile.apply() — the add-on never
# parses a spec file and never reads a transcript.
"""`timeline.toml` → resolved assembly plan — SPEC.md §5.2/§10 M4. `timeline.toml` is the
only file this task resolves rather than merely validates: the anchor-relative timing
pipeline ("re-transcribe, re-resolve, done") needs a real word-timing lookup. The output is
plain JSON (integer frame numbers, no more anchors) that `addon/comonteur/reconcile.py`
reads with the stdlib `json` module and turns into VSE strips.

The add-on never imports this script and never parses a spec file: parsing, validation and
anchor resolution are this side's job, and Blender's bundled interpreter cannot see a uv
environment anyway. This side emits JSON; that side reads it.
"""

from __future__ import annotations

import json
import math
import sys
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_TIMELINE = Path("timeline.toml")
DEFAULT_TRANSCRIPT = Path("audio/transcript.json")
DEFAULT_OUT = Path(".comonteur/timeline.resolved.json")


def _round_half_away(x: float) -> int:
    """Rust's `f64::round` rounds half away from zero; Python's built-in `round` is
    banker's rounding, so 0.5 would land on 0 instead of 1. Frame numbers must match the
    previous implementation exactly.
    """
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def load(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except OSError as e:
        raise SystemExit(f"reading {path}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"parsing {path}: {e}") from e


def load_transcript(path: Path) -> list[dict[str, Any]]:
    """Reads the `{"words": [...]}` document that the captions ingest wrote. This is the
    only coupling between the two tasks, and it is a data shape, not shared code.
    """
    try:
        with path.open(encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        raise SystemExit(f"reading {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise SystemExit(f"parsing {path}: {e}") from e
    words = doc.get("words") if isinstance(doc, dict) else None
    if not isinstance(words, list):
        raise SystemExit(f"parsing {path}: expected a `words` array")
    return words


def _one_of_start_anchor(entry: dict[str, Any]) -> bool:
    return (entry.get("start") is None) != (entry.get("anchor") is None)


def validate(doc: dict[str, Any]) -> list[str]:
    """Pure logic: fail loudly rather than guess (SPEC.md §5.2)."""
    errors: list[str] = []
    shots = doc.get("shots") or []
    audio = doc.get("audio") or []
    if not shots:
        errors.append("timeline.toml: `shots` is empty")

    shot_ids: set[str] = set()
    for i, shot in enumerate(shots):
        shot_id = str(shot.get("id", ""))
        if not shot_id.strip():
            errors.append(f"shots[{i}]: empty `id`")
        elif shot_id in shot_ids:
            errors.append(f"shots[{i}]: duplicate id {shot_id!r}")
        else:
            shot_ids.add(shot_id)
        if not _one_of_start_anchor(shot):
            errors.append(f"shots[{i}] ({shot_id}): exactly one of `start`/`anchor` must be set")
        duration = shot.get("duration")
        if duration is None or duration <= 0:
            errors.append(f"shots[{i}] ({shot_id}): duration must be > 0, got {duration}")
        anchor = shot.get("anchor")
        if anchor is not None:
            occurrence = anchor.get("occurrence", 0)
            if occurrence < 1:
                errors.append(
                    f"shots[{i}] ({shot_id}): anchor.occurrence must be >= 1, got {occurrence}"
                )

    audio_ids: set[str] = set()
    for i, track in enumerate(audio):
        track_id = str(track.get("id", ""))
        if not track_id.strip():
            errors.append(f"audio[{i}]: empty `id`")
        elif track_id in audio_ids:
            errors.append(f"audio[{i}]: duplicate id {track_id!r}")
        else:
            audio_ids.add(track_id)
        if not _one_of_start_anchor(track):
            errors.append(f"audio[{i}] ({track_id}): exactly one of `start`/`anchor` must be set")

    return errors


def parse(path: Path) -> dict[str, Any]:
    doc = load(path)
    errors = validate(doc)
    if errors:
        raise SystemExit("\n".join(errors))
    return doc


def resolve_anchor(anchor: dict[str, Any], words: list[dict[str, Any]], fps: int) -> int:
    """Find the anchor word's Nth (1-indexed) occurrence in the transcript,
    case-insensitive, and convert `word.start + offset` seconds to a frame number. Fails
    loudly (§5.2: "fail loudly, never silently") if the word or occurrence isn't there —
    that's the "script drifted from the recording" signal, not something to guess past.
    """
    target = str(anchor.get("word", ""))
    matches = [w for w in words if str(w.get("word", "")).lower() == target.lower()]
    occurrence = int(anchor.get("occurrence", 1))
    idx = max(occurrence - 1, 0)
    if idx >= len(matches):
        raise SystemExit(
            f"anchor word {target!r} occurrence {occurrence} not found "
            f"({len(matches)} occurrence(s) in transcript)"
        )
    seconds = float(matches[idx]["start"]) + float(anchor.get("offset", 0.0))
    return _round_half_away(seconds * fps)


def resolve_position(
    entry_id: str,
    entry: dict[str, Any],
    transcript: list[dict[str, Any]] | None,
    fps: int,
) -> int:
    start, anchor = entry.get("start"), entry.get("anchor")
    if start is not None and anchor is None:
        return int(start)
    if start is None and anchor is not None:
        if transcript is None:
            raise SystemExit(f"{entry_id!r} uses an anchor but no transcript was provided")
        try:
            return resolve_anchor(anchor, transcript, fps)
        except SystemExit as e:
            raise SystemExit(f"resolving anchor for {entry_id!r}: {e}") from e
    raise SystemExit(f"{entry_id!r}: exactly one of start/anchor must be set")


def resolve(
    doc: dict[str, Any], transcript: list[dict[str, Any]] | None, fps: int
) -> dict[str, Any]:
    """`timeline.toml` (already validated) + an optional transcript → a plan with plain
    integer frame numbers and no more anchors, ready for `reconcile.py` to apply.
    """
    shots: list[dict[str, Any]] = []
    for shot in doc.get("shots") or []:
        shot_id = str(shot.get("id", ""))
        transition = shot.get("transition")
        resolved_transition = None
        if transition is not None:
            resolved_transition = {
                "type": transition.get("type"),
                # Seconds, like an anchor's offset — both are timed relative to the
                # transcript/audio, not the edit grid, so both convert at resolve time.
                "duration_frames": _round_half_away(float(transition.get("duration", 0.0)) * fps),
            }
        shots.append(
            {
                "id": shot_id,
                "source": shot.get("source"),
                "start_frame": resolve_position(shot_id, shot, transcript, fps),
                "duration_frames": shot.get("duration"),
                "in_frame": shot.get("in"),
                "transition": resolved_transition,
            }
        )

    audio: list[dict[str, Any]] = []
    for track in doc.get("audio") or []:
        track_id = str(track.get("id", ""))
        audio.append(
            {
                "id": track_id,
                "path": track.get("path"),
                "start_frame": resolve_position(track_id, track, transcript, fps),
            }
        )

    return {
        "fps": doc.get("fps"),
        "resolution": doc.get("resolution"),
        "shots": shots,
        "audio": audio,
    }


def main(argv: list[str]) -> None:
    timeline_path = DEFAULT_TIMELINE
    out_path = DEFAULT_OUT
    transcript_path: Path | None = None
    for i, a in enumerate(argv):
        if a == "--timeline" and i + 1 < len(argv):
            timeline_path = Path(argv[i + 1])
        elif a in ("-o", "--out") and i + 1 < len(argv):
            out_path = Path(argv[i + 1])
        elif a == "--transcript" and i + 1 < len(argv):
            transcript_path = Path(argv[i + 1])

    doc = parse(timeline_path)
    # Required only if a shot or audio entry uses `anchor` instead of an absolute `start`.
    if transcript_path is None and DEFAULT_TRANSCRIPT.is_file():
        transcript_path = DEFAULT_TRANSCRIPT
    words = load_transcript(transcript_path) if transcript_path is not None else None

    fps = doc.get("fps")
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        raise SystemExit(f"timeline.toml: `fps` must be a positive integer, got {fps!r}")

    resolved = resolve(doc, words, fps)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resolved, indent=2), encoding="utf-8")
    print(
        f"wrote {out_path} ({len(resolved['shots'])} shot(s), "
        f"{len(resolved['audio'])} audio track(s))"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
