#!/usr/bin/env -S uv run --script
# fmt: off
#MISE description="Validate timeline.toml (shot titles/notes + assembly) and resolve anchors -> frames into .comonteur/timeline.resolved.json"
#MISE dir="{{config_root}}"
#MISE sources=["timeline.toml", "audio/transcript.json"]
#MISE outputs=[".comonteur/timeline.resolved.json"]
#MISE tools={uv = "latest"}
#USAGE flag "--timeline <timeline>" help="Timeline to resolve (default: timeline.toml)"
#USAGE flag "--transcript <transcript>" help="Word timings for anchors (default: audio/transcript.json when present)"
#USAGE flag "-o --out <out>" help="Resolved plan to write (default: .comonteur/timeline.resolved.json)"
# fmt: on
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# Step 1 of assembly. Step 2 runs inside Blender: cmt.reconcile.apply() — the add-on never
# parses a spec file and never reads a transcript.
"""`timeline.toml` → resolved assembly plan — SPEC.md §5.2/§5.3/§10 M4. `timeline.toml` is
the only file this task resolves rather than merely validates: the anchor-relative timing
pipeline ("re-transcribe, re-resolve, done") needs a real word-timing lookup. The output is
plain JSON (integer frame numbers, no more anchors) that `addon/comonteur/reconcile.py`
reads with the stdlib `json` module and turns into VSE strips.

`timeline.toml` also carries each shot's production intent (`title`, `target_duration`,
`vo`, `broll`, `notes`) — formerly a separate `narrative.toml` — since nothing ever derived
one file from the other and splitting them let the two shot lists silently drift apart. A
shot with no `source` yet is a title-only stub: valid, but excluded from the resolved
plan until assembly fields are added.

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


# What `addon/comonteur/reconcile.py` can actually link, and the keys it reads for each. Kept
# here because validation belongs outside Blender: the add-on's input is the resolved plan, so
# a typo'd kind must fail at `mise run comonteur:reconcile`, not halfway through apply().
SOURCE_KINDS = {"scene": ("blend", "scene"), "movie": ("path",)}


def _source_errors(i: int, shot_id: str, source: Any) -> list[str]:
    where = f"shots[{i}] ({shot_id})"
    if not isinstance(source, dict):
        return [f"{where}: `source` is required"]
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        known = ", ".join(sorted(SOURCE_KINDS))
        return [f"{where}: unknown source.kind {kind!r} — expected one of {known}"]
    return [
        f"{where}: source.kind={kind!r} requires `{key}`"
        for key in SOURCE_KINDS[kind]
        if not str(source.get(key, "")).strip()
    ]


def _overlay_cycle(shot_id: str, overlay_targets: dict[str, str]) -> bool:
    """Walks the `overlay_of` chain from `shot_id`; a chain can't be longer than the number
    of shots without repeating a node, so that many steps is enough to prove a cycle.
    """
    seen = {shot_id}
    current = overlay_targets.get(shot_id)
    for _ in range(len(overlay_targets) + 1):
        if current is None:
            return False
        if current in seen:
            return True
        seen.add(current)
        current = overlay_targets.get(current)
    return True


def _notes_error(where: str, notes: Any) -> list[str]:
    if notes is not None and not isinstance(notes, str):
        return [f"{where}: `notes` must be a string"]
    return []


def validate(doc: dict[str, Any]) -> list[str]:
    """Pure logic: fail loudly rather than guess (SPEC.md §5.2/§5.3)."""
    errors: list[str] = []
    errors.extend(_notes_error("timeline.toml", doc.get("notes")))
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

    overlay_targets = {
        str(shot.get("id", "")): str(shot.get("overlay_of"))
        for shot in shots
        if shot.get("overlay_of") is not None
    }

    for i, shot in enumerate(shots):
        shot_id = str(shot.get("id", ""))
        where = f"shots[{i}] ({shot_id})"
        if not str(shot.get("title", "")).strip():
            errors.append(f"{where}: empty `title`")
        target_duration = shot.get("target_duration")
        if target_duration is not None and target_duration <= 0:
            errors.append(f"{where}: target_duration must be > 0, got {target_duration}")
        errors.extend(_notes_error(where, shot.get("notes")))

        if shot.get("source") is None:
            continue  # title-only stub — not yet built, excluded from the resolved plan

        overlay_of = shot.get("overlay_of")
        if overlay_of is None:
            if not _one_of_start_anchor(shot):
                errors.append(
                    f"shots[{i}] ({shot_id}): exactly one of `start`/`anchor` must be set"
                )
            duration = shot.get("duration")
            if duration is None or duration <= 0:
                errors.append(f"shots[{i}] ({shot_id}): duration must be > 0, got {duration}")
        else:
            # `overlay_of` inherits start/duration from its target — `start`/`anchor`/
            # `duration` become optional overrides, not requirements.
            if shot.get("start") is not None and shot.get("anchor") is not None:
                errors.append(f"shots[{i}] ({shot_id}): only one of `start`/`anchor` may be set")
            duration = shot.get("duration")
            if duration is not None and duration <= 0:
                errors.append(f"shots[{i}] ({shot_id}): duration must be > 0, got {duration}")
            if str(overlay_of) == shot_id:
                errors.append(f"shots[{i}] ({shot_id}): overlay_of cannot reference itself")
            elif str(overlay_of) not in shot_ids:
                errors.append(
                    f"shots[{i}] ({shot_id}): overlay_of {overlay_of!r} is not a known shot id"
                )
            elif _overlay_cycle(shot_id, overlay_targets):
                errors.append(f"shots[{i}] ({shot_id}): overlay_of forms a cycle")
        errors.extend(_source_errors(i, shot_id, shot.get("source")))
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


def _resolve_shot(
    shot: dict[str, Any],
    shot_id: str,
    transcript: list[dict[str, Any]] | None,
    fps: int,
    inherited_start_frame: int | None = None,
    inherited_duration_frames: int | None = None,
) -> dict[str, Any]:
    transition = shot.get("transition")
    resolved_transition = None
    transition_frames = 0
    if transition is not None:
        transition_frames = _round_half_away(float(transition.get("duration", 0.0)) * fps)
        resolved_transition = {
            "type": transition.get("type"),
            # Seconds, like an anchor's offset — both are timed relative to the
            # transcript/audio, not the edit grid, so both convert at resolve time.
            "duration_frames": transition_frames,
        }
    if shot.get("start") is not None or shot.get("anchor") is not None:
        # A shot with a transition needs to actually overlap the previous shot for the CROSS
        # effect to have something to blend across — shift this shot's own start earlier by
        # the transition length and extend its duration to match, so its authored `start`
        # stays the frame where the previous shot's untouched footage ends. Only this shot
        # moves: shots authored back-to-back (next start == previous start + duration, the
        # documented convention) then overlap the previous shot by exactly the transition's
        # length without the previous shot needing any adjustment at all.
        start_frame = resolve_position(shot_id, shot, transcript, fps) - transition_frames
    else:
        assert inherited_start_frame is not None  # validate() requires start/anchor/overlay_of
        start_frame = inherited_start_frame
    duration_frames = shot.get("duration")
    if duration_frames is not None:
        duration_frames = duration_frames + transition_frames
    else:
        duration_frames = inherited_duration_frames
    result = {
        "id": shot_id,
        "source": shot.get("source"),
        "start_frame": start_frame,
        "duration_frames": duration_frames,
        "in_frame": shot.get("in"),
        "transition": resolved_transition,
    }
    overlay_of = shot.get("overlay_of")
    if overlay_of is not None:
        result["overlay_of"] = str(overlay_of)
    return result


def resolve(
    doc: dict[str, Any], transcript: list[dict[str, Any]] | None, fps: int
) -> dict[str, Any]:
    """`timeline.toml` (already validated) + an optional transcript → a plan with plain
    integer frame numbers and no more anchors, ready for `reconcile.py` to apply.

    `overlay_of` shots are resolved in a second pass, once their target is resolved, so
    they can inherit the target's `start_frame`/`duration_frames` when they don't set
    their own — a target can itself be an overlay, so this repeats until nothing left
    makes progress (`validate()` already rejects cycles, so that always terminates).
    """
    shots_in = list(doc.get("shots") or [])
    resolved_by_id: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    for shot in shots_in:
        if shot.get("source") is None:
            continue  # title-only stub — not yet built, not part of the assembly
        shot_id = str(shot.get("id", ""))
        if shot.get("overlay_of") is None:
            resolved_by_id[shot_id] = _resolve_shot(shot, shot_id, transcript, fps)
        else:
            pending.append(shot)

    while pending:
        still_pending = []
        progressed = False
        for shot in pending:
            target = resolved_by_id.get(str(shot.get("overlay_of")))
            if target is None:
                still_pending.append(shot)
                continue
            shot_id = str(shot.get("id", ""))
            resolved_by_id[shot_id] = _resolve_shot(
                shot,
                shot_id,
                transcript,
                fps,
                target["start_frame"],
                target["duration_frames"],
            )
            progressed = True
        if not progressed:
            raise SystemExit("overlay_of cycle detected (should have failed validate())")
        pending = still_pending

    shots = [
        resolved_by_id[sid] for s in shots_in if (sid := str(s.get("id", ""))) in resolved_by_id
    ]

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

    encode = doc.get("encode") or {}
    return {
        "fps": doc.get("fps"),
        "resolution": doc.get("resolution"),
        "video_codec": encode.get("video_codec", "H265"),
        "video_container": encode.get("video_container"),
        "audio_codec": encode.get("audio_codec"),
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
