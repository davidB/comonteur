"""gn.char_reveal() reveals characters left-to-right from one keyframed Progress input —
zero per-character keyframes, confirmed by evaluated vertex count growing over the reveal
window. Verified interactively against a live Blender before this module existed (see the
GN evaluation plan); this pins that behaviour in the headless suite.
"""

import _bl
import bpy

cmt = _bl.setup()

ng = cmt.gn.char_reveal()
assert bpy.data.node_groups.get("CMT Char Reveal") is ng
assert ng.asset_data is not None, "char_reveal() must asset_mark() its node group (SPEC.md §9)"

with cmt.journal.batch("fixture: gn reveal"):
    scn = cmt.scene.new_scene("shot-gn", fps=30, frame_range=(1, 90))
    mesh = bpy.data.meshes.new("GN_Reveal_Mesh")
    obj = bpy.data.objects.new("GN_Reveal", mesh)
    scn.collection.objects.link(obj)
    cmt.provenance.tag(obj, "gn-reveal")
    mod = cmt.gn.apply(obj, ng)
    string_id = next(
        r["identifier"] for r in cmt.introspect.gn_inputs(obj) if r["name"] == "String"
    )
    # Long enough that default spacing/window don't finish revealing well before dur's end
    # (9 chars * 0.08 spacing + 0.15 window ~= 0.79 of the Progress range) -- a short string
    # plateaus almost immediately and the growth-check below would false-fail on the plateau.
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

# Idempotent by name — re-building must not duplicate the node group.
assert cmt.gn.char_reveal() is ng

rows = cmt.introspect.gn_inputs(obj)
by_name = {r["name"]: r for r in rows}
assert by_name["String"]["value"] == "COMONTEUR", rows
assert by_name["Progress"]["identifier"].startswith("Socket_"), rows

animated = cmt.introspect.animated_paths(scn)
row = next(r for r in animated if r["object"] == obj.name)
assert row["data_path"] == cmt.gn.input_path(mod, "Progress"), row
assert row["keys"] == 2, row

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
    f"expected monotonic growth as Progress advances (no per-instance keyframes involved), "
    f"got {v_start} -> {v_mid} -> {v_end}"
)

# The keyframed input is diffed like any other object property — no GN special-casing needed.
assert cmt.provenance.claimed_paths(obj) == set()
