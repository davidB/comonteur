"""anim.idle_jitter() bakes N sampled keyframes around the current value — the
"sine wobble over N cycles" pattern HyperFrames names but cmt.anim had no primitive
for (tween() only supports two endpoints).
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-jitter", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Idle", size=0.8)

with cmt.journal.batch("idle jitter"):
    cmt.anim.idle_jitter(obj, "rotation_euler", 2, amplitude=0.1, cycles=2, start=1, dur=20)

rows = cmt.introspect.animated_paths(scn)
row = next(r for r in rows if r["data_path"] == "rotation_euler" and r["index"] == 2)
assert row["keys"] == 6, f"base + 2*cycles peak/trough + closing base = 6, got {row['keys']}"
assert row["frame_range"] == (1.0, 21.0), row

written = cmt.journal.paths_written_by_agent(obj)
assert "rotation_euler[2]" in written, written
