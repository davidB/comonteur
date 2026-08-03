"""new_scene(kind="2d") pins EEVEE indirect-lighting settings, and text color defaults to
flat/emission shading — a fresh 2D scene has no lights, so Base-Color-only Principled BSDF
rendered black until this. See addon/comonteur/scene.py new_scene() and text.py style().
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-2d", kind="2d", fps=30, frame_range=(1, 90))

assert scn.eevee.use_fast_gi is False
assert scn.eevee.use_raytracing is False
assert scn.eevee.indirect_light_intensity == 0.0
assert scn.eevee.taa_samples == 2
assert scn.eevee.taa_render_samples == 4
assert scn.eevee.use_shadows is False
assert scn.render.image_settings.media_type == "VIDEO"
assert scn.render.image_settings.file_format == "FFMPEG"
assert scn.render.ffmpeg.audio_codec == "NONE"

with cmt.journal.batch("text"):
    obj = cmt.text.create(scn, "Ship faster", color=(1.0, 0.0, 0.0))

mat = obj.data.materials[0]
bsdf = mat.node_tree.nodes["Principled BSDF"]
assert tuple(bsdf.inputs["Emission Color"].default_value) == (1.0, 0.0, 0.0, 1.0)
assert tuple(bsdf.inputs["Base Color"].default_value) == (0.0, 0.0, 0.0, 1.0)
assert bsdf.inputs["Emission Strength"].default_value == 1.0

with cmt.journal.batch("restyle lit"):
    cmt.text.style(obj, color=(0.0, 1.0, 0.0), shading="lit")

assert tuple(bsdf.inputs["Base Color"].default_value) == (0.0, 1.0, 0.0, 1.0)
assert bsdf.inputs["Emission Strength"].default_value == 0.0
