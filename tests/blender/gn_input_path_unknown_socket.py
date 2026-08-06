"""gn.input_path() raises KeyError on a socket name that does not exist on the modifier's
node group, rather than silently returning a bogus path anim.tween() would fail on later
with a less obvious error. introspect.gn_inputs() must also skip the Geometry-typed input
socket -- it has no scalar `.value` to report.
"""

import _bl
import bpy

cmt = _bl.setup()

ng = cmt.gn.char_reveal()

with cmt.journal.batch("fixture: gn unknown socket"):
    scn = cmt.scene.new_scene("shot-gn-unknown", fps=30, frame_range=(1, 10))
    mesh = bpy.data.meshes.new("GN_Unknown_Mesh")
    obj = bpy.data.objects.new("GN_Unknown", mesh)
    scn.collection.objects.link(obj)
    cmt.provenance.tag(obj, "gn-unknown")
    mod = cmt.gn.apply(obj, ng)

err = _bl.raises(KeyError, lambda: cmt.gn.input_path(mod, "Nonexistent"))
assert err is not None, "input_path() must raise KeyError for an unknown socket name"

rows = cmt.introspect.gn_inputs(obj)
names = {r["name"] for r in rows if "name" in r}
assert "Geometry" not in names, f"gn_inputs() must skip the Geometry socket, got {rows}"
assert {"String", "Size", "Progress", "Spacing", "Window"} <= names, rows
