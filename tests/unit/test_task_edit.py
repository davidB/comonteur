"""ensure_master() — comonteur:edit creates master.blend on first run when missing.

Needs a real headless Blender (imports the comonteur add-on, saves a .blend), so this
is both a task-script test and a Blender one — skip like the blender-marked suite does
when Blender is not on PATH.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from _tasks import load

pytestmark = [
    pytest.mark.task,
    pytest.mark.blender,
    pytest.mark.skipif(shutil.which("blender") is None, reason="blender not on PATH"),
]

edit = load("edit")

TIMELINE_TOML = """
fps = 24
resolution = [1280, 720]
"""


def _read_master(master: Path) -> dict:
    script = master.parent / "_read.py"
    script.write_text(
        "import bpy, json\n"
        "scn = bpy.context.scene\n"
        "ws = bpy.data.workspaces.get('Video Editing')\n"
        "fb_dir = None\n"
        "if ws is not None:\n"
        "    for area in ws.screens[0].areas:\n"
        "        if area.type == 'FILE_BROWSER':\n"
        "            fb_dir = area.spaces.active.params.directory.decode()\n"
        "print('CMT_JSON', json.dumps({\n"
        "    'name': scn.name,\n"
        "    'resolution': [scn.render.resolution_x, scn.render.resolution_y],\n"
        "    'fps': scn.render.fps,\n"
        "    'filepath': scn.render.filepath,\n"
        "    'has_video_editing': ws is not None,\n"
        "    'file_browser_dir': fb_dir,\n"
        "}))\n"
    )
    proc = subprocess.run(
        [shutil.which("blender") or "blender", "-b", str(master), "--python", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    line = next(line for line in proc.stdout.splitlines() if line.startswith("CMT_JSON "))
    return json.loads(line[len("CMT_JSON ") :])


def test_creates_master_blend_from_timeline_toml(tmp_path: Path) -> None:
    (tmp_path / "timeline.toml").write_text(TIMELINE_TOML)
    master = tmp_path / "master.blend"

    edit.ensure_master(tmp_path)

    assert master.exists()
    info = _read_master(master)
    assert info["name"] == "timeline"
    assert info["resolution"] == [1280, 720]
    assert info["fps"] == 24
    assert info["filepath"] == "//renders/"
    assert info["has_video_editing"] is True
    assert info["file_browser_dir"] == f"{tmp_path}/"


def test_second_run_is_a_no_op(tmp_path: Path) -> None:
    (tmp_path / "timeline.toml").write_text(TIMELINE_TOML)
    master = tmp_path / "master.blend"

    edit.ensure_master(tmp_path)
    mtime = master.stat().st_mtime_ns

    edit.ensure_master(tmp_path)

    assert master.stat().st_mtime_ns == mtime
