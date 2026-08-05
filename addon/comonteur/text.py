"""Text objects — SPEC.md §6 module table: styling, fit-to-box, per-character split.
Per docs/M3-FINDINGS.md (Check 1), per-character stagger uses real per-character
Objects, not a Geometry Nodes String to Curves tree — GN instances aren't
independently keyframeable, and §6.2 requires real F-curves.
"""

from typing import Any, Literal

import bpy
from mathutils import Vector

from . import anim, card, provenance


def create(
    scene: Any,
    body: str,
    *,
    name: str | None = None,
    size: float = 1.0,
    font: Any = None,
    color: tuple[float, ...] | None = None,
    shading: Literal["flat", "lit"] = "flat",
) -> Any:
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
        style(obj, color=color, shading=shading)
    return obj


def style(
    obj: Any,
    *,
    size: float | None = None,
    font: Any = None,
    color: tuple[float, ...] | None = None,
    shading: Literal["flat", "lit"] = "flat",
) -> Any:
    """color defaults to flat/emission shading — new_scene(kind="2d") has no lights,
    so Base-Color-only Principled BSDF renders black. shading="lit" restores plain
    Base Color for scenes with actual lighting.
    """
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
            mat.blend_method = "BLEND"  # required for a later Alpha-input fade to have any effect
            data.materials.append(mat)
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            rgba = (*color[:3], color[3] if len(color) > 3 else 1.0)
            if shading == "flat":
                bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, rgba[3])
                bsdf.inputs["Emission Color"].default_value = rgba
                bsdf.inputs["Emission Strength"].default_value = 1.0
            else:
                bsdf.inputs["Base Color"].default_value = rgba
                bsdf.inputs["Emission Strength"].default_value = 0.0
    return obj


def fit_to_box(
    obj: Any, width: float, height: float, *, min_size: float = 0.01, step: float = 0.9
) -> Any:
    """No layout engine (§11): measure obj.dimensions after a depsgraph update,
    shrink iteratively until it fits.
    """
    bpy.context.view_layer.update()
    while (obj.dimensions.x > width or obj.dimensions.y > height) and obj.data.size > min_size:
        obj.data.size *= step
        bpy.context.view_layer.update()
    return obj


def measure(obj: Any) -> dict[str, Any]:
    """Read-only bounding box in world space, for positioning underlines/accents
    without restructuring the text object (§11: no layout engine). Same
    view_layer.update() + dimensions precedent as fit_to_box().

    obj must be visible (hide_viewport=False) at the current frame: Blender freezes
    matrix_world (and anything derived from it -- dimensions, this function,
    measure_many()) for a hidden object, with no error. Measure/position everything
    first, hide as the last step -- not the reverse.
    """
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mins = (min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners))
    maxs = (max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners))
    return {
        "width": obj.dimensions.x,
        "height": obj.dimensions.y,
        "depth": obj.dimensions.z,
        "min": mins,
        "max": maxs,
    }


def check_fonts(scn: Any) -> list[dict[str, Any]]:
    """Read-only: FONT objects still on Blender's built-in default font — a new
    FONT curve starts on "Bfont Regular" (filepath "<builtin>"), not None, so a
    forgotten font= is easy to miss in a low-res preview.
    """
    return [
        {"name": obj.name}
        for obj in scn.objects
        if obj.type == "FONT" and obj.data.font.filepath == "<builtin>"
    ]


def _captured_color(obj: Any) -> tuple[tuple[float, ...], Literal["flat", "lit"]] | None:
    """Read back the (color, shading) pair a prior style(color=...) call wrote, so
    split_chars() can restyle its output instead of leaving it material-less.
    """
    mats = obj.data.materials
    if not mats or mats[0] is None:
        return None
    bsdf = mats[0].node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return None
    base = tuple(bsdf.inputs["Base Color"].default_value)
    if any(base[:3]):
        return base, "lit"
    return tuple(bsdf.inputs["Emission Color"].default_value), "flat"


def split_chars(obj: Any, *, spacing: float = 0.0, space_width_factor: float = 0.3) -> list[Any]:
    """Replace obj with one FONT object per character, left to right, positioned by
    each character's measured advance width — the fallback from docs/M3-FINDINGS.md
    Check 1 (GN String to Curves gives one multi-spline object, not N keyframeable
    objects). Space glyphs measure 0 width, so they fall back to size * factor.

    Preserves obj's color (if any) and its true left edge -- measure()'s world-space
    min.x, not obj.location.x, since align_x='CENTER'/'RIGHT' otherwise leaves the
    output shifted from where the source text visually was.
    """
    scene = next(s for s in bpy.data.scenes if obj.name in s.objects)
    body, base_name, base_size, base_font = obj.data.body, obj.name, obj.data.size, obj.data.font
    color = _captured_color(obj)
    origin = obj.location.copy()
    left_x = measure(obj)["min"][0]
    bpy.data.objects.remove(obj, do_unlink=True)

    chars = []
    cursor_x = left_x
    for i, ch in enumerate(body):
        char_obj = create(scene, ch, name=f"{base_name}.{i}", size=base_size, font=base_font)
        char_obj.location = origin.copy()
        char_obj.location.x = cursor_x
        if color is not None:
            style(char_obj, color=color[0], shading=color[1])
        bpy.context.view_layer.update()
        advance = char_obj.dimensions.x or base_size * space_width_factor
        cursor_x += advance + spacing
        chars.append(char_obj)
    return chars


def split_spans(
    obj: Any,
    spans: list[tuple[int, int]] | list[tuple[int, int, dict[str, Any]]],
    *,
    spacing: float = 0.0,
    space_width_factor: float = 0.3,
) -> list[Any]:
    """Replace obj with one FONT object per (start, end[, props]) span, left to right —
    the word/phrase-granularity counterpart to split_chars(): use this when spans, not
    individual characters, need independent styling/positioning (e.g. a 2-color 2-word
    heading), since split_chars() + style_spans() costs one object per glyph even when
    only 2 are ever restyled independently.

    Text not covered by any span -- leading text before the first span, a skipped range
    between two spans, or trailing text after the last span -- is preserved as its own
    unstyled (base color/font) object, so a partial span list still renders the full
    string; only a gap that's pure whitespace is collapsed into a cursor advance of
    size * space_width_factor per char instead of becoming an object (same fallback
    split_chars() uses for a zero-width space glyph). A span's props (e.g. {"color": ...})
    restyle on top of the base color/font, same as split_chars().
    """
    scene = next(s for s in bpy.data.scenes if obj.name in s.objects)
    body, base_name, base_size, base_font = obj.data.body, obj.name, obj.data.size, obj.data.font
    color = _captured_color(obj)
    origin = obj.location.copy()
    left_x = measure(obj)["min"][0]
    bpy.data.objects.remove(obj, do_unlink=True)

    parts: list[Any] = []
    cursor_x = left_x

    def emit(text: str, name: str, props: dict[str, Any]) -> None:
        nonlocal cursor_x
        part_obj = create(scene, text, name=name, size=base_size, font=base_font)
        part_obj.location = origin.copy()
        part_obj.location.x = cursor_x
        if color is not None:
            style(part_obj, color=color[0], shading=color[1])
        if props:
            style(part_obj, **props)
        bpy.context.view_layer.update()
        cursor_x += part_obj.dimensions.x + spacing
        parts.append(part_obj)

    def emit_gap(text: str, name: str) -> None:
        nonlocal cursor_x
        if not text:
            return
        if text.strip():
            emit(text, name, {})
        else:
            cursor_x += sum(base_size * space_width_factor for ch in text if ch.isspace())

    prev_end = 0
    for i, span in enumerate(spans):
        start, end = span[0], span[1]
        props = span[2] if len(span) > 2 else {}
        emit_gap(body[prev_end:start], f"{base_name}.gap{i}")
        emit(body[start:end], f"{base_name}.{i}", props)
        prev_end = end
    emit_gap(body[prev_end:], f"{base_name}.gap{len(spans)}")
    return parts


def style_spans(chars: list[Any], spans: list[tuple[int, int, dict[str, Any]]]) -> list[Any]:
    """Apply style() per index range over split_chars()'s output — the hook for
    multi-color/multi-font inline spans, since color/font live on individual objects
    (one material per object), not on a substring within one FONT object.
    """
    for start, end, props in spans:
        for obj in chars[start:end]:
            style(obj, **props)
    return chars


def word_spans(body: str) -> list[tuple[int, int]]:
    """(start, end) char-index pairs per whitespace-delimited word, aligned 1:1 with
    split_chars()'s output list. Skips whitespace runs.
    """
    spans = []
    start = None
    for i, ch in enumerate(body):
        if ch.isspace():
            if start is not None:
                spans.append((start, i))
                start = None
        elif start is None:
            start = i
    if start is not None:
        spans.append((start, len(body)))
    return spans


def measure_many(objs: list[Any]) -> dict[str, Any]:
    """measure()'s bbox, unioned across objs — for sizing a highlight/background that
    spans a whole word or span, not one glyph.
    """
    boxes = [measure(obj) for obj in objs]
    mins = tuple(min(b["min"][a] for b in boxes) for a in range(3))
    maxs = tuple(max(b["max"][a] for b in boxes) for a in range(3))
    return {
        "width": maxs[0] - mins[0],
        "height": maxs[1] - mins[1],
        "depth": maxs[2] - mins[2],
        "min": mins,
        "max": maxs,
    }


def highlight_bg(
    scn: Any,
    objs: list[Any],
    color: tuple[float, ...],
    *,
    padding: float = 0.05,
    name: str | None = None,
) -> Any:
    """One quad sized/positioned from measure_many(objs) — a highlight behind text
    (small padding, partial alpha) or a background box (larger padding, full alpha),
    same primitive either way. Reuses card's quad/material builders rather than
    duplicating them.
    """
    name = name or f"{objs[0].name}.highlight"
    box = measure_many(objs)
    w, h = box["width"] + 2 * padding, box["height"] + 2 * padding
    cx = (box["min"][0] + box["max"][0]) / 2
    cy = (box["min"][1] + box["max"][1]) / 2
    quad = card._plane(scn, name, w, h)
    quad.location = (cx, cy, box["min"][2] - 0.001)
    card._flat_material(quad, color)
    provenance.tag(quad, name)
    return quad


def color_target(obj: Any) -> Any:
    """The ID-block tween()/stagger() must keyframe color_path() on — a node input's
    F-curve lives on the node_tree's own animation_data, not the Object's or the
    Material's (keyframe_insert() cannot cross an ID-block boundary). Precondition:
    obj already has a material from a prior style(color=...) call.
    """
    return obj.data.materials[0].node_tree


def color_path(obj: Any, shading: Literal["flat", "lit"] = "flat") -> str:
    """RNA path, relative to color_target(obj), for tween()/stagger() to animate a
    style()'d object's color — mirrors the exact node/input names style() writes to,
    so callers don't hand-type it.

    Resolves the input's *numeric* collection index rather than keeping the
    `inputs["Emission Color"]` string form: Blender's own keyframe_insert() silently
    normalizes a node-input string lookup to its positional index in the stored
    F-curve's data_path (verified — NodeInputs, unlike NodeTree.nodes, has no
    name-based RNA path resolution), so a string-keyed path would never match the
    fcurve tween()'s own bookkeeping goes looking for afterward.
    """
    bsdf = obj.data.materials[0].node_tree.nodes["Principled BSDF"]
    field = "Emission Color" if shading == "flat" else "Base Color"
    idx = list(bsdf.inputs.keys()).index(field)
    return f'nodes["Principled BSDF"].inputs[{idx}].default_value'


def alpha_path(obj: Any) -> str:
    """RNA path, relative to color_target(obj), for tween()/stagger() to fade a
    style()'d object in/out via the Principled BSDF's Alpha input.

    color_path()'s alpha component (index 3 of Emission/Base Color) is a red herring
    for transparency: Blender's Principled BSDF ignores a Color socket's alpha
    entirely. Only this dedicated scalar Alpha input, combined with the
    material.blend_method='BLEND' style()/card already sets, actually fades an
    object -- tweening color_path()'s alpha compiles and runs with no error but the
    object stays fully opaque throughout.

    Same numeric-index resolution as color_path() -- see its docstring for why the
    string form ("Alpha") would never match the fcurve tween() looks up afterward.
    """
    bsdf = obj.data.materials[0].node_tree.nodes["Principled BSDF"]
    idx = list(bsdf.inputs.keys()).index("Alpha")
    return f'nodes["Principled BSDF"].inputs[{idx}].default_value'


def karaoke(
    scn: Any,
    obj: Any,
    color: tuple[float, ...],
    *,
    start: float,
    word_gap: float,
    dur: float,
    ease: str | None = None,
) -> list[Any]:
    """Word-by-word highlight sweep: split obj into words, one highlight_bg() quad per
    word, stagger the quads' alpha in word order. Bundles the pattern into one call so
    word-granularity stagger is the easy path, not the one an agent has to hand-roll under
    time pressure. Uses split_spans() (word-level), not split_chars() -- only the quads
    are ever animated here, never individual letters.
    """
    body, base_name = obj.data.body, obj.name
    words = split_spans(obj, word_spans(body))
    quads = [
        highlight_bg(scn, [word_obj], color, name=f"{base_name}.word{i}")
        for i, word_obj in enumerate(words)
    ]
    anim.stagger(
        [color_target(q) for q in quads],
        color_path(quads[0]),
        3,
        word_gap,
        start=start,
        frm=0.0,
        to=color[3] if len(color) > 3 else 1.0,
        dur=dur,
        ease=ease,
    )
    return quads
