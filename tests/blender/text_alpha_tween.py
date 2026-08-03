"""text.alpha_path() actually fades a styled object -- tweening color_path()'s alpha
component compiles and runs but Principled BSDF ignores a Color socket's alpha, so
it's a silent no-op; only the dedicated Alpha input (with blend_method='BLEND',
set by style() by default) has any visible effect.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-alpha", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "fade me", color=(0.8, 0.1, 0.1, 1.0))

mat = obj.data.materials[0]
assert mat.blend_method == "BLEND", mat.blend_method

target = cmt.text.color_target(obj)
path = cmt.text.alpha_path(obj)
with cmt.journal.batch("alpha tween"):
    cmt.anim.tween(target, path, None, frm=1.0, to=0.0, start=1, dur=10)

action = target.animation_data.action
fc = action.fcurve_ensure_for_datablock(target, path, index=0)
assert len(fc.keyframe_points) == 2, len(fc.keyframe_points)
values = [kf.co[1] for kf in fc.keyframe_points]
assert values == [1.0, 0.0], values

# color_path()'s own alpha component is a distinct fcurve/path from alpha_path() --
# confirms the two aren't accidentally aliased to the same node input.
assert cmt.text.color_path(obj) != path, (cmt.text.color_path(obj), path)
