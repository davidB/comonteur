"""Regression for #6: _flat_material()/highlight_bg() set Base Color's and Emission
Color's alpha but never the Principled BSDF's real "Alpha" input, which is the only
socket that actually drives BLEND transparency -- so a shadow/border/highlight built
with alpha < 1.0 silently rendered fully opaque.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("card-alpha"):
    scn = cmt.scene.new_scene("shot-card-alpha", fps=30, frame_range=(1, 90))
    obj = cmt.card._plane(scn, "swatch", 1.0, 1.0)
    cmt.card._flat_material(obj, (1.0, 0.5, 0.0, 0.35))

bsdf = obj.data.materials[0].node_tree.nodes["Principled BSDF"]
alpha = bsdf.inputs["Alpha"].default_value
assert abs(alpha - 0.35) < 1e-6, alpha
