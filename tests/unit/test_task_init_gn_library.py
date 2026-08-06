"""comonteur:init_gn_library materializes lib/gn-vfx.blend, add-only.

Needs a real headless Blender (imports the comonteur add-on, saves a .blend), so this
is both a task-script test and a Blender one -- skip like the blender-marked suite does
when Blender is not on PATH (same shape as test_task_edit.py).
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

init_gn_library = load("init_gn_library")


def _discover_node_groups(lib_blend: Path) -> list[str]:
    script = lib_blend.parent / "_read.py"
    script.write_text(
        "import bpy, json\n"
        "names = [ng.name for ng in bpy.data.node_groups]\n"
        "print('CMT_JSON', json.dumps(names))\n"
    )
    proc = subprocess.run(
        [shutil.which("blender") or "blender", "-b", str(lib_blend), "--python", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    line = next(line for line in proc.stdout.splitlines() if line.startswith("CMT_JSON "))
    return json.loads(line[len("CMT_JSON ") :])


def test_creates_gn_vfx_blend_with_every_effect(tmp_path: Path) -> None:
    exit_code = init_gn_library.main([str(tmp_path)])

    assert exit_code == 0
    lib_blend = tmp_path / "lib" / "gn-vfx.blend"
    assert lib_blend.exists()
    names = _discover_node_groups(lib_blend)
    assert {"CMT Char Reveal", "CMT Typewriter", "CMT Fracture"} <= set(names), names


def test_second_run_is_a_no_op(tmp_path: Path) -> None:
    init_gn_library.main([str(tmp_path)])
    lib_blend = tmp_path / "lib" / "gn-vfx.blend"
    mtime = lib_blend.stat().st_mtime_ns

    exit_code = init_gn_library.main([str(tmp_path)])

    assert exit_code == 0
    assert lib_blend.stat().st_mtime_ns == mtime
