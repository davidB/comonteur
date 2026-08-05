#!/usr/bin/env -S uv run --script
# fmt: off
#MISE description="Convert .woff/.woff2 fonts to .ttf/.otf so Blender can load them"
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
#USAGE arg "[paths]" var=#true help="Font files or directories to scan (default: assets/fonts)"
#USAGE flag "-f --force" help="Reconvert even if the .ttf/.otf is up to date"
#USAGE flag "--fetch-full" help="Fetch the full family from Google Fonts when glyph coverage looks subsetted"
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

A font that arrives already missing basic glyphs (a CDN unicode-range shard, or a
`text=`-subsetted webfont) converts cleanly and stays broken — the unwrap can't invent
outlines that were never there. `check_coverage()` below only warns about that; it never
introduces the gap itself.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from _common import TaskError, die, ok, skip, step, warn
from fontTools.ttLib import TTFont

SUFFIXES = (".woff", ".woff2")
SFNT_SUFFIXES = (".ttf", ".otf")
ALL_SUFFIXES = SFNT_SUFFIXES + SUFFIXES
DEFAULT_DIR = Path("assets/fonts")

BASIC_LATIN = (
    frozenset(range(0x41, 0x5B)) | frozenset(range(0x61, 0x7B)) | frozenset(range(0x30, 0x3A))
)
"""A-Z, a-z, 0-9 — the floor any general-purpose UI font must clear, not a claim about
accents/punctuation/other scripts."""

GOOGLE_FONTS_CSS2 = "https://fonts.googleapis.com/css2?family={family}:wght@{weight}"
FETCH_USER_AGENT = "comonteur-convert-fonts (+https://github.com/davidB/comonteur)"
"""Google's css2 endpoint version-negotiates the `@font-face` format on User-Agent: any
non-browser UA (verified: this one, curl's, and urllib's own default all behave the same)
gets a direct .ttf `src` — a *browser* UA (even a spoofed legacy one) gets routed through
Google's incremental-transfer `/l/font?kit=...` delivery instead, which isn't a plain sfnt
and fontTools can't open. So: identify honestly, don't impersonate a browser — it also
happens to be what gets the format this script wants."""


def missing_basic_glyphs(cmap: dict[int, str]) -> set[str]:
    """`cmap` is `TTFont.getBestCmap()` (or `{}`) — codepoint -> glyph name."""
    return {chr(c) for c in BASIC_LATIN if c not in cmap}


def family_name(font: TTFont) -> str:
    name = font["name"]
    return name.getDebugName(16) or name.getDebugName(1) or "Unknown"


def weight_class(font: TTFont) -> int:
    os2 = font.get("OS/2")
    return os2.usWeightClass if os2 is not None else 400


def fetch_full_ttf(family: str, weight: int) -> bytes | None:
    """Best-effort: `None` on any failure (network, unknown family, still incomplete) —
    the caller degrades to a warning rather than treating this as fatal.
    """
    css_url = GOOGLE_FONTS_CSS2.format(family=family.replace(" ", "+"), weight=weight)
    try:
        req = urllib.request.Request(css_url, headers={"User-Agent": FETCH_USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            css = resp.read().decode("utf-8", errors="replace")
        match = re.search(r"url\((https://[^)]+\.ttf)\)", css)
        if match is None:
            return None
        with urllib.request.urlopen(match.group(1), timeout=60) as resp:  # noqa: S310
            return resp.read()
    except (urllib.error.URLError, TimeoutError):
        return None


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


def convert(src: Path) -> Path | None:
    """Drop the WOFF container. Extension follows sfntVersion: CFF outlines are .otf, glyf .ttf.

    Returns `None`, not `out`, when skipped — never lets a worse-coverage source clobber a
    better-coverage `out` that's already there (e.g. a hand-fixed full font); `--force`
    reconverts stale outputs, not good ones.
    """
    font = TTFont(src)
    font.flavor = None
    out = src.with_suffix(".otf" if font.sfntVersion == "OTTO" else ".ttf")
    if out.exists():
        existing_missing = missing_basic_glyphs(TTFont(out).getBestCmap() or {})
        new_missing = missing_basic_glyphs(font.getBestCmap() or {})
        if len(existing_missing) <= len(new_missing):
            warn(
                f"{out.name} already has equal or better glyph coverage than {src.name}",
                f"delete {out.name} first if you really want to reconvert {src.name}",
            )
            return None
    font.save(out)
    return out


def effective_font_files(paths: list[Path]) -> list[Path]:
    """One file per logical font — the one Blender will actually load. `inter-400.woff2` and
    `inter-400.ttf` are the same font; prefer the sfnt over the still-wrapped web font so a
    correctly-converted pair isn't checked (and warned about) twice.
    """
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found += [p for p in path.rglob("*") if p.suffix.lower() in ALL_SUFFIXES]
        elif path.suffix.lower() in ALL_SUFFIXES:
            found.append(path)
    by_stem: dict[Path, Path] = {}
    for p in found:
        key = p.with_suffix("")
        current = by_stem.get(key)
        if current is None or (
            p.suffix.lower() in SFNT_SUFFIXES and current.suffix.lower() not in SFNT_SUFFIXES
        ):
            by_stem[key] = p
    return sorted(by_stem.values())


def check_coverage(paths: list[Path], *, fetch_full: bool) -> None:
    """Warn about any font — converted or not — missing basic Latin glyphs. Catches both a
    subsetted `.woff2` (converts cleanly, stays broken) and a raw `.ttf` that arrived as a
    wrong CDN unicode-range shard (no conversion involved, so `convert()` never sees it).
    """
    for path in effective_font_files(paths):
        font = TTFont(path)
        missing = missing_basic_glyphs(font.getBestCmap() or {})
        if not missing:
            continue
        chars = "".join(sorted(missing))
        if fetch_full:
            data = fetch_full_ttf(family_name(font), weight_class(font))
            if data is not None and not missing_basic_glyphs(
                TTFont(io.BytesIO(data)).getBestCmap() or {}
            ):
                out = path if path.suffix.lower() in SFNT_SUFFIXES else path.with_suffix(".ttf")
                out.write_bytes(data)
                ok(
                    f"{path.name}: fetched full {family_name(font)} from Google Fonts "
                    f"(was missing {chars!r})"
                )
                continue
        warn(
            f"{path.name}: missing basic glyphs {chars!r} — likely a subsetted/CDN-shard font",
            "rerun with --fetch-full, or replace the font manually",
        )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Convert web fonts to Blender-loadable sfnt")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("--fetch-full", action="store_true")
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
    else:
        step(f"converting {len(todo)} font(s)")
        for src in todo:
            out = convert(src)
            if out is not None:
                ok(f"{src.name} → {out.name}")
    check_coverage(paths, fetch_full=args.fetch_full)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
