"""gn.typewriter() types a string in character-by-character (nesting char_reveal()'s own
node group) with a blinking cursor driven by Scene Time, not keyframes -- confirmed live
against a real Blender session before this module existed (see gn.py's module docstring).
This pins that behaviour in the headless suite: revealed-character growth over a keyframed
Progress, and the cursor's visibility toggling as frames advance at a fixed Progress.
"""

import _bl
import bpy

cmt = _bl.setup()

ng = cmt.gn.typewriter()
assert bpy.data.node_groups.get("CMT Typewriter") is ng
assert ng.asset_data is not None, "typewriter() must asset_mark() its node group"

with cmt.journal.batch("fixture: gn typewriter"):
    scn = cmt.scene.new_scene("shot-gn-typewriter", fps=30, frame_range=(1, 90))
    mesh = bpy.data.meshes.new("GN_Typewriter_Mesh")
    obj = bpy.data.objects.new("GN_Typewriter", mesh)
    scn.collection.objects.link(obj)
    cmt.provenance.tag(obj, "gn-typewriter")
    mod = cmt.gn.apply(obj, ng)
    string_id = next(
        r["identifier"] for r in cmt.introspect.gn_inputs(obj) if r["name"] == "String"
    )
    getattr(mod.properties.inputs, string_id).value = "COMONTEUR"
    cmt.anim.tween(
        obj,
        cmt.gn.input_path(mod, "Progress"),
        None,
        frm=0.0,
        to=1.0,
        start=1,
        dur=40,
        ease="linear",
    )

# Idempotent by name -- re-building must not duplicate the node group.
assert cmt.gn.typewriter() is ng

depsgraph = bpy.context.evaluated_depsgraph_get()


def verts(frame: int) -> int:
    scn.frame_set(frame)
    depsgraph.update()
    eval_obj = obj.evaluated_get(depsgraph)
    me = eval_obj.to_mesh()
    n = len(me.vertices)
    eval_obj.to_mesh_clear()
    return n


v_start, v_mid, v_end = verts(1), verts(10), verts(20)
assert v_start < v_mid < v_end, (
    f"expected monotonic growth as Progress advances (reveal + a fixed-size cursor), "
    f"got {v_start} -> {v_mid} -> {v_end}"
)

# Cursor blink is Scene-Time-driven, not keyframed: past the tween's end (frame 41,
# Progress held at 1.0 by CONSTANT extrapolation), scrubbing frames alone must toggle the
# evaluated vertex count as the cursor appears/disappears.
counts_at_fixed_progress = set()
for frame in range(45, 75, 3):
    scn.frame_set(frame)
    depsgraph.update()
    eval_obj = obj.evaluated_get(depsgraph)
    me = eval_obj.to_mesh()
    counts_at_fixed_progress.add(len(me.vertices))
    eval_obj.to_mesh_clear()
assert len(counts_at_fixed_progress) == 2, (
    f"expected the cursor to blink on/off (exactly 2 distinct vertex counts) while "
    f"Progress holds at 1.0 past frame 41, got {counts_at_fixed_progress}"
)

# The keyframed input is diffed like any other object property -- no GN special-casing.
assert cmt.provenance.claimed_paths(obj) == set()
