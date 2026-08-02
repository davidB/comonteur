"""fx.vignette() builds a camera-facing radial-gradient overlay plane — the
darken-the-corners effect that was flattened to a plain dim when dropped under
time pressure.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("vignette"):
    scn = cmt.scene.new_scene("shot-vignette", fps=30, frame_range=(1, 90))
    quad = cmt.fx.vignette(scn, color=(0.0, 0.0, 0.0), strength=0.6)

assert cmt.provenance.origin(quad) == "agent", cmt.provenance.origin(quad)
mat = quad.data.materials[0]
node_types = {n.bl_idname for n in mat.node_tree.nodes}
assert "ShaderNodeTexGradient" in node_types, node_types
gradient = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexGradient")
assert gradient.gradient_type == "QUADRATIC_SPHERE", gradient.gradient_type
