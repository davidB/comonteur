"""Ownership tagging and the automatic provenance flip — SPEC.md §4.1/§4.3."""

from typing import Any

import bpy

from . import const, journal, paths


def tag(id_block: Any, cmt_id: str, origin: str = const.ORIGIN_AGENT, rev: int = 1) -> None:
    id_block[const.PROP_ID] = cmt_id
    id_block[const.PROP_ORIGIN] = origin
    id_block[const.PROP_REV] = rev


def origin(id_block: Any) -> str | None:
    return id_block.get(const.PROP_ORIGIN)


def is_agent_owned(id_block: Any) -> bool:
    return origin(id_block) == const.ORIGIN_AGENT


def claimed_paths(id_block: Any) -> set[str]:
    """Fine-grained claim, derived not observed (§4.3): a path the agent wrote whose
    live value no longer matches what the agent last wrote there.
    """
    claimed = set()
    for path in journal.paths_written_by_agent(id_block):
        if paths.resolve(id_block, path) != journal.last_agent_value(id_block, path):
            claimed.add(path)
    return claimed


@bpy.app.handlers.persistent
def _on_depsgraph_update(scene: Any, depsgraph: Any) -> None:
    if journal.batch_active():
        return  # agent's own writes — not a human edit
    for upd in depsgraph.updates:
        id_ = getattr(upd.id, "original", upd.id)
        if id_.get(const.PROP_ORIGIN) == const.ORIGIN_AGENT:
            id_[const.PROP_ORIGIN] = const.ORIGIN_SHARED
            journal.record_flip(id_)


def register() -> None:
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister() -> None:
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
