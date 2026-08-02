"""RNA-path get/set on a dotted "a.b[1].c" or "a.b["Name"].c" string. No bpy import —
unit-testable outside Blender against plain Python objects (SPEC.md §8, "pure-logic
modules"). Quoted-string indices resolve a node/collection by name (e.g.
`nodes["Principled BSDF"]`), same as bpy's own bpy_prop_collection indexing.
"""

import re
from typing import Any

_PART_RE = re.compile(r"""^([a-zA-Z_][a-zA-Z0-9_]*)(\[(\d+|"[^"]*"|'[^']*')\])?$""")


def _parse_idx(raw: str) -> int | str:
    return int(raw) if raw[0] not in "\"'" else raw[1:-1]


def _step(obj: Any, part: str) -> Any:
    m = _PART_RE.match(part)
    if not m:
        raise ValueError(f"bad path segment: {part!r}")
    name, idx = m.group(1), m.group(3)
    obj = getattr(obj, name)
    return obj[_parse_idx(idx)] if idx is not None else obj


def resolve(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        cur = _step(cur, part)
    return cur


def set_(obj: Any, path: str, value: Any) -> None:
    *head, last = path.split(".")
    cur = obj
    for part in head:
        cur = _step(cur, part)
    m = _PART_RE.match(last)
    if not m:
        raise ValueError(f"bad path segment: {last!r}")
    name, idx = m.group(1), m.group(3)
    if idx is not None:
        getattr(cur, name)[_parse_idx(idx)] = value
    else:
        setattr(cur, name, value)
