"""The whole-ID provenance flip (provenance.py's _on_depsgraph_update) is documented as
plausible-but-unverified for a human editing a driver's expression, as opposed to a plain
property value (the only case the M1-era check simulated). This pins the assumption: a
driver-expression edit outside journal.batch() must flip an agent-owned object to `shared`,
same as a moved keyframe or a hand-edited value would.
"""

import _bl
import bpy

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-drive-flip", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Wobble", size=0.8)

with cmt.journal.batch("drive"):
    cmt.anim.drive(obj, "rotation_euler", 1, "sin(frame*0.2)*0.1")

assert cmt.provenance.origin(obj) == "agent", cmt.provenance.origin(obj)

# Human edits the driver's formula directly in the Driver Editor — simulated the same way
# the property-edit case is (data-side mutation + view_layer.update()), since a headless run
# cannot drive the actual UI.
fc = obj.animation_data.drivers[0]
fc.driver.expression = "sin(frame*0.2)*0.3"
bpy.context.view_layer.update()

assert cmt.provenance.origin(obj) == "shared", (
    f"driver-expression edit did not flip ownership: origin={cmt.provenance.origin(obj)}"
)

flip_entries = [
    e
    for e in cmt.journal._read_all()
    if e.get("op") == "flip" and e.get("target") == cmt.journal.target_of(obj)
]
assert len(flip_entries) == 1, flip_entries
