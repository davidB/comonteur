"""Project-root discovery + portable (//-relative) asset path resolution.

A project folder must survive being copied to a different directory or machine without
breaking links: `bpy.data.libraries.load()` and VSE strip creation need Blender's own
`//`-relative form (resolved against the *linking* .blend's own location, every time it
is opened — not baked in once), not a bare relative string, which Blender/os resolve
against the process's cwd instead. A caller only knows a project-root-relative logical
name ("lib/design.blend"); the //-relative form depends on where the *current* .blend
sits (timeline.blend at the root, compositions/frames/*.blend one level down), so
resolution goes: logical name -> absolute (anchored on the project root) -> //-relative
(anchored on the current .blend's own directory).

`_walk_up`/`_to_link_path` are pure (no bpy import) so the path math is testable without
Blender, matching reconcile.py's diff()/apply() split.
"""

import os

try:
    from . import const
except ImportError:  # imported standalone (tests/unit/test_project.py, no bpy/package)
    import const  # type: ignore[no-redef]


def _walk_up(start: str, marker: str) -> str:
    cur = os.path.abspath(start)
    origin = cur
    while True:
        if os.path.isdir(os.path.join(cur, marker)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return origin
        cur = parent


def _to_link_path(target: str, current_blend_path: str) -> str:
    if not current_blend_path:
        return target
    rel = os.path.relpath(target, os.path.dirname(current_blend_path))
    return "//" + rel.replace(os.sep, "/")


def find_root(start: str | None = None) -> str:
    import bpy

    if start is None:
        start = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    return _walk_up(start, const.JOURNAL_DIR)


def to_abs_path(project_rel_path: str, root: str | None = None) -> str:
    """Real filesystem path — for os.path calls (e.g. a sidecar file lookup), not bpy."""
    return os.path.join(root or find_root(), project_rel_path)


def to_link_path(project_rel_path: str, root: str | None = None) -> str:
    """The form bpy.data.libraries.load()/VSE strips need: //-relative to the current
    .blend, so the link stays portable if the whole project folder moves.
    """
    import bpy

    target = to_abs_path(project_rel_path, root)
    return _to_link_path(target, bpy.data.filepath)
