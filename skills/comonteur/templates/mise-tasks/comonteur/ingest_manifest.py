#!/usr/bin/env -S uv run --script
#MISE description="Build assets/manifest.json from assets/ (sha256 + ffprobe metadata)"
#MISE dir="{{config_root}}"
#MISE sources=["assets/**/*", "!assets/manifest.json"]
#MISE outputs=["assets/manifest.json"]
#MISE tools={ffmpeg = "latest", uv = "latest"}
#USAGE arg "[assets_dir]" help="Directory to scan (default: assets)"
#USAGE arg "[out]" help="Manifest path to write (default: <assets_dir>/manifest.json)"
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# sources/outputs: sha256 + ffprobe over every asset is slow, so mise skips this when assets/
# is unchanged. The manifest itself is excluded from sources — it lives in the directory it
# describes, and without the negation it would invalidate itself on every run. Force a rebuild
# with `mise run --force comonteur:ingest_manifest`.
"""`assets/manifest.json` ingest — SPEC.md §5.3: content-addressed by sha256, per-asset
duration/fps/resolution/has_alpha/codec from `ffprobe`.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ALPHA_PIX_FMTS = frozenset(
    ("rgba", "bgra", "argb", "abgr", "ya8", "ya16le", "ya16be", "gbrap")
)


def has_alpha(pix_fmt: str) -> bool:
    return pix_fmt in ALPHA_PIX_FMTS or pix_fmt.startswith("yuva")


def parse_rate(rate: str) -> float | None:
    num, sep, den = rate.partition("/")
    if not sep:
        return None
    try:
        n, d = float(num), float(den)
    except ValueError:
        return None
    return None if d == 0.0 else n / d


def _as_float(v: Any) -> float | None:
    """ffprobe reports duration as a string; mirror serde's `as_str().parse::<f64>()`."""
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _as_int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _as_str(v: Any) -> str | None:
    return v if isinstance(v, str) else None


def parse_probe(probe_json: dict[str, Any]) -> dict[str, Any]:
    """Pure function over an already-parsed `ffprobe -show_format -show_streams
    -print_format json` value — unit-tested against literal fixtures, no subprocess.
    """
    streams = probe_json.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    primary = video if video is not None else (streams[0] if streams else None)

    duration = _as_float((primary or {}).get("duration"))
    if duration is None:
        duration = _as_float((probe_json.get("format") or {}).get("duration"))

    fps = None
    if video is not None:
        rate = _as_str(video.get("r_frame_rate"))
        fps = parse_rate(rate) if rate is not None else None

    resolution = None
    if primary is not None:
        w, h = _as_int(primary.get("width")), _as_int(primary.get("height"))
        if w is not None and h is not None:
            resolution = [w, h]

    pix_fmt = _as_str((primary or {}).get("pix_fmt"))
    codec = _as_str((primary or {}).get("codec_name"))

    return {
        "duration": duration,
        "fps": fps,
        "resolution": resolution,
        "has_alpha": has_alpha(pix_fmt) if pix_fmt is not None else False,
        "codec": codec,
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(64 * 1024):
            h.update(chunk)
    return h.hexdigest()


def run_ffprobe(path: Path) -> dict[str, Any]:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
        )
    except OSError as e:
        raise SystemExit(
            f"running ffprobe (is it on PATH? see `mise run comonteur:doctor`): {e}"
        ) from e
    if out.returncode != 0:
        raise SystemExit(f"ffprobe failed on {path}: {out.stderr.decode(errors='replace')}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise SystemExit(f"parsing ffprobe JSON output: {e}") from e


def probe_asset(path: Path, rel_path: str) -> dict[str, Any]:
    # sha256 first, then probe — same order as the Rust original, so a probe failure on a
    # late asset leaves the same partial state.
    entry = {"sha256": sha256_file(path), "path": rel_path}
    entry.update(parse_probe(run_ffprobe(path)))
    return entry


def walk_files(directory: Path) -> list[Path]:
    files: list[Path] = []
    for entry in sorted(directory.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            files.extend(walk_files(entry))
        else:
            files.append(entry)
    return files


def build_manifest(assets_dir: Path, out_path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    for entry in walk_files(assets_dir):
        rel = entry.relative_to(assets_dir).as_posix()
        if rel == "manifest.json":
            continue
        asset = probe_asset(entry, rel)
        manifest[asset["sha256"]] = asset
    # Sort the top level only, mirroring the Rust BTreeMap keyed by sha256: byte-stable
    # across runs so git sees no diff when nothing changed. Not `sort_keys=True` — that
    # would also alphabetize each entry's fields, which serde emitted in declaration order.
    ordered = dict(sorted(manifest.items()))
    out_path.write_text(json.dumps(ordered, indent=2), encoding="utf-8")
    return ordered


def main(argv: list[str]) -> None:
    assets_dir = Path(argv[0]) if argv else Path("assets")
    out_path = Path(argv[1]) if len(argv) > 1 else assets_dir / "manifest.json"
    if not assets_dir.is_dir():
        raise SystemExit(f"reading {assets_dir}: not a directory")
    manifest = build_manifest(assets_dir, out_path)
    print(f"wrote {out_path} ({len(manifest)} asset(s))")


if __name__ == "__main__":
    main(sys.argv[1:])
