"""card.reorigin_left() re-origins a plane's mesh so local X spans 0..w instead of
-w/2..w/2, with world position unchanged -- so a later scale.x tween from 0 to 1
grows the plane from its left edge instead of from its center.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-reorigin", fps=30, frame_range=(1, 30))
    obj = cmt.card._plane(scn, "bar", 2.0, 0.2)
    obj.location = (1.5, -0.5, 0.0)

# obj has no rotation/scale/parent, so world position is plain location + local vert
# co (no depsgraph update needed to read this back correctly).
world_left_before = obj.location.x + min(v.co.x for v in obj.data.vertices)
world_right_before = obj.location.x + max(v.co.x for v in obj.data.vertices)

cmt.card.reorigin_left(obj)

xs = [v.co.x for v in obj.data.vertices]
assert min(xs) == 0.0, min(xs)
assert abs(max(xs) - 2.0) < 1e-6, max(xs)

world_left_after = obj.location.x + min(v.co.x for v in obj.data.vertices)
world_right_after = obj.location.x + max(v.co.x for v in obj.data.vertices)
assert abs(world_left_after - world_left_before) < 1e-6, (world_left_after, world_left_before)
assert abs(world_right_after - world_right_before) < 1e-6, (world_right_after, world_right_before)
