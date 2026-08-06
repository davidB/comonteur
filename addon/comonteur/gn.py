"""Geometry Nodes effect builders — non-baked, tunable procedural VFX (docs/library.md
§6.2/§9). A GN modifier input is an ordinary Object RNA path
(`modifiers["Name"].properties.inputs.Socket_N.value`, Blender 5.2's post-idprop API —
the old `modifier["Socket_N"]` idprop form raises TypeError here), so anim.tween()/
stagger()/drive() already animate it with zero changes: a GN effect's driving parameter
is a real keyframe like any other, and introspect.animated_paths()/provenance.claimed_paths()
already see it for free, same as any other object property.

What is new here is building the node graphs and resolving a named input to that RNA path
(input_path(), mirroring text.color_path()'s "resolve the real identifier, don't hand-type
it" precedent). Per-instance timing (e.g. per-character stagger) deliberately stays out of
individual keyframes: one keyframed "Progress" input drives an Index-node formula inside the
tree, non-destructive and tunable by changing Spacing/Window rather than touching N objects.
Confirmed working end to end (build, keyframe, save/reload, provenance) via a live spike
before this module existed.
"""

import math
from typing import Any

import bpy


def char_reveal(name: str = "CMT Char Reveal") -> Any:
    """Build (once) a reusable node group: String-to-Curves characters revealed
    left-to-right by a single "Progress" input (0-1) — each character's delay comes from
    its instance Index inside the tree, so there are zero per-character keyframes to
    manage or retime. Idempotent by name, like scene.new_scene() is by cmt_id: re-calling
    returns the existing group rather than duplicating it. Marked as a Blender asset so it
    joins the project's reusable-effect catalog (§9) the first time it is built.

    Modifier inputs on the result: Geometry (unused passthrough), String, Size, Progress,
    Spacing (per-character delay), Window (reveal duration per character, in Progress units).
    """
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        return existing

    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket(
        "String", in_out="INPUT", socket_type="NodeSocketString"
    ).default_value = "Text"
    iface.new_socket("Size", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 1.0
    s_progress = iface.new_socket("Progress", in_out="INPUT", socket_type="NodeSocketFloat")
    s_progress.default_value = 0.0
    s_progress.min_value = 0.0
    s_progress.max_value = 1.0
    iface.new_socket("Spacing", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 0.08
    iface.new_socket("Window", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 0.15

    nodes, links = ng.nodes, ng.links
    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-800, 0)
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (900, 0)
    n_str = nodes.new("GeometryNodeStringToCurves")
    n_str.location = (-500, 200)
    n_index = nodes.new("GeometryNodeInputIndex")
    n_index.location = (-500, -200)
    n_mul = nodes.new("ShaderNodeMath")
    n_mul.operation = "MULTIPLY"
    n_mul.location = (-300, -200)
    n_sub = nodes.new("ShaderNodeMath")
    n_sub.operation = "SUBTRACT"
    n_sub.location = (-100, -200)
    n_map = nodes.new("ShaderNodeMapRange")
    n_map.location = (100, -200)
    n_map.inputs["From Min"].default_value = 0.0
    n_map.clamp = True
    n_combine = nodes.new("ShaderNodeCombineXYZ")
    n_combine.location = (300, -200)
    n_scale = nodes.new("GeometryNodeScaleInstances")
    n_scale.location = (300, 100)
    n_realize = nodes.new("GeometryNodeRealizeInstances")
    n_realize.location = (550, 100)
    n_fill = nodes.new("GeometryNodeFillCurve")  # closed glyph-outline splines -> solid mesh
    n_fill.location = (700, 100)

    links.new(n_in.outputs["String"], n_str.inputs["String"])
    links.new(n_in.outputs["Size"], n_str.inputs["Size"])
    links.new(n_in.outputs["Progress"], n_sub.inputs[0])
    links.new(n_index.outputs["Index"], n_mul.inputs[0])
    links.new(n_in.outputs["Spacing"], n_mul.inputs[1])
    links.new(n_mul.outputs["Value"], n_sub.inputs[1])
    links.new(n_sub.outputs["Value"], n_map.inputs["Value"])
    links.new(n_in.outputs["Window"], n_map.inputs["From Max"])
    links.new(n_map.outputs["Result"], n_combine.inputs["X"])
    links.new(n_map.outputs["Result"], n_combine.inputs["Y"])
    links.new(n_map.outputs["Result"], n_combine.inputs["Z"])
    links.new(n_str.outputs["Curve Instances"], n_scale.inputs["Instances"])
    links.new(n_combine.outputs["Vector"], n_scale.inputs["Scale"])
    links.new(n_scale.outputs["Instances"], n_realize.inputs["Geometry"])
    links.new(n_realize.outputs["Geometry"], n_fill.inputs["Curve"])
    links.new(n_fill.outputs["Mesh"], n_out.inputs["Geometry"])

    ng.asset_mark()
    ng.asset_data.description = (
        "Reveals text characters left-to-right from a single Progress input (0-1) — "
        "non-destructive, no per-character keyframes."
    )
    return ng


def typewriter(name: str = "CMT Typewriter") -> Any:
    """Build (once) a reusable node group: a live-typing text reveal with a blinking
    cursor, both driven from ordinary modifier inputs — human-editable in Blender's UI,
    no agent round-trip needed to change the displayed text or retime it. Idempotent by
    name and asset-marked, same as char_reveal().

    Reuses char_reveal()'s own node group by nesting it (a Group node) rather than
    duplicating its graph — one place owns the character-reveal formula, and any future
    improvement to it benefits typewriter() too. Defaults Window much smaller than
    char_reveal()'s own default: an (almost) instant per-character pop instead of a
    smooth per-character grow, matching a typewriter's character-at-a-time look; still
    tunable for a softer transition.

    The cursor is a thin quad whose visibility blinks from Scene Time (not keyframes —
    BlinkHz is a rate, not a timed event), so it keeps blinking through any hold after
    typing finishes. Its X position tracks the reveal edge via CursorAdvance, a tunable
    per-character pitch in local units: exact for a monospace font, approximate for a
    proportional one (Geometry Nodes has no font-metrics query to do better — same
    caveat char_reveal()'s own Spacing input already carries).

    Modifier inputs: Geometry (unused passthrough), String, Size, Progress, Spacing,
    Window, CursorWidth, CursorHeight, CursorAdvance, BlinkHz.
    """
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        return existing

    reveal = char_reveal()

    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket(
        "String", in_out="INPUT", socket_type="NodeSocketString"
    ).default_value = "Text"
    iface.new_socket("Size", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 1.0
    s_progress = iface.new_socket("Progress", in_out="INPUT", socket_type="NodeSocketFloat")
    s_progress.default_value = 0.0
    s_progress.min_value = 0.0
    s_progress.max_value = 1.0
    iface.new_socket("Spacing", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 0.08
    iface.new_socket("Window", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 0.01
    iface.new_socket(
        "CursorWidth", in_out="INPUT", socket_type="NodeSocketFloat"
    ).default_value = 0.04
    iface.new_socket(
        "CursorHeight", in_out="INPUT", socket_type="NodeSocketFloat"
    ).default_value = 1.0
    iface.new_socket(
        "CursorAdvance", in_out="INPUT", socket_type="NodeSocketFloat"
    ).default_value = 0.6
    iface.new_socket("BlinkHz", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 2.0

    nodes, links = ng.nodes, ng.links
    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-1200, 0)
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (1200, 0)

    n_group = nodes.new("GeometryNodeGroup")
    n_group.node_tree = reveal
    n_group.location = (-900, 200)
    links.new(n_in.outputs["String"], n_group.inputs["String"])
    links.new(n_in.outputs["Size"], n_group.inputs["Size"])
    links.new(n_in.outputs["Progress"], n_group.inputs["Progress"])
    links.new(n_in.outputs["Spacing"], n_group.inputs["Spacing"])
    links.new(n_in.outputs["Window"], n_group.inputs["Window"])

    # Cursor X tracks the reveal edge: (Progress / Spacing) * CursorAdvance.
    n_grid = nodes.new("GeometryNodeMeshGrid")
    n_grid.location = (-900, -300)
    links.new(n_in.outputs["CursorWidth"], n_grid.inputs["Size X"])
    links.new(n_in.outputs["CursorHeight"], n_grid.inputs["Size Y"])

    n_div = nodes.new("ShaderNodeMath")
    n_div.operation = "DIVIDE"
    n_div.location = (-700, -300)
    links.new(n_in.outputs["Progress"], n_div.inputs[0])
    links.new(n_in.outputs["Spacing"], n_div.inputs[1])

    n_mul_adv = nodes.new("ShaderNodeMath")
    n_mul_adv.operation = "MULTIPLY"
    n_mul_adv.location = (-500, -300)
    links.new(n_div.outputs["Value"], n_mul_adv.inputs[0])
    links.new(n_in.outputs["CursorAdvance"], n_mul_adv.inputs[1])

    n_combine = nodes.new("ShaderNodeCombineXYZ")
    n_combine.location = (-500, -250)
    links.new(n_mul_adv.outputs["Value"], n_combine.inputs["X"])

    n_xform = nodes.new("GeometryNodeTransform")
    n_xform.location = (-300, -300)
    links.new(n_grid.outputs["Mesh"], n_xform.inputs["Geometry"])
    links.new(n_combine.outputs["Vector"], n_xform.inputs["Translation"])

    # Blink: sin(Seconds * BlinkHz * 2*pi) > 0 -- driven by Scene Time, not keyframes,
    # so the cursor keeps blinking through any hold after Progress reaches 1.0.
    n_time = nodes.new("GeometryNodeInputSceneTime")
    n_time.location = (-900, -500)

    n_mul_hz = nodes.new("ShaderNodeMath")
    n_mul_hz.operation = "MULTIPLY"
    n_mul_hz.location = (-700, -500)
    links.new(n_time.outputs["Seconds"], n_mul_hz.inputs[0])
    links.new(n_in.outputs["BlinkHz"], n_mul_hz.inputs[1])

    n_mul_2pi = nodes.new("ShaderNodeMath")
    n_mul_2pi.operation = "MULTIPLY"
    n_mul_2pi.location = (-500, -500)
    n_mul_2pi.inputs[1].default_value = 2 * math.pi
    links.new(n_mul_hz.outputs["Value"], n_mul_2pi.inputs[0])

    n_sine = nodes.new("ShaderNodeMath")
    n_sine.operation = "SINE"
    n_sine.location = (-300, -500)
    links.new(n_mul_2pi.outputs["Value"], n_sine.inputs[0])

    n_gt = nodes.new("FunctionNodeCompare")
    n_gt.operation = "GREATER_THAN"
    n_gt.data_type = "FLOAT"
    n_gt.location = (-100, -500)
    links.new(n_sine.outputs["Value"], n_gt.inputs[0])

    n_not = nodes.new("FunctionNodeBooleanMath")
    n_not.operation = "NOT"
    n_not.location = (-100, -350)
    links.new(n_gt.outputs["Result"], n_not.inputs[0])

    n_del = nodes.new("GeometryNodeDeleteGeometry")
    n_del.location = (-100, -300)
    links.new(n_xform.outputs["Geometry"], n_del.inputs["Geometry"])
    links.new(n_not.outputs["Boolean"], n_del.inputs["Selection"])

    n_join = nodes.new("GeometryNodeJoinGeometry")
    n_join.location = (500, 0)
    links.new(n_group.outputs["Geometry"], n_join.inputs["Geometry"])
    links.new(n_del.outputs["Geometry"], n_join.inputs["Geometry"])
    links.new(n_join.outputs["Geometry"], n_out.inputs["Geometry"])

    ng.asset_mark()
    ng.asset_data.description = (
        "Types a string in character-by-character with a blinking cursor — String/"
        "Progress/timing are ordinary modifier inputs, editable in the UI with no "
        "agent call needed."
    )
    return ng


def fracture(name: str = "CMT Fracture") -> Any:
    """Build (once) a reusable node group: per-face shatter/explode driven by a single
    "Progress" input (0-1) — each face's random outward direction comes from its face
    index inside the tree, so there are zero per-fragment keyframes to manage. Idempotent
    by name and asset-marked, same as char_reveal(). Unlike char_reveal()'s Geometry input
    (an unused passthrough), this one operates on the incoming mesh.

    Splits every edge first (GeometryNodeSplitEdges) so each face becomes its own
    disconnected island before displacing it -- otherwise shared vertices at face
    boundaries would blend neighboring faces' random directions into visible seams.
    Per-face centroid and random direction are computed at FACE domain and read back at
    POINT domain via Blender's own attribute-domain interpolation (Store Named Attribute
    + Named Attribute, not a custom evaluator).

    Modifier inputs: Geometry (the mesh to fracture), Progress, Distance (max explode
    radius), Scale (per-fragment shrink toward its own centroid, for gaps), Seed.
    """
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        return existing

    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    iface = ng.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    s_progress = iface.new_socket("Progress", in_out="INPUT", socket_type="NodeSocketFloat")
    s_progress.default_value = 0.0
    s_progress.min_value = 0.0
    s_progress.max_value = 1.0
    iface.new_socket("Distance", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 1.0
    iface.new_socket("Scale", in_out="INPUT", socket_type="NodeSocketFloat").default_value = 0.85
    iface.new_socket("Seed", in_out="INPUT", socket_type="NodeSocketInt").default_value = 0

    nodes, links = ng.nodes, ng.links
    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-1200, 0)
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (1200, 0)

    n_split = nodes.new("GeometryNodeSplitEdges")
    n_split.location = (-1000, 0)
    links.new(n_in.outputs["Geometry"], n_split.inputs["Mesh"])

    # Per-face centroid: Store Named Attribute (FACE domain) reading point-domain
    # Position auto-averages it down to one value per face.
    n_pos = nodes.new("GeometryNodeInputPosition")
    n_pos.location = (-1000, -200)
    n_store_center = nodes.new("GeometryNodeStoreNamedAttribute")
    n_store_center.domain = "FACE"
    n_store_center.data_type = "FLOAT_VECTOR"
    n_store_center.location = (-800, -100)
    n_store_center.inputs["Name"].default_value = "cmt_frac_center"
    links.new(n_split.outputs["Mesh"], n_store_center.inputs["Geometry"])
    links.new(n_pos.outputs["Position"], n_store_center.inputs["Value"])

    # Per-face random direction, seeded by face Index + the Seed input.
    n_index = nodes.new("GeometryNodeInputIndex")
    n_index.location = (-1000, -400)
    n_rand = nodes.new("FunctionNodeRandomValue")
    n_rand.data_type = "FLOAT_VECTOR"
    n_rand.location = (-800, -400)
    links.new(n_index.outputs["Index"], n_rand.inputs["ID"])
    links.new(n_in.outputs["Seed"], n_rand.inputs["Seed"])

    n_store_dir = nodes.new("GeometryNodeStoreNamedAttribute")
    n_store_dir.domain = "FACE"
    n_store_dir.data_type = "FLOAT_VECTOR"
    n_store_dir.location = (-600, -300)
    n_store_dir.inputs["Name"].default_value = "cmt_frac_dir"
    links.new(n_store_center.outputs["Geometry"], n_store_dir.inputs["Geometry"])
    links.new(n_rand.outputs["Value"], n_store_dir.inputs["Value"])

    n_named_center = nodes.new("GeometryNodeInputNamedAttribute")
    n_named_center.data_type = "FLOAT_VECTOR"
    n_named_center.location = (-400, 100)
    n_named_center.inputs["Name"].default_value = "cmt_frac_center"
    n_named_dir = nodes.new("GeometryNodeInputNamedAttribute")
    n_named_dir.data_type = "FLOAT_VECTOR"
    n_named_dir.location = (-400, -100)
    n_named_dir.inputs["Name"].default_value = "cmt_frac_dir"
    n_pos2 = nodes.new("GeometryNodeInputPosition")
    n_pos2.location = (-400, 300)

    # shrunk_pos = center + (Position - center) * Scale  (per-fragment gap)
    n_sub = nodes.new("ShaderNodeVectorMath")
    n_sub.operation = "SUBTRACT"
    n_sub.location = (-200, 300)
    links.new(n_pos2.outputs["Position"], n_sub.inputs[0])
    links.new(n_named_center.outputs["Attribute"], n_sub.inputs[1])

    n_scale_local = nodes.new("ShaderNodeVectorMath")
    n_scale_local.operation = "SCALE"
    n_scale_local.location = (0, 300)
    links.new(n_sub.outputs["Vector"], n_scale_local.inputs["Vector"])
    links.new(n_in.outputs["Scale"], n_scale_local.inputs["Scale"])

    n_shrunk_pos = nodes.new("ShaderNodeVectorMath")
    n_shrunk_pos.operation = "ADD"
    n_shrunk_pos.location = (200, 300)
    links.new(n_named_center.outputs["Attribute"], n_shrunk_pos.inputs[0])
    links.new(n_scale_local.outputs["Vector"], n_shrunk_pos.inputs[1])

    # explode_offset = normalize(dir) * Distance * Progress
    n_norm = nodes.new("ShaderNodeVectorMath")
    n_norm.operation = "NORMALIZE"
    n_norm.location = (-200, -100)
    links.new(n_named_dir.outputs["Attribute"], n_norm.inputs[0])

    n_mul_amt = nodes.new("ShaderNodeMath")
    n_mul_amt.operation = "MULTIPLY"
    n_mul_amt.location = (0, -100)
    links.new(n_in.outputs["Distance"], n_mul_amt.inputs[0])
    links.new(n_in.outputs["Progress"], n_mul_amt.inputs[1])

    n_explode = nodes.new("ShaderNodeVectorMath")
    n_explode.operation = "SCALE"
    n_explode.location = (200, -100)
    links.new(n_norm.outputs["Vector"], n_explode.inputs["Vector"])
    links.new(n_mul_amt.outputs["Value"], n_explode.inputs["Scale"])

    n_final = nodes.new("ShaderNodeVectorMath")
    n_final.operation = "ADD"
    n_final.location = (400, 100)
    links.new(n_shrunk_pos.outputs["Vector"], n_final.inputs[0])
    links.new(n_explode.outputs["Vector"], n_final.inputs[1])

    n_setpos = nodes.new("GeometryNodeSetPosition")
    n_setpos.location = (600, 0)
    links.new(n_store_dir.outputs["Geometry"], n_setpos.inputs["Geometry"])
    links.new(n_final.outputs["Vector"], n_setpos.inputs["Position"])
    links.new(n_setpos.outputs["Geometry"], n_out.inputs["Geometry"])

    ng.asset_mark()
    ng.asset_data.description = (
        "Per-face shatter/explode from a single Progress input (0-1) — random per-face "
        "direction from face index, non-destructive."
    )
    return ng


def apply(obj: Any, node_group: Any, name: str | None = None) -> Any:
    """Add node_group as a Nodes modifier on obj. Returns the modifier, for input_path() +
    anim.tween()/stagger()/drive() and for setting non-animated inputs via journal.set().
    """
    mod = obj.modifiers.new(name or node_group.name, "NODES")
    mod.node_group = node_group
    return mod


def input_path(mod: Any, socket_name: str) -> str:
    """RNA path, relative to the object owning `mod`, for tween()/stagger()/drive() (or
    journal.set(), for a non-animated input) to target a GN modifier input by its
    human-readable socket name. Blender 5.2 moved modifier inputs off id-properties onto
    `modifier.properties.inputs.Socket_N.value` — this is the one place that needs to know
    the generated `Socket_N` identifier, same "resolve the real identifier, don't hand-type
    it" precedent as text.color_path()/text.alpha_path().
    """
    for item in mod.node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == socket_name:
            return f'modifiers["{mod.name}"].properties.inputs.{item.identifier}.value'
    raise KeyError(f"{socket_name!r} not found on {mod.node_group.name!r}'s inputs")
