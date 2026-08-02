"""card.create() bundles image + border + shadow planes under one root Empty — the
common HyperFrames "card" pattern that was dropped on real shots because building
it by hand per-object was too much.
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

    children = [o for o in scn.objects if o.parent == root]
    assert len(children) == 3, [c.name for c in children]
    names = {c.name for c in children}
    assert names == {"fixture.image", "fixture.border", "fixture.shadow"}, names

    for obj in [root, *children]:
        assert cmt.provenance.origin(obj) == "agent", (obj.name, cmt.provenance.origin(obj))
