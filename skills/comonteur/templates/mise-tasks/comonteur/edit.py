#!/usr/bin/env -S uv run --script
#MISE description="Open timeline.blend in Blender — leave it open, the agent talks to this session"
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
#USAGE arg "[blender_args]…" help="Extra arguments forwarded verbatim to Blender"
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Open `timeline.blend` for the human, creating it first if this is the first run.

Extra args go straight to Blender.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from _common import TaskError, blender_headless, die, require_blender, run


def _render_settings_from_timeline(root: Path) -> dict[str, Any]:
    """fps/resolution/encode straight off timeline.toml, no anchor/shot resolution.

    A fresh project (right after `comonteur:init`) may have no narrative/audio inputs
    yet, so the full `reconcile.py::resolve()` (which needs those) can't run here —
    this reads only the three top-level fields the scene's render settings need. Reads
    the TOML directly rather than importing the sibling `reconcile.py` task script:
    that module shares its bare top-level name with `addon/comonteur/reconcile.py`,
    and whichever gets `sys.modules`-cached first in a given process wins — a real
    collision in the test suite, which imports both.
    """
    with (root / "timeline.toml").open("rb") as f:
        doc = tomllib.load(f)
    encode = doc.get("encode") or {}
    return {
        "fps": doc.get("fps"),
        "resolution": doc.get("resolution"),
        "video_codec": encode.get("video_codec", "H265"),
        "video_container": encode.get("video_container"),
        "audio_codec": encode.get("audio_codec"),
    }


def ensure_timeline(root: Path) -> None:
    """Create `timeline.blend` if it doesn't exist yet — the one exception to "the
    agent never saves the .blend" (docs/architecture.md §4.5): nothing to clobber on
    a brand-new file, and every later `edit`/`render` run still refuses to re-save.
    """
    timeline_blend = root / "timeline.blend"
    if timeline_blend.exists():
        return
    settings_json = json.dumps(_render_settings_from_timeline(root))
    script = f"""
import importlib
import json
import bpy
import addon_utils

# Installed as a Blender extension, comonteur lives at bl_ext.<repo>.comonteur, not a
# bare top-level "comonteur" — find its actual module name rather than guess it.
cmt_module_name = next(
    (m.__name__ for m in addon_utils.modules() if m.__name__.split(".")[-1] == "comonteur"),
    None,
)
if cmt_module_name is None:
    raise SystemExit("comonteur add-on not installed — run `mise run comonteur:install` first")
cmt = importlib.import_module(cmt_module_name)
journal, provenance, cmt_reconcile = cmt.journal, cmt.provenance, cmt.reconcile

template = next(bpy.utils.app_template_paths()) + "/Video_Editing/startup.blend"
bpy.ops.workspace.append_activate(idname="Video Editing", filepath=template)
ws = bpy.data.workspaces["Video Editing"]
for area in ws.screens[0].areas:
    if area.type == "FILE_BROWSER":
        # Not bpy.path.abspath("//") — that resolves against bpy.data.filepath, which
        # is still empty at this point (the file isn't saved yet).
        area.spaces.active.params.directory = {(str(root) + os.sep)!r}.encode()

settings = json.loads({settings_json!r})
scn = bpy.context.scene
with journal.batch("create timeline.blend"):
    scn.name = "timeline"
    provenance.tag(scn, "timeline")
    if scn.sequence_editor is None:
        scn.sequence_editor_create()
    cmt_reconcile.apply_render_settings(scn, settings)
bpy.ops.wm.save_as_mainfile(filepath={str(timeline_blend)!r})
"""
    blender_headless(script)


def main(argv: list[str]) -> int:
    exe = require_blender()
    ensure_timeline(Path.cwd())
    cmd = [exe, "timeline.blend", *argv]
    # execvp hands the terminal to Blender outright; Windows has no equivalent (it would
    # spawn and return), so there we wait and pass the exit code back.
    if os.name == "posix":
        os.execvp(exe, cmd)  # noqa: S606 — never returns
    return run(cmd, check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
