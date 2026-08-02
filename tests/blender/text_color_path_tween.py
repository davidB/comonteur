"""text.color_path() returns the exact RNA path style() writes to, so tween()/stagger()
can animate a styled object's color without every caller hand-typing the node/input
names and risking a typo against style()'s exact string.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-color-path", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Ship faster", color=(0.2, 0.2, 0.2, 1.0))

target = cmt.text.color_target(obj)
path = cmt.text.color_path(obj)
with cmt.journal.batch("color tween"):
    cmt.anim.tween(target, path, 0, frm=0.2, to=0.9, start=1, dur=10)

action = target.animation_data.action
fc = action.fcurve_ensure_for_datablock(target, path, index=0)
assert len(fc.keyframe_points) == 2, len(fc.keyframe_points)
assert (fc.keyframe_points[0].co[0], fc.keyframe_points[-1].co[0]) == (1.0, 11.0)
