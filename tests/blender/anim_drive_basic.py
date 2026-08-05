"""anim.drive() attaches a real Blender driver instead of pre-sampled keyframes, and must
participate in the same journal.batch() bookkeeping as anim.tween()/journal.set() — an
op:"driver" entry, a cmt_rev bump, and the `writes`-gated undo_push/autosave (see
batch_journals_creation.py's docstring: the undo_push itself needs a window a headless run
hasn't got, so what's pinned here is the `writes` list that gates it).
"""

import json
from pathlib import Path

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-drive", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Wobble", size=0.8)

with cmt.journal.batch("drive"):
    cmt.anim.drive(obj, "rotation_euler", 1, "sin(frame*0.2)*0.1")

drivers = obj.animation_data.drivers
assert len(drivers) == 1, drivers
fc = drivers[0]
assert fc.data_path == "rotation_euler", fc.data_path
assert fc.array_index == 1, fc.array_index
assert fc.driver.expression == "sin(frame*0.2)*0.1", fc.driver.expression

entries = [json.loads(line) for line in Path(".comonteur/journal.jsonl").read_text().splitlines()]
driver_entries = [e for e in entries if e["op"] == "driver"]
assert len(driver_entries) == 1, driver_entries
assert driver_entries[0]["path"] == "rotation_euler[1]", driver_entries[0]
assert driver_entries[0]["expression"] == "sin(frame*0.2)*0.1", driver_entries[0]

assert obj["cmt_rev"] >= 2, obj["cmt_rev"]  # bumped by the fixture batch, then the drive batch
