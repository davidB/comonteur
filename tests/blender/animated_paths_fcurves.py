"""introspect.animated_paths() must work on the pinned Blender (5.2).

5.2's layered-Action rework removed `Action.fcurves` in favour of
`action.layers[].strips[].channelbags[].fcurves`. anim.py already goes through
`fcurve_ensure_for_datablock()` for writes; the read path in introspect.py did not, so
`animated_paths()` raised AttributeError on any scene that had animation — including animation
`cmt.anim.tween()` had just created. That is step 2 of the SKILL.md loop, so it broke every
shot before the first write.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture: animated shot"):
    scn = cmt.scene.new_scene("shot-anim", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "Ship faster", size=0.8)
    cmt.anim.tween(title, "location", 1, frm=-0.4, to=0.0, start=1, dur=18, ease="power2.out")

rows = cmt.introspect.animated_paths(scn)

assert rows, "animated_paths() found nothing after a tween wrote two keyframes"

row = next(r for r in rows if r["object"] == title.name)
assert row["data_path"] == "location", row
assert row["index"] == 1, row
assert row["keys"] == 2, f"tween writes exactly two keyframes, got {row['keys']}"
assert row["frame_range"] == (1.0, 19.0), row

# The documented dict shape (references/api.md) — the agent reads these keys by name.
assert set(row) == {"object", "data_path", "index", "keys", "frame_range"}, sorted(row)
