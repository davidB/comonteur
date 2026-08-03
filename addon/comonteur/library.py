"""Component library — SPEC.md §6/§9. Blender's asset system is the component
registry; do not build a custom one. Headless discovery mechanism confirmed in
docs/M3-FINDINGS.md (Check 2): bpy.data.libraries.load(assets_only=True), no GUI or
Asset Browser needed.
"""

import os
from typing import Any

import bpy

from . import project, provenance

_CATALOG_FILE = "blender_assets.cats.txt"


def _catalog_names(blend_path: str) -> dict[str, str]:
    # ponytail: line format is "uuid:catalog/path:display_name" per Blender's asset
    # catalog sidecar; falls back to the raw uuid if the file is missing or a line
    # doesn't parse, so a bad sidecar degrades discover() rather than crashing it.
    cats_path = os.path.join(os.path.dirname(blend_path), _CATALOG_FILE)
    names: dict[str, str] = {}
    if not os.path.exists(cats_path):
        return names
    with open(cats_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", "VERSION")):
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                names[parts[0]] = parts[-1]
    return names


def discover(
    blend_path: str,
    kinds: tuple[str, ...] = ("actions", "scenes", "node_groups"),
    root: str | None = None,
) -> list[dict[str, Any]]:
    """List assets in blend_path — description, tags, catalog. Linking (not
    appending) is required to read .asset_data headless; the linked datablocks stay
    in bpy.data as zero-user until link() actually uses one.

    blend_path is project-root-relative (e.g. "lib/design.blend") — resolved to a
    portable //-relative path via project.to_link_path() rather than passed straight
    to bpy, which would resolve a bare relative string against the process's cwd.
    """
    catalogs = _catalog_names(project.to_abs_path(blend_path, root))
    resolved = project.to_link_path(blend_path, root)
    with bpy.data.libraries.load(resolved, link=True, assets_only=True) as (data_from, data_to):
        for kind in kinds:
            setattr(data_to, kind, list(getattr(data_from, kind, [])))

    found: list[dict[str, Any]] = []
    for kind in kinds:
        for db in getattr(data_to, kind):
            meta = db.asset_data
            found.append(
                {
                    "kind": kind,
                    "name": db.name,
                    "description": meta.description if meta else "",
                    "tags": [t.name for t in meta.tags] if meta else [],
                    "catalog": catalogs.get(str(meta.catalog_id), str(meta.catalog_id))
                    if meta
                    else None,
                }
            )
    return found


def link(blend_path: str, kind: str, name: str, root: str | None = None) -> Any:
    """Link one component (Scene/Action/node group) from blend_path, tagging
    provenance if it isn't already tagged (M0.6: custom props survive linking).

    blend_path is project-root-relative — see discover()'s docstring on why it goes
    through project.to_link_path() rather than straight to bpy.
    """
    resolved = project.to_link_path(blend_path, root)
    with bpy.data.libraries.load(resolved, link=True, assets_only=True) as (data_from, data_to):
        if name not in getattr(data_from, kind):
            raise ValueError(f"{name!r} not found in {kind} of {blend_path}")
        setattr(data_to, kind, [name])

    obj = getattr(data_to, kind)[0]
    # bpy.data.libraries.load() resolves `resolved` to find the file but stores an
    # absolute Library.filepath regardless of what was passed — set it back to the
    # //-relative form so the link survives the project folder moving.
    obj.library.filepath = resolved
    if provenance.origin(obj) is None:
        provenance.tag(obj, f"{os.path.basename(blend_path)}:{name}")
    return obj


def link_scene(blend_path: str, scene_name: str, root: str | None = None) -> Any:
    """Link a plain generated Scene (shots/*.blend, SPEC.md §5.1b) for
    use as a VSE Scene strip (M0.7). Unlike link(), not assets_only — these scenes are
    agent-generated, not asset-marked (docs/M4-FINDINGS.md).
    """
    resolved = project.to_link_path(blend_path, root)
    with bpy.data.libraries.load(resolved, link=True) as (data_from, data_to):
        if scene_name not in data_from.scenes:
            raise ValueError(f"{scene_name!r} not found in scenes of {blend_path}")
        data_to.scenes = [scene_name]

    scn = data_to.scenes[0]
    scn.library.filepath = resolved
    if provenance.origin(scn) is None:
        provenance.tag(scn, f"{os.path.basename(blend_path)}:{scene_name}")
    return scn
