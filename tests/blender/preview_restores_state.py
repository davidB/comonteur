"""preview.frames() renders the scene's actual camera view and touches only the current
frame — never render.filepath, window.scene, engine (unless requested), or image_settings.

It used to go through bpy.ops.render.opengl(), which renders whatever the ambient interactive
viewport is looking at rather than the scene's camera, and silently produces a wrong (but
validly-shaped) placeholder image whenever the active workspace has no VIEW_3D area or that
area isn't locked to camera view. bpy.ops.render.opengl() also cannot run in background mode
at all, so this test previously could only assert state-restoration on the error path and
never exercised the actual render. Switching to bpy.ops.render.render(write_still=False,
scene=...) — the "Render Image" path — fixes both: it always uses the scene's own camera
regardless of viewport/workspace state, and it runs headless, so this test can now assert on
the rendered pixels too.
"""

import os

import _bl
import bpy

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    # kind="2d" pins media_type="VIDEO"/file_format="FFMPEG" (scene.py) — exactly the
    # setting preview.frames() must render past without touching or depending on.
    scn = cmt.scene.new_scene("shot-preview", kind="2d", fps=30, frame_range=(1, 90))
    quad = cmt.card._plane(scn, "red-card", 10.0, 10.0)
    cmt.card._flat_material(quad, (1.0, 0.0, 0.0, 1.0))

    cam_data = bpy.data.cameras.new("preview-cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 10.0
    cam_obj = bpy.data.objects.new("preview-cam", cam_data)
    scn.collection.objects.link(cam_obj)
    cam_obj.location = (0.0, 0.0, 5.0)
    scn.camera = cam_obj

SENTINEL = "//renders/final_####"
scn.render.filepath = SENTINEL
scn.render.engine = "BLENDER_EEVEE"
scn.frame_set(42)
prev_media_type = scn.render.image_settings.media_type
prev_file_format = scn.render.image_settings.file_format
prev_window_scene = bpy.context.window.scene

paths = cmt.preview.frames(scn, [1, 45, 90])

assert len(paths) == 3, paths
for p in paths:
    assert os.path.exists(p), f"preview.frames() did not write {p}"

assert scn.render.filepath == SENTINEL, (
    f"preview.frames() left render.filepath at {scn.render.filepath!r} — "
    f"the human's next render would go there"
)
assert scn.frame_current == 42, f"preview.frames() left the playhead at {scn.frame_current}"
assert scn.render.engine == "BLENDER_EEVEE", scn.render.engine
assert scn.render.image_settings.media_type == prev_media_type, scn.render.image_settings.media_type
assert scn.render.image_settings.file_format == prev_file_format, (
    scn.render.image_settings.file_format
)
assert bpy.context.window.scene == prev_window_scene, (
    "preview.frames() switched the active window scene — it must render by name only"
)

# Direct regression check: the scene's camera sees a bright red plane on a transparent/black
# background. If frames() falls back to opengl()-style ambient-viewport rendering (or any
# other wrong-content path), this reads as flat gray/black instead of red-dominant.
img = bpy.data.images.load(paths[0])
px = img.pixels[:]
n = len(px) // 4
avg_r = sum(px[i * 4] for i in range(n)) / n
avg_g = sum(px[i * 4 + 1] for i in range(n)) / n
avg_b = sum(px[i * 4 + 2] for i in range(n)) / n
assert avg_r > avg_g + 0.1 and avg_r > avg_b + 0.1, (
    f"expected a red-dominant frame, got avg rgb=({avg_r:.3f}, {avg_g:.3f}, {avg_b:.3f}) — "
    f"preview.frames() rendered the wrong content"
)
