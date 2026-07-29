"""VSE assembly — SPEC.md §5.2/§10 M4. Turns a resolved timeline plan (the JSON
`comonteur reconcile plan` writes from timeline.yaml, docs/M4-FINDINGS.md) into VSE
strips. `diff()` is pure logic (no bpy import, unit-testable like paths.py) so the
create/update/delete decision can be tested without Blender; `apply()` is the thin bpy
layer that actually mutates the sequence editor, entirely through journal.set() like any
other agent write (§5.2: "reconcile is not exempt from provenance").
"""

import os
from typing import Any

try:
    from . import const
except ImportError:  # imported standalone (tests/unit/test_reconcile.py, no bpy/package)
    import const  # type: ignore[no-redef]

CHANNEL_SHOTS = 1
CHANNEL_AUDIO = 2
CHANNEL_TRANSITIONS = 3

_TRANSITION_TYPES = {"cross": "CROSS"}


class ReconcilePlan:
    def __init__(
        self,
        to_create: list[dict[str, Any]],
        to_update: list[dict[str, Any]],
        to_delete: list[str],
    ) -> None:
        self.to_create = to_create
        self.to_update = to_update
        self.to_delete = to_delete


def diff(
    desired: list[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    claimed: dict[str, set[str]],
    fields: tuple[str, ...],
) -> ReconcilePlan:
    """desired: items with an "id" plus values for each name in `fields` (may carry
    extra creation-only keys, e.g. "source" — diff() ignores anything not in `fields`).
    existing: cmt_id -> {"origin": str, "fields": {...}} for currently tagged strips.
    claimed: cmt_id -> field names the human has since edited (provenance.claimed_paths).

    Rules (SPEC.md §4.2/§5.2): missing from existing -> create. Present in both -> update
    only fields that changed and aren't claimed. Present in existing but not desired ->
    delete only if agent-owned AND untouched (never shared/human, never a claimed field).
    VSE strips are not ID datablocks (docs/M4-FINDINGS.md) — depsgraph updates surface
    against the parent Scene, so §4.3's automatic origin flip never fires for a strip
    edit and `origin` alone can't be trusted for delete-safety here; `claimed` (derived
    straight from the journal, not from the flip) is what actually catches it.
    """
    to_create: list[dict[str, Any]] = []
    to_update: list[dict[str, Any]] = []
    desired_ids: set[str] = set()

    for item in desired:
        item_id = item["id"]
        desired_ids.add(item_id)
        if item_id not in existing:
            to_create.append(item)
            continue
        current = existing[item_id].get("fields", {})
        item_claimed = claimed.get(item_id, set())
        changes = {
            f: item[f] for f in fields if f not in item_claimed and current.get(f) != item.get(f)
        }
        if changes:
            to_update.append({"id": item_id, "fields": changes})

    to_delete = [
        cmt_id
        for cmt_id, info in existing.items()
        if cmt_id not in desired_ids
        and info.get("origin") == const.ORIGIN_AGENT
        and not claimed.get(cmt_id)
    ]
    return ReconcilePlan(to_create, to_update, to_delete)


def _existing_index(se: Any, types: tuple[str, ...]) -> dict[str, Any]:
    return {
        s.get(const.PROP_ID): s
        for s in se.strips
        if s.get(const.PROP_ID) is not None and s.type in types
    }


def _strip_fields(strip: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: int(getattr(strip, f)) for f in fields}


def apply(scene: Any, resolved: dict[str, Any], project_root: str) -> None:
    """Reconcile scene.sequence_editor against a resolved timeline plan. One
    journal.batch (one undo_push) for the whole reconcile — imports the bpy-dependent
    submodules locally so this module stays importable (for diff()) without bpy.
    """
    from . import journal, library, provenance

    se = scene.sequence_editor
    if se is None:
        se = scene.sequence_editor_create()

    def plan_for(
        desired: list[dict[str, Any]], types: tuple[str, ...], fields: tuple[str, ...]
    ) -> tuple[ReconcilePlan, dict[str, Any]]:
        existing = _existing_index(se, types)
        existing_info = {
            cid: {"origin": provenance.origin(s), "fields": _strip_fields(s, fields)}
            for cid, s in existing.items()
        }
        claimed = {cid: provenance.claimed_paths(s) for cid, s in existing.items()}
        return diff(desired, existing_info, claimed, fields), existing

    def write_fields(strip: Any, fields: dict[str, Any]) -> None:
        for path, value in fields.items():
            journal.set(strip, path, value)

    def create_shot_strip(item: dict[str, Any]) -> Any:
        source = item["source"]
        kind = source["kind"]
        if kind == "scene":
            blend = os.path.join(project_root, source["blend"])
            linked = library.link_scene(blend, source["scene"])
            strip = se.strips.new_scene(
                name=item["id"], scene=linked, channel=CHANNEL_SHOTS, frame_start=1
            )
        elif kind == "movie":
            path = os.path.join(project_root, source["path"])
            strip = se.strips.new_movie(
                name=item["id"], filepath=path, channel=CHANNEL_SHOTS, frame_start=1
            )
        else:
            raise ValueError(f"unknown shot source kind: {kind!r}")
        provenance.tag(strip, item["id"])
        return strip

    def reconcile_shots(shots: list[dict[str, Any]]) -> dict[str, Any]:
        fields = ("frame_start", "frame_final_duration")
        desired = [
            {
                "id": s["id"],
                "source": s["source"],
                "frame_start": s["start_frame"],
                "frame_final_duration": s["duration_frames"],
            }
            for s in shots
        ]
        shot_plan, existing = plan_for(desired, ("SCENE", "MOVIE"), fields)

        for item in shot_plan.to_create:
            strip = create_shot_strip(item)
            write_fields(strip, {f: item[f] for f in fields})
            existing[item["id"]] = strip
        for update in shot_plan.to_update:
            write_fields(existing[update["id"]], update["fields"])
        for cmt_id in shot_plan.to_delete:
            se.strips.remove(existing.pop(cmt_id))
        return existing

    def reconcile_audio(audio: list[dict[str, Any]]) -> None:
        fields = ("frame_start",)
        desired = [
            {"id": a["id"], "path": a["path"], "frame_start": a["start_frame"]} for a in audio
        ]
        audio_plan, existing = plan_for(desired, ("SOUND",), fields)

        for item in audio_plan.to_create:
            path = os.path.join(project_root, item["path"])
            strip = se.strips.new_sound(
                name=item["id"], filepath=path, channel=CHANNEL_AUDIO, frame_start=1
            )
            provenance.tag(strip, item["id"])
            write_fields(strip, {f: item[f] for f in fields})
        for update in audio_plan.to_update:
            write_fields(existing[update["id"]], update["fields"])
        for cmt_id in audio_plan.to_delete:
            se.strips.remove(existing[cmt_id])

    def reconcile_transitions(shots: list[dict[str, Any]], shot_strips: dict[str, Any]) -> None:
        existing = _existing_index(se, ("CROSS",))
        prev: dict[str, Any] | None = None
        for shot in shots:
            transition = shot.get("transition")
            cur_strip = shot_strips.get(shot["id"])
            if transition and prev is not None and cur_strip is not None:
                tid = f"{shot['id']}:transition"
                prev_strip = shot_strips.get(prev["id"])
                if tid not in existing and prev_strip is not None:
                    effect = se.strips.new_effect(
                        name=tid,
                        type=_TRANSITION_TYPES.get(transition["type"], "CROSS"),
                        channel=CHANNEL_TRANSITIONS,
                        frame_start=int(cur_strip.frame_start),
                        length=int(transition["duration_frames"]),
                        input1=prev_strip,
                        input2=cur_strip,
                    )
                    provenance.tag(effect, tid)
            prev = shot

    with journal.batch("reconcile timeline"):
        shots = resolved.get("shots", [])
        shot_strips = reconcile_shots(shots)
        reconcile_audio(resolved.get("audio", []))
        reconcile_transitions(shots, shot_strips)
