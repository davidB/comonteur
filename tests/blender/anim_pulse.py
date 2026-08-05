"""anim.pulse() is a one-shot spike (base -> peak -> base), distinct from
idle_jitter()'s repeating peak/trough oscillation — the primitive a flash-pulse effect
needs instead of dropping it under time pressure.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-pulse", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Flash", size=0.8)

with cmt.journal.batch("pulse"):
    cmt.anim.pulse(obj, "empty_display_size", None, peak=3.0, start=10, dur=20)

rows = cmt.introspect.animated_paths(scn)
row = next(r for r in rows if r["data_path"] == "empty_display_size")
assert row["keys"] == 3, f"base, peak, base = 3 keyframes, got {row['keys']}"
assert row["frame_range"] == (10.0, 30.0), row

fc = obj.animation_data.action.fcurve_ensure_for_datablock(obj, "empty_display_size", index=0)
values = [kf.co[1] for kf in fc.keyframe_points]
assert values[1] == 3.0, f"middle keyframe must hold peak=3.0, got {values}"
assert values[0] == values[2] != 3.0, (
    f"outer keyframes must hold base, distinct from peak, got {values}"
)
