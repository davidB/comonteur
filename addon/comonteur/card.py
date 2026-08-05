"""Card chrome — image plane + hairline border + soft shadow, the common HyperFrames
"card" pattern bundled into one call. Border/shadow are flat offset planes with
Emission-only materials, not raytraced shadows: new_scene(kind="2d") has no lights
(use_raytracing=False), and adding one for a single card would break that baseline
for every other object in frame.
"""

from pathlib import Path
from typing import Any

import bpy

from . import provenance


def _plane(scn: Any, name: str, w: float, h: float) -> Any:
    mesh = bpy.data.meshes.new(name)
    hw, hh = w / 2, h / 2
    verts = [(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)]
    mesh.from_pydata(verts, [], [[0, 1, 2, 3]])
    uv = mesh.uv_layers.new()
    for loop, co in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = co
    obj = bpy.data.objects.new(name, mesh)
    scn.collection.objects.link(obj)
    return obj


def _flat_material(obj: Any, rgba: tuple[float, ...]) -> None:
    mat = bpy.data.materials.new(f"{obj.name}.color")
    mat.use_nodes = True
    mat.blend_method = "BLEND"  # required for a later Alpha-input fade to have any effect
    obj.data.materials.append(mat)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    color = (*rgba[:3], rgba[3] if len(rgba) > 3 else 1.0)
    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, color[3])
    bsdf.inputs["Emission Color"].default_value = color
    bsdf.inputs["Emission Strength"].default_value = 1.0
    bsdf.inputs["Alpha"].default_value = color[
        3
    ]  # Color socket alpha is ignored by Principled BSDF


def _image_material(obj: Any, image: Any) -> None:
    mat = bpy.data.materials.new(f"{obj.name}.image")
    mat.use_nodes = True
    mat.blend_method = "BLEND"  # required for a later Alpha-input fade to have any effect
    obj.data.materials.append(mat)
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Emission Strength"].default_value = 1.0


def reorigin_left(obj: Any) -> None:
    """Shift obj's mesh so local X spans 0..w instead of -w/2..w/2 (world position
    unchanged) -- so a scale.x tween from 0 to 1 grows the plane from its left edge
    instead of from its center. For progress bars / underline reveals built on any
    _plane()-based object (card image/border/shadow, text.highlight_bg() quads).
    """
    mesh = obj.data
    min_x = min(v.co.x for v in mesh.vertices)
    for v in mesh.vertices:
        v.co.x -= min_x
    obj.location.x += min_x


def create(
    scn: Any,
    image_path: str,
    w: float,
    h: float,
    border_color: tuple[float, ...] | None = None,
    *,
    border_width: float = 0.02,
    shadow: bool = True,
    name: str | None = None,
) -> Any:
    """Build a card bundle (image + optional border + optional shadow), parented
    under a root Empty so the whole card moves with one anim.tween() on the root.
    """
    name = name or Path(image_path).stem
    root = bpy.data.objects.new(name, None)
    scn.collection.objects.link(root)
    provenance.tag(root, name)

    # Camera looks toward -Z, so higher z is closer to camera. Stack closest-to-farthest
    # as image, border (visible only as a frame in the margin), shadow.
    image_z, border_z, shadow_z = 0.0, -0.001, -0.002

    if shadow:
        shadow_obj = _plane(scn, f"{name}.shadow", w * 1.05, h * 1.05)
        shadow_obj.location = (0.03 * w, -0.03 * h, shadow_z)
        _flat_material(shadow_obj, (0.0, 0.0, 0.0, 0.35))
        shadow_obj.parent = root
        provenance.tag(shadow_obj, f"{name}.shadow")

    if border_color is not None:
        border_obj = _plane(scn, f"{name}.border", w + 2 * border_width, h + 2 * border_width)
        border_obj.location = (0, 0, border_z)
        _flat_material(border_obj, border_color)
        border_obj.parent = root
        provenance.tag(border_obj, f"{name}.border")

    image_obj = _plane(scn, f"{name}.image", w, h)
    image_obj.location = (0, 0, image_z)
    img = bpy.data.images.load(image_path, check_existing=True)
    _image_material(image_obj, img)
    image_obj.parent = root
    provenance.tag(image_obj, f"{name}.image")

    return root
