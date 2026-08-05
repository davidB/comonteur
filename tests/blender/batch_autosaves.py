"""journal.batch() saves the .blend on exit once it has a path, and backs the save with
Blender's native save_version rotation (docs/architecture.md §4.5) — the rule changed from
"the agent never saves" to "batches save themselves". This pins: a write-batch after the
first save produces a new .blend1 backup and bumps mtime; a no-write batch touches neither.
"""

import time
from pathlib import Path

import _bl
import bpy

cmt = _bl.setup()

blend_path = Path.cwd() / "test.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
assert bpy.data.filepath == str(blend_path)
assert not (Path.cwd() / "test.blend1").exists(), "no backup should exist before any batch save"

mtime_before = blend_path.stat().st_mtime
time.sleep(1.1)  # mtime resolution on some filesystems is 1s

scn = bpy.context.scene
with cmt.journal.batch("tag scene"):
    cmt.provenance.tag(scn, "t1")

assert blend_path.stat().st_mtime > mtime_before, "a batch with writes must save the .blend"
assert bpy.context.preferences.filepaths.save_version >= 2, (
    "save_version must be bumped for backups"
)
assert (Path.cwd() / "test.blend1").exists(), "the prior version must be backed up as .blend1"

mtime_after_write = blend_path.stat().st_mtime
time.sleep(1.1)

with cmt.journal.batch("no-op"):
    pass

assert blend_path.stat().st_mtime == mtime_after_write, "a batch with no writes must not save"
