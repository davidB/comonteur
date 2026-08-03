"""scene.new_scene() — deterministic baseline, SPEC.md §6.1."""

from typing import Any

import bpy

from . import const, provenance


def new_scene(
    name: str,
    *,
    kind: str = "2d",
    fps: int = 30,
    resolution: tuple[int, int] = (1920, 1080),
    frame_range: tuple[int, int] = (1, 90),
    transparent: bool = True,
    view_transform: str | None = None,
) -> Any:
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
    if kind == "2d":
        # bpy.ops.scene.new(type='EMPTY') copies settings from the active scene, not
        # factory defaults — pin these explicitly so a flat/unlit scene is deterministic
        # regardless of what the previously active scene had enabled.
        scn.eevee.use_fast_gi = False
        scn.eevee.use_raytracing = False
        scn.eevee.indirect_light_intensity = 0.0
        # No lights/shadows in a flat scene, so cheap sampling is free perf, not a
        # quality tradeoff — and the scene has no sound data, so mute the output track.
        scn.eevee.taa_samples = 2
        scn.eevee.taa_render_samples = 4
        scn.eevee.use_shadows = False
        scn.render.image_settings.media_type = "VIDEO"
        scn.render.image_settings.file_format = "FFMPEG"
        scn.render.ffmpeg.audio_codec = "NONE"

    provenance.tag(scn, name)
    return scn


def find(cmt_id: str) -> Any:
    for scn in bpy.data.scenes:
        if scn.get(const.PROP_ID) == cmt_id:
            return scn
    return None


# --- Brand params (§9): numeric params propagate via drivers; strings are not
# drivable, so a handler syncs scene[param] into the bound text object's data.body.


def set_param(
    scn: Any,
    name: str,
    value: Any,
    *,
    min: float | None = None,
    max: float | None = None,
    subtype: str | None = None,
) -> None:
    scn[name] = value
    # Colours and vectors carry UI metadata too — gating on scalars alone silently dropped
    # subtype="COLOR", which is the one that decides whether the human gets a swatch or four
    # raw floats. Booleans are ints in Python but are not sliders, so they stay out.
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    vector = isinstance(value, (tuple, list)) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
    )
    if numeric or vector:
        ui = scn.id_properties_ui(name)
        if min is not None or max is not None:
            ui.update(min=min if min is not None else -1e6, max=max if max is not None else 1e6)
        if subtype is not None:
            ui.update(subtype=subtype)


def bind_param(obj: Any, name: str) -> None:
    """Strings aren't drivable (§9/§11): tag obj so the sync handler mirrors
    scn[name] into obj.data.body whenever the scene custom property changes.
    """
    obj[const.PROP_PARAM] = name


@bpy.app.handlers.persistent
def _sync_string_params(scn: Any, depsgraph: Any) -> None:
    for obj in scn.objects:
        name = obj.get(const.PROP_PARAM)
        if not name or obj.type != "FONT":
            continue
        value = scn.get(name)
        if value is not None and obj.data.body != value:
            obj.data.body = value


def register() -> None:
    if _sync_string_params not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_sync_string_params)


def unregister() -> None:
    if _sync_string_params in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sync_string_params)
