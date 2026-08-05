"""anim.hard_cut() keyframes hide_render/hide_viewport with CONSTANT interpolation so
an object pops in/out at exact frames instead of crossfading -- and does so on both
properties identically, since hide_viewport also gates preview renders and
measure()/dimensions (see text.measure()'s docstring on the frozen-matrix_world trap).
Also cascades to obj.children_recursive, since Blender's hide_render/hide_viewport
don't cascade from a parent to its children on their own -- a bug that let a hidden
grouping Empty's child text/mesh stay visibly rendered.
"""

import _bl
import bpy

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-hard-cut", fps=30, frame_range=(1, 60))
    obj = cmt.text.create(scn, "pop")

with cmt.journal.batch("hard cut"):
    cmt.anim.hard_cut(obj, [(10, 20), (35, 40)])

action = obj.animation_data.action
for path in ("hide_render", "hide_viewport"):
    fc = action.fcurve_ensure_for_datablock(obj, path, index=0)
    for kp in fc.keyframe_points:
        assert kp.interpolation == "CONSTANT", (path, kp.co[0], kp.interpolation)
    frames = sorted(kp.co[0] for kp in fc.keyframe_points)
    assert frames == [1.0, 10.0, 21.0, 35.0, 41.0], (path, frames)

for frame, expect_hidden in [
    (1, True),
    (9, True),
    (10, False),
    (20, False),
    (21, True),
    (37, False),
    (41, True),
]:
    scn.frame_set(frame)
    assert obj.hide_render == expect_hidden, (frame, obj.hide_render)
    assert obj.hide_viewport == expect_hidden, (frame, obj.hide_viewport)

with cmt.journal.batch("fixture-group"):
    empty = bpy.data.objects.new("line-group", None)
    scn.collection.objects.link(empty)
    child = cmt.text.create(scn, "line 1")
    child.parent = empty

with cmt.journal.batch("hard cut group"):
    cmt.anim.hard_cut(empty, [(10, 20)])

child_action = child.animation_data.action
for path in ("hide_render", "hide_viewport"):
    fc = child_action.fcurve_ensure_for_datablock(child, path, index=0)
    frames = sorted(kp.co[0] for kp in fc.keyframe_points)
    assert frames == [1.0, 10.0, 21.0], (path, frames)

for frame, expect_hidden in [(1, True), (10, False), (20, False), (21, True)]:
    scn.frame_set(frame)
    assert empty.hide_render == expect_hidden, (frame, empty.hide_render)
    assert child.hide_render == expect_hidden, (frame, child.hide_render)
    assert child.hide_viewport == expect_hidden, (frame, child.hide_viewport)
