#!/usr/bin/env -S uv run --script
# fmt: off
#MISE description="Validate narrative.toml (shot intents)"
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
#USAGE arg "[narrative]" help="Narrative file to validate (default: narrative.toml)"
# fmt: on
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""`narrative.toml` ingest — SPEC.md §5.3 production contract. First-cut schema (no
example given in the spec): shots with intent, target duration, VO/b-roll references.

`vo`/`broll` are validated-by-tolerance only (any string) — they are consumed by M3/M4
scene authoring, not by this ingest.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except OSError as e:
        raise SystemExit(f"reading {path}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"parsing {path}: {e}") from e


def validate(doc: dict[str, Any]) -> list[str]:
    """Pure logic: fail loudly rather than guess (SPEC.md §5.2's anchor-resolution
    philosophy applied here too).
    """
    errors: list[str] = []
    shots = doc.get("shots") or []
    if not shots:
        errors.append("narrative.toml: `shots` is empty")
    seen: set[str] = set()
    for i, shot in enumerate(shots):
        shot_id = str(shot.get("id", ""))
        if not shot_id.strip():
            errors.append(f"shots[{i}]: empty `id`")
        elif shot_id in seen:
            errors.append(f"shots[{i}]: duplicate id {shot_id!r}")
        else:
            seen.add(shot_id)
        if not str(shot.get("intent", "")).strip():
            errors.append(f"shots[{i}] ({shot_id}): empty `intent`")
        d = shot.get("target_duration")
        if d is not None and d <= 0:
            errors.append(f"shots[{i}] ({shot_id}): target_duration must be > 0, got {d}")
    return errors


def parse(path: Path) -> dict[str, Any]:
    doc = load(path)
    errors = validate(doc)
    if errors:
        raise SystemExit("\n".join(errors))
    return doc


def main(argv: list[str]) -> None:
    path = Path(argv[0]) if argv else Path("narrative.toml")
    doc = parse(path)
    print(f"OK: {len(doc.get('shots') or [])} shot(s)")


if __name__ == "__main__":
    main(sys.argv[1:])
