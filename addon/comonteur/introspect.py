"""Progressive disclosure — SPEC.md §6.3. Never dump a whole tree; always cap
and truncate. drift()/find() are deferred past M1 (not on the walking-skeleton
checklist); add when reconcile (M4) needs them.
"""

from typing import Any

from . import const


def outline(scene: Any, max_lines: int = 60) -> str:
    lines = [f"Scene: {scene.name!r} [{scene.get(const.PROP_ORIGIN, 'untagged')}]"]
    for coll in scene.collection.children:
        lines.append(f"  Collection: {coll.name!r} ({len(coll.objects)} objects)")
        if len(lines) >= max_lines:
            break
    for obj in scene.collection.objects:
        if len(lines) >= max_lines:
            lines.append(f"  … +{len(scene.collection.objects) - len(lines)} more")
            break
        lines.append(
            f"  Object: {obj.name!r} [{obj.type}] origin={obj.get(const.PROP_ORIGIN, '-')}"
        )
    return "\n".join(lines)


def describe(id_block: Any, path: str = "", max_lines: int = 40) -> str:
    cur = id_block
    for part in filter(None, path.split(".")):
        cur = getattr(cur, part)
    attrs = [a for a in dir(cur) if not a.startswith("_")]
    body = "\n".join(f"  {a}" for a in attrs[:max_lines])
    return f"{type(cur).__name__} at {path or '<root>'}:\n{body}"


def animated_paths(scene: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for obj in scene.objects:
        action = obj.animation_data.action if obj.animation_data else None
        if not action:
            continue
        for fc in action.fcurves:
            out.append(
                {
                    "object": obj.name,
                    "data_path": fc.data_path,
                    "index": fc.array_index,
                    "keys": len(fc.keyframe_points),
                    "frame_range": (fc.range()[0], fc.range()[1]) if fc.keyframe_points else None,
                }
            )
    return out
