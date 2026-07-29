"""Visual review — SPEC.md §6.4. Renders via raw bpy.ops.render.opengl (M0.10),
not the MCP add-on's own viewport-render tool, which sandboxes output into its
own temp dir instead of the requested path.
"""

import os

import bpy

from . import const


def frames(scene, frame_numbers, engine="WORKBENCH"):
    root = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    out_dir = os.path.join(root, const.JOURNAL_DIR, "review")
    os.makedirs(out_dir, exist_ok=True)

    prev_scene, prev_engine = bpy.context.window.scene, scene.render.engine
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
        bpy.context.window.scene = prev_scene
