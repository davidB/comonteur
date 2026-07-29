"""scene.new_scene() — deterministic baseline, SPEC.md §6.1."""

import bpy

from . import const, provenance


def new_scene(
    name,
    *,
    kind="2d",
    fps=30,
    resolution=(1920, 1080),
    frame_range=(1, 90),
    transparent=True,
    view_transform=None,
):
    existing = find(name)
    if existing is not None:
        return existing

    bpy.ops.scene.new(type="EMPTY")  # M0.2: EMPTY/NEW both give 0 inherited objects
    scn = bpy.context.window.scene
    scn.name = name

    scn.render.resolution_x, scn.render.resolution_y = resolution
    scn.render.resolution_percentage = 100
    scn.render.fps = fps
    scn.render.fps_base = 1.0
    scn.frame_start, scn.frame_end = frame_range
    scn.render.film_transparent = transparent
    scn.view_settings.view_transform = view_transform or ("Standard" if kind == "2d" else "AgX")

    provenance.tag(scn, name)
    return scn


def find(cmt_id):
    for scn in bpy.data.scenes:
        if scn.get(const.PROP_ID) == cmt_id:
            return scn
    return None
