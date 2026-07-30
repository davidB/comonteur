#!/usr/bin/env -S uv run --script
#MISE description="Normalize word-level timing into captions/vo.json"
#USAGE arg "<input>" help="JSON with word-level timing: Whisper output, or TTS timing marks"
#USAGE flag "-k --kind <kind>" help="whisper (ASR, human-recorded VO) or tts (synthesis marks)" default="whisper" {
#USAGE   choices "whisper" "tts"
#USAGE }
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# ///
# Prefer `tts` whenever the audio was synthesized — timing marks are exact by construction
# and avoid ASR error on proper nouns and technical terms.
# No sources/outputs: the input path is an argument, so mise cannot know it in advance.
"""`captions/*.json` ingest — SPEC.md §5.3. Word-level timing, normalized from either
TTS provider timing marks (exact by construction) or Whisper word-level output (primary
path for human-recorded VO, not a degraded fallback). Normalization only — comonteur does
not invoke `whisper` itself; per §5.7 that's an existing external pipeline
(`vo:transcribe`) whose `transcript.json` output this module consumes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

WORD_KEYS = ("word", "text")
START_KEYS = ("start", "start_time")
END_KEYS = ("end", "end_time")

OUT_PATH = Path("captions/vo.json")


def _first_str(v: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        val = v.get(k)
        if isinstance(val, str):
            return val
    return None


def _first_float(v: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for k in keys:
        val = v.get(k)
        # bool is an int subclass in Python; serde's as_f64 would not accept it either.
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return float(val)
    return None


def normalize_words(raw: list[Any]) -> list[dict[str, Any]]:
    """Pure logic: tolerant of common key aliases (`word`/`text`, `start`/`start_time`,
    `end`/`end_time`) since neither Whisper's nor any given TTS provider's exact wire
    format is pinned by the spec. Entries missing any field are skipped.
    """
    words: list[dict[str, Any]] = []
    for v in raw:
        if not isinstance(v, dict):
            continue
        word = _first_str(v, WORD_KEYS)
        start = _first_float(v, START_KEYS)
        end = _first_float(v, END_KEYS)
        if word is None or start is None or end is None:
            continue
        words.append({"word": word, "start": start, "end": end})
    return words


def from_whisper_json(v: Any) -> list[dict[str, Any]]:
    """openai-whisper's documented `segments[].words[]` shape — a concrete, verifiable
    format. This is what a project's existing `vo:transcribe` task already produces.
    """
    segments = v.get("segments") if isinstance(v, dict) else None
    raw: list[Any] = []
    for seg in segments or []:
        if isinstance(seg, dict) and isinstance(seg.get("words"), list):
            raw.extend(seg["words"])
    return normalize_words(raw)


def from_timing_marks(v: Any) -> list[dict[str, Any]]:
    """Generic normalizer for upstream-supplied TTS provider timing marks. No specific
    vendor is named anywhere in the spec, so this is a tolerant first-cut shape — a
    top-level array, or `{"words": [...]}` / `{"alignment": [...]}` — not a vendor
    contract.
    """
    if isinstance(v, list):
        return normalize_words(v)
    if isinstance(v, dict):
        for key in ("words", "alignment"):
            if isinstance(v.get(key), list):
                return normalize_words(v[key])
    return []


def main(argv: list[str]) -> None:
    # mise's #USAGE header exports usage_*; fall back to argv for direct-by-path runs (§8.2).
    input_path = os.environ.get("usage_input")
    kind = os.environ.get("usage_kind")
    args = [a for a in argv if not a.startswith("-")]
    if not input_path:
        if not args:
            raise SystemExit("usage: ingest_captions.py <input.json> [--kind whisper|tts]")
        input_path = args[0]
    if not kind:
        kind = "whisper"
        for i, a in enumerate(argv):
            if a in ("-k", "--kind") and i + 1 < len(argv):
                kind = argv[i + 1]
            elif a.startswith("--kind="):
                kind = a.split("=", 1)[1]
    if kind not in ("whisper", "tts"):
        raise SystemExit(f"--kind must be whisper or tts, got {kind!r}")

    src = Path(input_path)
    try:
        with src.open(encoding="utf-8") as f:
            v = json.load(f)
    except OSError as e:
        raise SystemExit(f"reading {src}: {e}") from e
    except json.JSONDecodeError as e:
        raise SystemExit(f"parsing {src}: {e}") from e

    words = from_whisper_json(v) if kind == "whisper" else from_timing_marks(v)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"words": words}, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(words)} word(s))")


if __name__ == "__main__":
    main(sys.argv[1:])
