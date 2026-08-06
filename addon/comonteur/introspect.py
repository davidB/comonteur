"""Progressive disclosure — SPEC.md §6.3. Never dump a whole tree; always cap
and truncate. drift()/find() are deferred past M1 (not on the walking-skeleton
checklist); add when reconcile (M4) needs them.
"""

from collections.abc import Iterator
from typing import Any

from . import const


def outline(scene: Any, max_lines: int = 60) -> str:
    lines = [f"Scene: {scene.name!r} [{scene.get(const.PROP_ORIGIN, 'untagged')}]"]
    for coll in scene.collection.children:
        lines.append(f"  Collection: {coll.name!r} ({len(coll.objects)} objects)")
        if len(lines) >= max_lines:
            break
    shown = 0
    for obj in scene.collection.objects:
        if len(lines) >= max_lines:
            # Count objects against objects: `lines` also holds the scene header and one entry
            # per collection, so subtracting len(lines) here under-reported what was hidden.
            lines.append(f"  … +{len(scene.collection.objects) - shown} more")
            break
        lines.append(
            f"  Object: {obj.name!r} [{obj.type}] origin={obj.get(const.PROP_ORIGIN, '-')}"
        )
        shown += 1
    return "\n".join(lines)


def describe(id_block: Any, path: str = "", max_lines: int = 40) -> str:
    cur = id_block
    for part in filter(None, path.split(".")):
        cur = getattr(cur, part)
    attrs = [a for a in dir(cur) if not a.startswith("_")]
    body = "\n".join(f"  {a}" for a in attrs[:max_lines])
    return f"{type(cur).__name__} at {path or '<root>'}:\n{body}"


def _action_fcurves(action: Any) -> Iterator[Any]:
    """Every F-curve in `action`, across the 5.2 layered-Action structure.

    5.2's layered-animation rework removed `Action.fcurves` in favour of
    layers/strips/channelbags (docs/M3-FINDINGS.md Check 3). `anim.py` avoids walking that
    structure by using `fcurve_ensure_for_datablock()`, but that accessor is per
    (datablock, path, index) and cannot enumerate — reading back *what is animated* has to
    walk. Keep this the only place that does.
    """
    for layer in getattr(action, "layers", ()):
        for strip in layer.strips:
            for channelbag in getattr(strip, "channelbags", ()):
                yield from channelbag.fcurves


def animated_paths(scene: Any, max_lines: int = 60) -> list[dict[str, Any]]:
    """One dict per F-curve, capped like its siblings. When the cap bites, a final
    `{"truncated": N}` entry says how many were dropped — a silently short list would read
    as "that is the whole scene", which is the opposite of what this module is for.
    """
    out: list[dict[str, Any]] = []
    total = 0
    for obj in scene.objects:
        action = obj.animation_data.action if obj.animation_data else None
        if not action:
            continue
        for fc in _action_fcurves(action):
            total += 1
            if len(out) >= max_lines:
                continue
            out.append(
                {
                    "object": obj.name,
                    "data_path": fc.data_path,
                    "index": fc.array_index,
                    "keys": len(fc.keyframe_points),
                    "frame_range": (fc.range()[0], fc.range()[1]) if fc.keyframe_points else None,
                }
            )
    if total > len(out):
        out.append({"truncated": total - len(out)})
    return out


def gn_inputs(obj: Any, max_lines: int = 60) -> list[dict[str, Any]]:
    """Named inputs (identifier + current value) of every Geometry Nodes modifier on obj —
    what gn.input_path() needs to resolve a socket name, without groping for a Socket_N
    identifier by trial and error (see gn.py's module docstring for why that lookup exists
    at all). Skips Geometry-typed sockets (not a scalar value to display) and any socket
    kind whose properties struct exposes no `.value` (Object/Image/Material inputs — none
    of comonteur's own effects use them yet).
    """
    out: list[dict[str, Any]] = []
    total = 0
    for mod in obj.modifiers:
        if mod.type != "NODES" or mod.node_group is None:
            continue
        for item in mod.node_group.interface.items_tree:
            if item.item_type != "SOCKET" or item.in_out != "INPUT":
                continue
            if item.socket_type == "NodeSocketGeometry":
                continue
            sock = getattr(mod.properties.inputs, item.identifier)
            if not hasattr(sock, "value"):
                continue
            total += 1
            if len(out) >= max_lines:
                continue
            out.append(
                {
                    "modifier": mod.name,
                    "name": item.name,
                    "identifier": item.identifier,
                    "value": sock.value,
                }
            )
    if total > len(out):
        out.append({"truncated": total - len(out)})
    return out
