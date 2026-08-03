"""Visual review — SPEC.md §6.4. Renders via bpy.ops.render.render(scene=..., write_still=False)
— the "Render Image" path, not "Render Animation" — so the result lands in the in-memory
Render Result image datablock instead of on disk. That means the call needs no VIEW_3D area,
no camera-locked viewport, and no window.scene switch: it works on any scene (a timeline
scene, a human-owned scene, an agent-built shot) regardless of what workspace/viewport the
human currently has open, and touches none of that scene's own render settings except the
frame it's currently parked on.
"""

import os
from typing import Any, Iterable

import bpy

from . import const


def frames(scene: Any, frame_numbers: Iterable[int], engine: str | None = None) -> list[str]:
    root = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    out_dir = os.path.join(root, const.JOURNAL_DIR, "review")
    os.makedirs(out_dir, exist_ok=True)

    prev_frame = scene.frame_current
    prev_engine = scene.render.engine
    if engine is not None:
        scene.render.engine = engine
    prev_media_type = scene.render.image_settings.media_type
    prev_file_format = scene.render.image_settings.file_format
    try:
        out_paths = []
        for f in frame_numbers:
            scene.frame_set(f)
            seconds = f / scene.render.fps
            path = os.path.join(out_dir, f"frame-{f:03d}-at-{seconds:.2f}.png")
            bpy.ops.render.render(write_still=False, scene=scene.name)
            # Save the Render Result explicitly rather than write_still=True: that path writes
            # via scene.render.filepath/image_settings, which a kind="2d" scene pins to
            # VIDEO/FFMPEG (scene.py) and which we don't want to touch or depend on at all.
            scene.render.image_settings.media_type = "IMAGE"
            scene.render.image_settings.file_format = "PNG"
            bpy.data.images["Render Result"].save_render(path, scene=scene)
            out_paths.append(path)
        return out_paths
    finally:
        scene.render.engine = prev_engine
        scene.render.image_settings.media_type = prev_media_type
        scene.render.image_settings.file_format = prev_file_format
        scene.frame_set(prev_frame)
