#!/usr/bin/env -S uv run --script
# fmt: off
#MISE description="Convert .woff/.woff2 fonts to .ttf/.otf so Blender can load them"
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
#USAGE arg "[paths]" var=#true help="Font files or directories to scan (default: assets/fonts)"
#USAGE flag "-f --force" help="Reconvert even if the .ttf/.otf is up to date"
# fmt: on
# /// script
# requires-python = ">=3.11"
# dependencies = ["fonttools[woff]>=4.55"]
# ///
"""Blender's font loader reads sfnt only — a web-packaged `.woff`/`.woff2` silently fails
to resolve. fontTools unwraps both back to the sfnt they contain (no re-encoding: the
outlines are untouched, only the WOFF container is dropped).

The one task script with a dependency (CLAUDE.md): unwrapping WOFF2 needs a Brotli decoder,
which the stdlib does not have. `uvx` cannot do it either — `fonttools ttLib.woff2
decompress` covers woff2 alone, and plain `.woff` has no CLI verb short of a `ttx`
round-trip. The `[woff]` extra pulls brotli + zopfli.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import TaskError, die, ok, skip, step
from fontTools.ttLib import TTFont

SUFFIXES = (".woff", ".woff2")
DEFAULT_DIR = Path("assets/fonts")


def outputs(src: Path) -> list[Path]:
    """Both candidate names — which one fontTools picks is only known after reading the font."""
    return [src.with_suffix(ext) for ext in (".ttf", ".otf")]


def collect(paths: list[Path], *, force: bool) -> list[Path]:
    """Web fonts under `paths` that still need converting. Directories are scanned recursively."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found += sorted(p for p in path.rglob("*") if p.suffix.lower() in SUFFIXES)
        elif path.suffix.lower() in SUFFIXES:
            found.append(path)
        elif not path.exists():
            raise TaskError(f"{path} does not exist")
        else:
            raise TaskError(f"{path} is not a .woff/.woff2 font")
    if force:
        return found
    fresh = []
    for src in found:
        done = [o for o in outputs(src) if o.exists() and o.stat().st_mtime >= src.stat().st_mtime]
        if done:
            skip(f"{src.name} → {done[0].name} (up to date)")
        else:
            fresh.append(src)
    return fresh


def convert(src: Path) -> Path:
    """Drop the WOFF container. Extension follows sfntVersion: CFF outlines are .otf, glyf .ttf."""
    font = TTFont(src)
    font.flavor = None
    out = src.with_suffix(".otf" if font.sfntVersion == "OTTO" else ".ttf")
    font.save(out)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Convert web fonts to Blender-loadable sfnt")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("-f", "--force", action="store_true")
    args = parser.parse_args(argv)

    paths: list[Path] = args.paths or [DEFAULT_DIR]
    if not any(p.exists() for p in paths):
        raise TaskError(
            f"no such path: {', '.join(str(p) for p in paths)}",
            "pass the font files or the directory holding them",
        )
    todo = collect(paths, force=args.force)
    if not todo:
        step("nothing to convert")
        return 0
    step(f"converting {len(todo)} font(s)")
    for src in todo:
        ok(f"{src.name} → {convert(src).name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
