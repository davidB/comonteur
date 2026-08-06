"""The mutation journal — SPEC.md §4.4/§4.5. Every agent write goes through
journal.set() inside a journal.batch(); that is the only sanctioned write path.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import uuid
from collections.abc import Iterator
from typing import Any

import bpy

from . import const, paths, project

_state: dict[str, Any] = {"active": False, "batch_id": None, "writes": [], "touched": []}


def batch_active() -> bool:
    return _state["active"]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _journal_path() -> str:
    d = os.path.join(project.find_root(), const.JOURNAL_DIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, const.JOURNAL_FILENAME)


def _append(entry: dict[str, Any]) -> None:
    with open(_journal_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")


def _read_all() -> Iterator[dict[str, Any]]:
    path = _journal_path()
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def jsonable(value: Any) -> Any:
    """bpy hands back Vector / Color / bpy_prop_array for anything vector-shaped, and none of
    them are JSON-serializable. Coerce here rather than at the call site: `set()` is documented
    as the escape hatch for arbitrary properties, so array-valued writes are expected, and a
    TypeError would otherwise surface at batch exit with the batch already half-flushed.

    Not module-private: `provenance.claimed_paths()` also calls this, on the *live* value it
    reads back from the strip/object, so it compares against `last_agent_value()`'s journalled
    form on equal footing — `mathutils.Color`/`Vector`/`bpy_prop_array` compare unequal to a
    plain list even when every element matches (`Color(...) != [0.1, 0.1, 0.1]` is `True` in
    Blender), which made any vector-valued `journal.set()` write look human-claimed the instant
    it was created, with nothing having touched it.
    """
    if isinstance(value, (str, bytes)) or value is None:
        return value
    if isinstance(value, (int, float, bool)):
        return value
    try:
        return [jsonable(v) for v in value]
    except TypeError:
        return repr(value)


def target_of(id_block: Any) -> str:
    return f"{type(id_block).__name__}:{id_block.get(const.PROP_ID, id_block.name)}"


@contextlib.contextmanager
def batch(label: str) -> Iterator[str]:
    """One labelled undo_push per batch (SPEC.md §4.5). Nesting is not supported —
    batches are the agent's unit of work, not a general transaction primitive.
    """
    if _state["active"]:
        raise RuntimeError("journal.batch() does not nest")
    _state.update(active=True, batch_id="b_" + uuid.uuid4().hex[:8], writes=[], touched=[])
    try:
        yield _state["batch_id"]
    finally:
        writes, touched = _state["writes"], _state["touched"]
        for entry in writes:
            _append(entry)
        for id_block in touched:
            # split_chars() replaces its input object within the same batch — a datablock
            # touched earlier in the batch can be gone by the time it exits.
            try:
                id_block[const.PROP_REV] = id_block.get(const.PROP_REV, 0) + 1
            except ReferenceError:
                continue
        if writes:
            # depsgraph_update_post is deferred, not synchronous with property
            # writes — force evaluation now, while batch_active() still gates the
            # flip handler, so the batch's own writes never get misread as a human
            # edit on the next unrelated evaluation (found live testing M1).
            bpy.context.view_layer.update()
        _state.update(active=False, batch_id=None, writes=[], touched=[])
        # ponytail: bpy.ops.ed.undo_push needs a window (M0.8) — absent in headless
        # runs (tests, CI). Guard rather than crash; GUI sessions are the real path.
        if writes and bpy.context.window is not None:
            bpy.ops.ed.undo_push(message=f"comonteur: {label}")
        # Autosave: nothing to overwrite until the file has been saved once
        # (bpy.ops.wm.save_mainfile requires an existing filepath — a brand-new
        # timeline.blend goes through save_as_mainfile in ensure_timeline() instead).
        # Bump save_version first so Blender's own .blend1/.blend2 rotation is the backup.
        if writes and bpy.data.filepath:
            prefs = bpy.context.preferences.filepaths
            if prefs.save_version < 2:
                prefs.save_version = 2
            bpy.ops.wm.save_mainfile()


def set(id_block: Any, path: str, value: Any) -> None:
    if not _state["active"]:
        raise RuntimeError("journal.set() must run inside journal.batch()")
    old = paths.resolve(id_block, path)
    paths.set_(id_block, path, value)
    new = paths.resolve(id_block, path)
    _state["writes"].append(
        {
            "ts": _now(),
            "batch": _state["batch_id"],
            "actor": "agent",
            "op": "set",
            "target": target_of(id_block),
            "path": path,
            "old": jsonable(old),
            "new": jsonable(new),
        }
    )
    if id_block not in _state["touched"]:
        _state["touched"].append(id_block)


def record_create(id_block: Any) -> None:
    """Record that the agent brought `id_block` into existence, inside the current batch.

    Called from provenance.tag(), so every constructor gets this for free. It goes through
    `_state["writes"]` rather than straight to the file because that list is what batch() uses
    to decide there is anything to journal, bump and undo_push at all.
    """
    if not _state["active"]:
        raise RuntimeError("journal.record_create() must run inside journal.batch()")
    _state["writes"].append(
        {
            "ts": _now(),
            "batch": _state["batch_id"],
            "actor": "agent",
            "op": "create",
            "target": target_of(id_block),
        }
    )
    if id_block not in _state["touched"]:
        _state["touched"].append(id_block)


def created_by_agent(id_block: Any) -> bool:
    """True when the journal shows the agent created `id_block` — the check revert needs to
    know whether undoing means deleting the datablock or restoring its previous values.
    """
    target = target_of(id_block)
    return any(
        e.get("target") == target and e.get("actor") == "agent" and e.get("op") == "create"
        for e in _read_all()
    )


def record_driver(
    id_block: Any, path: str, expression: str, variables: dict[str, tuple[Any, str]] | None
) -> None:
    """Record that the agent attached/changed a driver on `path` — the formula-install
    counterpart to set()'s single-value write. Goes through `_state["writes"]` for the
    same reason record_create() does: that list is what batch() checks before journalling,
    bumping cmt_rev and undo_pushing at all.
    """
    if not _state["active"]:
        raise RuntimeError("journal.record_driver() must run inside journal.batch()")
    _state["writes"].append(
        {
            "ts": _now(),
            "batch": _state["batch_id"],
            "actor": "agent",
            "op": "driver",
            "target": target_of(id_block),
            "path": path,
            "expression": expression,
            "variables": (
                [
                    {"name": name, "target": target_of(tgt), "target_path": tgt_path}
                    for name, (tgt, tgt_path) in variables.items()
                ]
                if variables
                else []
            ),
        }
    )
    if id_block not in _state["touched"]:
        _state["touched"].append(id_block)


def record_flip(id_block: Any) -> None:
    _append(
        {
            "ts": _now(),
            "batch": None,
            "actor": "human",
            "op": "flip",
            "target": target_of(id_block),
            "from": const.ORIGIN_AGENT,
            "to": const.ORIGIN_SHARED,
        }
    )


def paths_written_by_agent(id_block: Any) -> set[str]:
    target = target_of(id_block)
    return {
        e["path"]
        for e in _read_all()
        if e.get("target") == target and e.get("actor") == "agent" and e.get("op") == "set"
    }


def last_agent_value(id_block: Any, path: str) -> Any:
    target = target_of(id_block)
    val = None
    for e in _read_all():
        if (
            e.get("target") == target
            and e.get("path") == path
            and e.get("actor") == "agent"
            and e.get("op") == "set"
        ):
            val = e["new"]
    return val
