"""text.measure() gives a world-space bounding box without destructively splitting
the text object into per-character pieces just to measure (fit_to_box()'s
view_layer.update() + dimensions precedent, exposed read-only).
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-measure", fps=30, frame_range=(1, 90))
    obj = cmt.text.create(scn, "Ship faster", size=0.8)

m = cmt.text.measure(obj)
assert set(m) == {"width", "height", "depth", "min", "max"}, sorted(m)
assert abs(m["width"] - obj.dimensions.x) < 1e-6, m
assert abs(m["height"] - obj.dimensions.y) < 1e-6, m
assert m["max"][0] > m["min"][0], m  # non-degenerate in X

obj.location.x = 5.0
m2 = cmt.text.measure(obj)
assert abs((m2["min"][0] - m["min"][0]) - 5.0) < 1e-4, (m, m2)  # tracks world position, not local
