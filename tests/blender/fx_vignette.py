"""fx.vignette() builds a camera-facing radial-gradient overlay plane — the
darken-the-corners effect that was flattened to a plain dim when dropped under
time pressure.

The plane must cover the full camera frame regardless of aspect ratio: with the
fixed FRAME_HEIGHT-tall camera convention (scene.add_camera()), a non-square
render resolution needs a non-square plane, not the old hardcoded 2x2.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("vignette"):
    scn = cmt.scene.new_scene("shot-vignette", fps=30, frame_range=(1, 90), resolution=(1920, 1080))
    quad = cmt.fx.vignette(scn, color=(0.0, 0.0, 0.0), strength=0.6)

assert cmt.provenance.origin(quad) == "agent", cmt.provenance.origin(quad)
mat = quad.data.materials[0]
node_types = {n.bl_idname for n in mat.node_tree.nodes}
assert "ShaderNodeTexGradient" in node_types, node_types
gradient = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexGradient")
assert gradient.gradient_type == "QUADRATIC_SPHERE", gradient.gradient_type

expected_w = cmt.const.FRAME_HEIGHT * (1920 / 1080)
mesh = quad.data
xs = [v.co.x for v in mesh.vertices]
ys = [v.co.y for v in mesh.vertices]
w, h = max(xs) - min(xs), max(ys) - min(ys)
assert abs(w - expected_w) < 1e-6, (w, expected_w)
assert abs(h - cmt.const.FRAME_HEIGHT) < 1e-6, (h, cmt.const.FRAME_HEIGHT)
