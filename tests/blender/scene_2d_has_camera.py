"""new_scene(kind="2d") must set up a camera by itself: preview.frames() renders
through "the scene's own camera" and Blender's ops.render.render() raises a raw
"No camera found" RuntimeError with none set. scene.new_scene() deliberately never
inherits one (0 inherited objects from bpy.ops.scene.new(type="EMPTY")), so kind="2d"
now calls scene.add_camera() itself.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-camera", kind="2d", fps=30, frame_range=(1, 90))

cam = scn.camera
assert cam is not None, "new_scene(kind='2d') left the scene cameraless"
assert cam.data.type == "ORTHO", cam.data.type
assert cam.data.sensor_fit == "VERTICAL", cam.data.sensor_fit
assert cam.data.ortho_scale == cmt.const.FRAME_HEIGHT, cam.data.ortho_scale
assert cmt.provenance.origin(cam) == "agent", cmt.provenance.origin(cam)

# preview.frames() must succeed with zero extra camera setup.
paths = cmt.preview.frames(scn, [1])
assert len(paths) == 1, paths
