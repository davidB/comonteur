"""anim.drive_tween() is the formula-driven equivalent of tween(): one driver expression
instead of two keyframes, for when a formula is simpler for the agent to emit directly.
Pins the actual evaluated curve at a few frames (clamped before start, clamped after end,
and the easing shape at the midpoint) rather than just checking the driver was created —
same lesson as anim.pulse()'s bug: a driver that "exists" but evaluates to the wrong thing
is exactly the failure mode worth pinning.
"""

import math

import _bl
import bpy

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-drive-tween", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Slide", size=0.8)

with cmt.journal.batch("drive_tween linear"):
    cmt.anim.drive_tween(obj, "location", 0, frm=0.0, to=10.0, start=10, dur=20, ease="linear")


def at(frame: int) -> float:
    bpy.context.scene.frame_set(frame)
    return obj.location[0]


assert at(0) == 0.0, at(0)  # before start: clamped to frm
assert at(10) == 0.0, at(10)  # at start
assert abs(at(20) - 5.0) < 1e-4, at(20)  # midpoint of a linear ease
assert at(30) == 10.0, at(30)  # at end
assert at(60) == 10.0, at(60)  # after end: clamped to to

with cmt.journal.batch("drive_tween sine.out"):
    cmt.anim.drive_tween(obj, "location", 1, frm=0.0, to=1.0, start=0, dur=10, ease="sine.out")

bpy.context.scene.frame_set(5)
assert abs(obj.location[1] - math.sin(math.pi / 4)) < 1e-4, obj.location[1]

unsupported = _bl.raises(ValueError, lambda: cmt.anim.drive_tween(obj, "location", 2, 0, 1, 1, 10, ease="elastic.out"))
assert unsupported is not None, "elastic has no closed form, drive_tween() must reject it"
