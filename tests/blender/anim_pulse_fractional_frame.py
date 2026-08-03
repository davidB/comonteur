"""anim.pulse()'s peak frame (start + dur*0.3) is fractional for most durs, e.g.
dur=16 -> 4.8. _keyframe() used to look the inserted keyframe up by exact float
equality, which misses once Blender snaps the subframe internally -> StopIteration.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-pulse-frac", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Flash", size=0.8)

with cmt.journal.batch("pulse"):
    # dur=16 -> peak_frame = 58 + 16*0.3 = 62.8 (fractional); dur=10 -> 3.0 would not
    # reproduce the bug, which is why the existing anim_pulse.py test missed it.
    cmt.anim.pulse(obj, "empty_display_size", None, peak=3.0, start=58, dur=16)

rows = cmt.introspect.animated_paths(scn)
row = next(r for r in rows if r["data_path"] == "empty_display_size")
assert row["keys"] == 3, f"base, peak, base = 3 keyframes, got {row['keys']}"
assert row["frame_range"] == (58.0, 74.0), row
