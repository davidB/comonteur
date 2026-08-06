"""Ownership tagging and the automatic provenance flip — SPEC.md §4.1/§4.3."""

from typing import Any

import bpy

from . import const, introspect, journal, paths


def tag(id_block: Any, cmt_id: str, origin: str = const.ORIGIN_AGENT, rev: int = 1) -> None:
    id_block[const.PROP_ID] = cmt_id
    id_block[const.PROP_ORIGIN] = origin
    id_block[const.PROP_REV] = rev
    # Every constructor (scene.new_scene, text.create, library.link*) tags what it makes, so
    # journalling here is what makes a creation-only batch visible at all: without it such a
    # batch has no writes, and journal.batch() gates the JSONL append, the cmt_rev bump and the
    # undo_push on having some. Tagging outside a batch (a human taking ownership from the
    # sidebar) is not an agent write and is not recorded here.
    if journal.batch_active():
        journal.record_create(id_block)


def origin(id_block: Any) -> str | None:
    return id_block.get(const.PROP_ORIGIN)


def is_agent_owned(id_block: Any) -> bool:
    return origin(id_block) == const.ORIGIN_AGENT


def _animated_paths(id_block: Any) -> set[str]:
    """The `a.b[i]`-style paths driven by an F-curve on `id_block`'s own action."""
    action = getattr(getattr(id_block, "animation_data", None), "action", None)
    if action is None:
        return set()
    # Both spellings: tween() journals `location[1]`, the scalar form journals a bare path.
    return {
        spelling
        for fc in introspect._action_fcurves(action)
        for spelling in (fc.data_path, f"{fc.data_path}[{fc.array_index}]")
    }


def _driven_paths(id_block: Any) -> set[str]:
    """The `a.b[i]`-style paths governed by a driver on `id_block`'s own animation_data.

    Drivers live directly on `AnimData.drivers` (a flat FCurve collection, unlike the
    layered Action structure `_animated_paths()` has to walk), so no equivalent of
    `introspect._action_fcurves()` is needed here.
    """
    anim_data = getattr(id_block, "animation_data", None)
    if anim_data is None:
        return set()
    return {
        spelling
        for fc in anim_data.drivers
        for spelling in (fc.data_path, f"{fc.data_path}[{fc.array_index}]")
    }


def claimed_paths(id_block: Any) -> set[str]:
    """Fine-grained claim, derived not observed (§4.3): a path the agent wrote whose
    live value no longer matches what the agent last wrote there.

    Animated and driven paths are excluded. Their live value is whatever the F-curve/driver
    evaluates to at the current playhead, so it matches the journalled value in at most one
    frame — comparing them reported the agent's own tween/drive() as a human claim everywhere
    else. That is the dangerous direction to be wrong in: the agent must not touch a claimed
    path, so a false positive makes it abandon its own animation and tell the human they took
    it over.

    ponytail: keyframe-level and driver-expression-level claims (a human dragging the agent's
    keys, or editing the agent's driver formula) are therefore not detected here — that's
    what the whole-ID flip in _on_depsgraph_update() is for instead. Detecting them at this
    finer grain means diffing keyframe values or driver expression text against what was
    journalled, which needs the journal to record more than it does today.
    """
    animated = _animated_paths(id_block)
    driven = _driven_paths(id_block)
    claimed = set()
    for path in journal.paths_written_by_agent(id_block):
        if path in animated or path in driven:
            continue
        if journal.jsonable(paths.resolve(id_block, path)) != journal.last_agent_value(
            id_block, path
        ):
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
