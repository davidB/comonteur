#!/usr/bin/env -S uv run --script
#MISE description="Validate narrative.yaml (shot intents)"
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""`narrative.yaml` ingest — SPEC.md §5.3 production contract. First-cut schema (no
example given in the spec): shots with intent, target duration, VO/b-roll references.

`vo`/`broll` are validated-by-tolerance only (any string) — they are consumed by M3/M4
scene authoring, not by this ingest.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def load(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except OSError as e:
        raise SystemExit(f"reading {path}: {e}") from e
    except yaml.YAMLError as e:
        raise SystemExit(f"parsing {path}: {e}") from e
    if not isinstance(doc, dict):
        raise SystemExit(f"parsing {path}: expected a mapping at the top level")
    return doc


def validate(doc: dict[str, Any]) -> list[str]:
    """Pure logic: fail loudly rather than guess (SPEC.md §5.2's anchor-resolution
    philosophy applied here too).
    """
    errors: list[str] = []
    shots = doc.get("shots") or []
    if not shots:
        errors.append("narrative.yaml: `shots` is empty")
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
    path = Path(argv[0]) if argv else Path("narrative.yaml")
    doc = parse(path)
    print(f"OK: {len(doc.get('shots') or [])} shot(s)")


if __name__ == "__main__":
    main(sys.argv[1:])
