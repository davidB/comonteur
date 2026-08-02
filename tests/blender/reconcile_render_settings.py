"""apply_render_settings() sets resolution/fps/codec/output-folder from a resolved
plan that carries only fps/resolution/encode — no shots/audio/transitions — since
that's the partial-reconcile shape comonteur:edit's master.blend creation uses (no
shots exist yet right after comonteur:init). See addon/comonteur/reconcile.py.
"""

import _bl
import bpy

cmt = _bl.setup()

scn = bpy.context.scene
resolved = {
    "fps": 24,
    "resolution": [1280, 720],
    "video_codec": "H264",
    "video_container": None,
    "audio_codec": "AAC",
}

with cmt.journal.batch("render settings"):
    cmt.reconcile.apply_render_settings(scn, resolved)

assert scn.render.resolution_x == 1280
assert scn.render.resolution_y == 720
assert scn.render.fps == 24
assert scn.render.image_settings.file_format == "FFMPEG"
assert scn.render.ffmpeg.codec == "H264"
assert scn.render.ffmpeg.format == "MPEG4"
assert scn.render.ffmpeg.audio_codec == "AAC"
assert scn.render.ffmpeg.constant_rate_factor == "MEDIUM"
assert scn.render.ffmpeg.ffmpeg_preset == "GOOD"
assert scn.render.filepath == "//renders/"

# Same as fps/resolution: reconcile stays authoritative and re-syncs the output
# folder on every call rather than drifting from timeline.toml, even over a manual
# edit — journal.set() doesn't consult claimed_paths() for scalar scene properties,
# only the shot/audio/transition strip-diffing logic does that.
scn.render.filepath = "//custom-output/"
with cmt.journal.batch("render settings again"):
    cmt.reconcile.apply_render_settings(scn, resolved)
assert scn.render.filepath == "//renders/"
