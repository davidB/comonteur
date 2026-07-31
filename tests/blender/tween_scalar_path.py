"""anim.tween() animates scalar properties, not just array components.

references/api.md tells the agent that "scalar paths still take index=0". They did not:
tween() unconditionally journalled `f"{path}[{index}]"`, so paths.resolve subscripted a float
and raised `TypeError: 'float' object is not subscriptable`. Fading a single value — the most
common motion after a transform — was documented and broken.

`index=None` is the scalar form. `empty_display_size` is used here because it is a genuine
scalar *on the Object*; `data.size` (api.md's old example) lives on the Curve data and is not
a valid Object RNA path at all, so it could never have worked either way.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-scalar", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Ship faster", size=0.8)

with cmt.journal.batch("scalar tween"):
    cmt.anim.tween(obj, "empty_display_size", None, frm=0.5, to=1.0, start=1, dur=10)

rows = cmt.introspect.animated_paths(scn)
row = next(r for r in rows if r["data_path"] == "empty_display_size")
assert row["keys"] == 2, f"tween writes two real keyframes, got {row['keys']}"
assert row["frame_range"] == (1.0, 11.0), row

# The journal records the bare path — no phantom "[0]" an agent or revert would then fail on.
written = cmt.journal.paths_written_by_agent(obj)
assert "empty_display_size" in written, written
assert "empty_display_size[0]" not in written, written

# Array paths keep working exactly as before.
with cmt.journal.batch("array tween"):
    cmt.anim.tween(obj, "location", 1, frm=-0.4, to=0.0, start=1, dur=18)
assert "location[1]" in cmt.journal.paths_written_by_agent(obj)
