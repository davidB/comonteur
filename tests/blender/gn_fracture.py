"""gn.fracture() shatters/explodes a mesh from a single keyframed Progress input -- each
face's random outward direction comes from its face index inside the tree, zero
per-fragment keyframes. Confirmed working end to end via a live spike before this module
existed (see gn.py's module docstring). This pins that behaviour in the headless suite:
the evaluated mesh's bounding-box extent must grow monotonically as Progress advances.
"""

import _bl
import bpy

cmt = _bl.setup()

ng = cmt.gn.fracture()
assert bpy.data.node_groups.get("CMT Fracture") is ng
assert ng.asset_data is not None, "fracture() must asset_mark() its node group"


def _grid_mesh(name: str, n: int = 4, size: float = 2.0) -> bpy.types.Mesh:
    """An n x n grid of quads, manually built (no operator -- avoids depending on a
    VIEW_3D context this headless -b run doesn't have)."""
    step = size / n
    half = size / 2
    verts = [(-half + i * step, -half + j * step, 0.0) for j in range(n + 1) for i in range(n + 1)]
    faces = [
        [j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i]
        for j in range(n)
        for i in range(n)
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    return mesh


with cmt.journal.batch("fixture: gn fracture"):
    scn = cmt.scene.new_scene("shot-gn-fracture", fps=30, frame_range=(1, 40))
    obj = bpy.data.objects.new("GN_Fracture", _grid_mesh("GN_Fracture_Mesh"))
    scn.collection.objects.link(obj)
    cmt.provenance.tag(obj, "gn-fracture")
    mod = cmt.gn.apply(obj, ng)
    cmt.anim.tween(
        obj,
        cmt.gn.input_path(mod, "Progress"),
        None,
        frm=0.0,
        to=1.0,
        start=1,
        dur=20,
        ease="linear",
    )

# Idempotent by name -- re-building must not duplicate the node group.
assert cmt.gn.fracture() is ng

depsgraph = bpy.context.evaluated_depsgraph_get()


def bbox_extent(frame: int) -> float:
    scn.frame_set(frame)
    depsgraph.update()
    eval_obj = obj.evaluated_get(depsgraph)
    me = eval_obj.to_mesh()
    xs = [v.co.x for v in me.vertices]
    extent = max(xs) - min(xs)
    eval_obj.to_mesh_clear()
    return extent


e_start, e_mid, e_end = bbox_extent(1), bbox_extent(10), bbox_extent(20)
assert e_start < e_mid < e_end, (
    f"expected monotonic bbox growth as Progress explodes the fragments outward, "
    f"got {e_start} -> {e_mid} -> {e_end}"
)

# The keyframed input is diffed like any other object property -- no GN special-casing.
assert cmt.provenance.claimed_paths(obj) == set()
