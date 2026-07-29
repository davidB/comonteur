"""Component library — SPEC.md §6/§9. Blender's asset system is the component
registry; do not build a custom one. Headless discovery mechanism confirmed in
docs/M3-FINDINGS.md (Check 2): bpy.data.libraries.load(assets_only=True), no GUI or
Asset Browser needed.
"""

import os

import bpy

from . import provenance

_CATALOG_FILE = "blender_assets.cats.txt"


def _catalog_names(blend_path):
    # ponytail: line format is "uuid:catalog/path:display_name" per Blender's asset
    # catalog sidecar; falls back to the raw uuid if the file is missing or a line
    # doesn't parse, so a bad sidecar degrades discover() rather than crashing it.
    cats_path = os.path.join(os.path.dirname(blend_path), _CATALOG_FILE)
    names = {}
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


def discover(blend_path, kinds=("actions", "scenes", "node_groups")):
    """List assets in blend_path — description, tags, catalog. Linking (not
    appending) is required to read .asset_data headless; the linked datablocks stay
    in bpy.data as zero-user until link() actually uses one.
    """
    catalogs = _catalog_names(blend_path)
    with bpy.data.libraries.load(blend_path, link=True, assets_only=True) as (data_from, data_to):
        for kind in kinds:
            setattr(data_to, kind, list(getattr(data_from, kind, [])))

    found = []
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


def link(blend_path, kind, name):
    """Link one component (Scene/Action/node group) from blend_path, tagging
    provenance if it isn't already tagged (M0.6: custom props survive linking).
    """
    with bpy.data.libraries.load(blend_path, link=True, assets_only=True) as (data_from, data_to):
        if name not in getattr(data_from, kind):
            raise ValueError(f"{name!r} not found in {kind} of {blend_path}")
        setattr(data_to, kind, [name])

    obj = getattr(data_to, kind)[0]
    if provenance.origin(obj) is None:
        provenance.tag(obj, f"{os.path.basename(blend_path)}:{name}")
    return obj
