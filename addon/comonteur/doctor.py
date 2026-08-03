"""comonteur doctor — SPEC.md M1. Debugging tool for the risky milestones, not polish."""

import json
import os
import shutil

import bpy

from . import const


def run(project_root: str | None = None) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, "PASS" if ok else "FAIL", detail))

    check("blender-version", bpy.app.version[:2] == (5, 2), f"got {bpy.app.version_string}")
    check("mcp-addon-enabled", _any_addon_enabled("blender_mcp"))
    check(f"{const.ADDON_ID}-addon-enabled", _any_addon_enabled(const.ADDON_ID))
    check("ffmpeg-on-path", shutil.which("ffmpeg") is not None)
    check("ffprobe-on-path", shutil.which("ffprobe") is not None)
    check("git-lfs-on-path", shutil.which("git-lfs") is not None)

    if project_root:
        check("project-layout", os.path.isfile(os.path.join(project_root, "timeline.blend")))
        check("journal-readable", _journal_readable(project_root))

    return results


def _any_addon_enabled(needle: str) -> bool:
    return any(needle in name for name in bpy.context.preferences.addons.keys())


def _journal_readable(project_root: str) -> bool:
    path = os.path.join(project_root, const.JOURNAL_DIR, const.JOURNAL_FILENAME)
    if not os.path.exists(path):
        return True  # no journal yet is not a failure
    try:
        with open(path) as f:
            for line in f:
                if line.strip():
                    json.loads(line)
        return True
    except (json.JSONDecodeError, OSError):
        return False


def print_report(results: list[tuple[str, str, str]]) -> None:
    for name, status, detail in results:
        print(f"[{name}] {status}{': ' + detail if detail else ''}")
