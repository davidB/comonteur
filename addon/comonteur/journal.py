"""The mutation journal — SPEC.md §4.4/§4.5. Every agent write goes through
journal.set() inside a journal.batch(); that is the only sanctioned write path.
"""

import contextlib
import datetime
import json
import os
import uuid

import bpy

from . import const, paths

_state = {"active": False, "batch_id": None, "writes": [], "touched": []}


def batch_active():
    return _state["active"]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _journal_path():
    root = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    d = os.path.join(root, const.JOURNAL_DIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, const.JOURNAL_FILENAME)


def _append(entry):
    with open(_journal_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")


def _read_all():
    path = _journal_path()
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def target_of(id_block):
    return f"{type(id_block).__name__}:{id_block.get(const.PROP_ID, id_block.name)}"


@contextlib.contextmanager
def batch(label):
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
            id_block[const.PROP_REV] = id_block.get(const.PROP_REV, 0) + 1
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


def set(id_block, path, value):
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
            "old": old,
            "new": new,
        }
    )
    if id_block not in _state["touched"]:
        _state["touched"].append(id_block)


def record_flip(id_block):
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


def paths_written_by_agent(id_block):
    target = target_of(id_block)
    return {
        e["path"]
        for e in _read_all()
        if e.get("target") == target and e.get("actor") == "agent" and e.get("op") == "set"
    }


def last_agent_value(id_block, path):
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
