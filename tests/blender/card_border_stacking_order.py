"""card.create() must stack image closer to the camera than border, and border
closer than shadow -- otherwise the (larger, opaque) border plane fully occludes
the image behind it. Regression test for GitHub issue #2.
"""

import tempfile
from pathlib import Path

import _bl
import bpy

cmt = _bl.setup()

with tempfile.TemporaryDirectory() as tmp:
    img_path = str(Path(tmp) / "fixture.png")
    img = bpy.data.images.new("fixture", 2, 2)
    img.filepath_raw = img_path
    img.file_format = "PNG"
    img.save()

    with cmt.journal.batch("card"):
        scn = cmt.scene.new_scene("shot-card", fps=30, frame_range=(1, 90))
        root = cmt.card.create(scn, img_path, w=2.0, h=1.0, border_color=(1, 0, 0, 1), shadow=True)

    children = {o.name: o for o in scn.objects if o.parent == root}
    image_z = children["fixture.image"].location.z
    border_z = children["fixture.border"].location.z
    shadow_z = children["fixture.shadow"].location.z

    assert image_z > border_z > shadow_z, (image_z, border_z, shadow_z)
