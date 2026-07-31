"""Visual review — SPEC.md §6.4. Renders via raw bpy.ops.render.opengl (M0.10),
not the MCP add-on's own viewport-render tool, which sandboxes output into its
own temp dir instead of the requested path.
"""

import os
from typing import Any, Iterable

import bpy

from . import const


def frames(scene: Any, frame_numbers: Iterable[int], engine: str = "WORKBENCH") -> list[str]:
    root = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    out_dir = os.path.join(root, const.JOURNAL_DIR, "review")
    os.makedirs(out_dir, exist_ok=True)

    # Restore everything this function touches, including on the error path: comonteur:render
    # uses the file's own output settings, so a leaked filepath silently redirects the human's
    # next render into .comonteur/review/.
    prev_scene, prev_engine = bpy.context.window.scene, scene.render.engine
    prev_filepath, prev_frame = scene.render.filepath, scene.frame_current
    scene.render.engine = "BLENDER_WORKBENCH" if engine == "WORKBENCH" else engine
    bpy.context.window.scene = scene
    try:
        out_paths = []
        for f in frame_numbers:
            scene.frame_set(f)
            seconds = f / scene.render.fps
            path = os.path.join(out_dir, f"frame-{f:03d}-at-{seconds:.2f}.png")
            scene.render.filepath = path
            bpy.ops.render.opengl(write_still=True)
            out_paths.append(path)
        return out_paths
    finally:
        scene.render.engine = prev_engine
        scene.render.filepath = prev_filepath
        scene.frame_set(prev_frame)
        bpy.context.window.scene = prev_scene
