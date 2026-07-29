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


# --- Brand params (§9): numeric params propagate via drivers; strings are not
# drivable, so a handler syncs scene[param] into the bound text object's data.body.


def set_param(scn, name, value, *, min=None, max=None, subtype=None):
    scn[name] = value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ui = scn.id_properties_ui(name)
        if min is not None or max is not None:
            ui.update(min=min if min is not None else -1e6, max=max if max is not None else 1e6)
        if subtype is not None:
            ui.update(subtype=subtype)


def bind_param(obj, name):
    """Strings aren't drivable (§9/§11): tag obj so the sync handler mirrors
    scn[name] into obj.data.body whenever the scene custom property changes.
    """
    obj[const.PROP_PARAM] = name


@bpy.app.handlers.persistent
def _sync_string_params(scn, depsgraph):
    for obj in scn.objects:
        name = obj.get(const.PROP_PARAM)
        if not name or obj.type != "FONT":
            continue
        value = scn.get(name)
        if value is not None and obj.data.body != value:
            obj.data.body = value


def register():
    if _sync_string_params not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_sync_string_params)


def unregister():
    if _sync_string_params in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sync_string_params)
