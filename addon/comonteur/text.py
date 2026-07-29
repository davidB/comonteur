"""Text objects — SPEC.md §6 module table: styling, fit-to-box, per-character split.
Per docs/M3-FINDINGS.md (Check 1), per-character stagger uses real per-character
Objects, not a Geometry Nodes String to Curves tree — GN instances aren't
independently keyframeable, and §6.2 requires real F-curves.
"""

import bpy

from . import provenance


def create(scene, body, *, name=None, size=1.0, font=None, color=None):
    name = name or body[:24] or "Text"
    data = bpy.data.curves.new(name, type="FONT")
    data.body = body
    data.size = size
    if font is not None:
        data.font = font
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    provenance.tag(obj, name)
    if color is not None:
        style(obj, color=color)
    return obj


def style(obj, *, size=None, font=None, color=None):
    data = obj.data
    if size is not None:
        data.size = size
    if font is not None:
        data.font = font
    if color is not None:
        mat = data.materials[0] if data.materials else None
        if mat is None:
            mat = bpy.data.materials.new(f"{obj.name}.color")
            mat.use_nodes = True
            data.materials.append(mat)
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            rgba = (*color[:3], color[3] if len(color) > 3 else 1.0)
            bsdf.inputs["Base Color"].default_value = rgba
    return obj


def fit_to_box(obj, width, height, *, min_size=0.01, step=0.9):
    """No layout engine (§11): measure obj.dimensions after a depsgraph update,
    shrink iteratively until it fits.
    """
    bpy.context.view_layer.update()
    while (obj.dimensions.x > width or obj.dimensions.y > height) and obj.data.size > min_size:
        obj.data.size *= step
        bpy.context.view_layer.update()
    return obj


def split_chars(obj, *, spacing=0.0, space_width_factor=0.3):
    """Replace obj with one FONT object per character, left to right, positioned by
    each character's measured advance width — the fallback from docs/M3-FINDINGS.md
    Check 1 (GN String to Curves gives one multi-spline object, not N keyframeable
    objects). Space glyphs measure 0 width, so they fall back to size * factor.
    """
    scene = next(s for s in bpy.data.scenes if obj.name in s.objects)
    body, base_name, base_size, base_font = obj.data.body, obj.name, obj.data.size, obj.data.font
    origin = obj.location.copy()
    bpy.data.objects.remove(obj, do_unlink=True)

    chars = []
    cursor_x = origin.x
    for i, ch in enumerate(body):
        char_obj = create(scene, ch, name=f"{base_name}.{i}", size=base_size, font=base_font)
        char_obj.location = origin.copy()
        char_obj.location.x = cursor_x
        bpy.context.view_layer.update()
        advance = char_obj.dimensions.x or base_size * space_width_factor
        cursor_x += advance + spacing
        chars.append(char_obj)
    return chars
