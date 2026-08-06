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
