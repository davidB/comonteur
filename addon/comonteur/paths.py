"""RNA-path get/set on a dotted "a.b[1].c" string. No bpy import — unit-testable
outside Blender against plain Python objects (SPEC.md §8, "pure-logic modules").
"""

import re

_PART_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)(\[(\d+)\])?$")


def _step(obj, part):
    m = _PART_RE.match(part)
    if not m:
        raise ValueError(f"bad path segment: {part!r}")
    name, idx = m.group(1), m.group(3)
    obj = getattr(obj, name)
    return obj[int(idx)] if idx is not None else obj


def resolve(obj, path):
    cur = obj
    for part in path.split("."):
        cur = _step(cur, part)
    return cur


def set_(obj, path, value):
    *head, last = path.split(".")
    cur = obj
    for part in head:
        cur = _step(cur, part)
    m = _PART_RE.match(last)
    if not m:
        raise ValueError(f"bad path segment: {last!r}")
    name, idx = m.group(1), m.group(3)
    if idx is not None:
        getattr(cur, name)[int(idx)] = value
    else:
        setattr(cur, name, value)
