"""VSE assembly — SPEC.md §5.2/§10 M4. Turns a resolved timeline plan (the JSON the
`comonteur:reconcile` task writes from timeline.toml, docs/M4-FINDINGS.md) into VSE
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

# Bottom-up, matching pro NLE convention: audio at the bottom, video in the middle,
# overlay/titles reserved at the top. Video and audio ranges are never interleaved.
CHANNEL_AUDIO = 1  # SOUND — voiceover/dialogue, and any with_audio movie shot's own audio
# 2-4 reserved: human audio (music/SFX/ambience) — timeline.toml has no schema for these
# roles yet, so a human adds them by hand; kept next to dialogue at the bottom of the stack.
CHANNEL_SHOTS_A = 5
CHANNEL_SHOTS_B = 6  # shots alternate A/B by position so any two temporally adjacent shots
# sit on different channels — required for a CROSS effect between them to have a real
# overlapping frame range to blend across (same channel can't display two strips at once).
CHANNEL_TRANSITIONS = 7  # CROSS effect, above both shot channels
# 8-9 reserved: human video overlay (PiP, B-roll insert), and where `overlay_of` shots get
# dynamically allocated a channel (see _allocate_overlay_channel) — never a fixed constant,
# since a project may already have human content sitting there.
# 10+ reserved: titles/subtitles/karaoke overlay, topmost — nothing agent-side writes here
# yet (comonteur's text objects live in-scene, not as VSE text strips).
_SHOT_CHANNELS = (CHANNEL_SHOTS_A, CHANNEL_SHOTS_B)
_RESERVED_CHANNELS = {CHANNEL_AUDIO, CHANNEL_SHOTS_A, CHANNEL_SHOTS_B, CHANNEL_TRANSITIONS}


def _allocate_overlay_channel(
    occupied: list[tuple[int, int, int]],
    target_channel: int,
    frame_start: int,
    frame_end: int,
) -> int:
    """Lowest channel above both `target_channel` and the reserved shot/audio/transition
    range that has no strip overlapping [frame_start, frame_end) — `timeline.toml` only
    expresses intent (`overlay_of`), this is the addon's strategy for turning that into an
    actual channel, so it never collides with human content already sitting in 8+.
    """
    channel = max(target_channel + 1, CHANNEL_TRANSITIONS + 1)
    while channel in _RESERVED_CHANNELS or any(
        c == channel and frame_start < e and s < frame_end for c, s, e in occupied
    ):
        channel += 1
    return channel


_TRANSITION_TYPES = {"cross": "CROSS"}

_CONTAINER_FOR_CODEC = {
    "H264": "MPEG4",
    "H265": "MPEG4",
    "AV1": "WEBM",
    "WEBM": "WEBM",
    "PRORES": "QUICKTIME",
    "QTRLE": "QUICKTIME",
    "DNXHD": "QUICKTIME",
    "DV": "DV",
    "FLASH": "FLASH",
    "MPEG1": "MPEG1",
    "MPEG2": "MPEG2",
    "THEORA": "OGG",
    "HUFFYUV": "AVI",
}
_DEFAULT_CONTAINER = "MKV"  # Matroska accepts virtually every ffmpeg codec


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


def scene_range(resolved: dict[str, Any]) -> dict[str, Any]:
    """fps/resolution/encode/frame_end to apply to the container scene, derived from the
    resolved plan. Pure so the "984 frames short" class of bug (scene left on scaffold
    defaults because nothing ever read `resolved["fps"]`/shot end frames) has a fast test
    that doesn't need Blender. `frame_end` is absent from the result when there are no
    shots — nothing to derive it from. `video` is a (codec, container) pair — container is
    either the resolved plan's explicit override or looked up per-codec.
    """
    out: dict[str, Any] = {}
    fps = resolved.get("fps")
    if fps:
        out["fps"] = int(fps)
    resolution = resolved.get("resolution")
    if resolution:
        out["resolution"] = (int(resolution[0]), int(resolution[1]))
    video_codec = resolved.get("video_codec")
    if video_codec:
        codec = str(video_codec).upper()
        container = resolved.get("video_container")
        out["video"] = (
            codec,
            str(container).upper()
            if container
            else _CONTAINER_FOR_CODEC.get(codec, _DEFAULT_CONTAINER),
        )
    audio_codec = resolved.get("audio_codec")
    if audio_codec:
        out["audio_codec"] = str(audio_codec).upper()
    shots = resolved.get("shots") or []
    ends = [s["start_frame"] + s["duration_frames"] for s in shots]
    if ends:
        out["frame_end"] = max(ends)
    return out


def _existing_index(se: Any, types: tuple[str, ...]) -> dict[str, Any]:
    return {
        s.get(const.PROP_ID): s
        for s in se.strips
        if s.get(const.PROP_ID) is not None and s.type in types
    }


def _strip_fields(strip: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: int(getattr(strip, f)) for f in fields}


def apply_render_settings(
    scene: Any, resolved: dict[str, Any], *, has_audio: bool | None = None
) -> None:
    """The render/output settings a container scene needs, derived from `resolved`.

    Split out of `apply()` so a partial reconcile (no shots/audio yet, e.g. right
    after `comonteur:init`) can set just these without faking the rest of the
    resolved-plan schema. `has_audio` is None in that partial-reconcile case (no VSE
    to inspect yet) — omitted, this leaves `resolved["audio_codec"]` as the sole source
    of truth, same as before `has_audio` existed. `apply()` passes the real answer
    (any SOUND strip in the reconciled VSE) once shots/audio are in place, which is
    what lets a timeline with no audio strips end up video-only instead of carrying
    a default AAC track nothing feeds.
    """
    from . import journal

    sr = scene_range(resolved)
    for key, value in sr.items():
        if key == "resolution":
            journal.set(scene, "render.resolution_x", value[0])
            journal.set(scene, "render.resolution_y", value[1])
        elif key == "fps":
            journal.set(scene, "render.fps", value)
        elif key == "video":
            codec, container = value
            # media_type must be set before file_format — Blender ignores FFMPEG's
            # codec/format properties on an image_settings block still in its default
            # (IMAGE) media_type.
            journal.set(scene, "render.image_settings.media_type", "VIDEO")
            journal.set(scene, "render.image_settings.file_format", "FFMPEG")
            journal.set(scene, "render.ffmpeg.codec", codec)
            journal.set(scene, "render.ffmpeg.format", container)
            journal.set(scene, "render.ffmpeg.constant_rate_factor", "MEDIUM")
            journal.set(scene, "render.ffmpeg.ffmpeg_preset", "GOOD")
        elif key == "audio_codec":
            journal.set(scene, "render.ffmpeg.audio_codec", value)
        else:
            journal.set(scene, key, value)
    if has_audio is False:
        journal.set(scene, "render.ffmpeg.audio_codec", "NONE")
    elif has_audio is True and "audio_codec" not in sr:
        journal.set(scene, "render.ffmpeg.audio_codec", "AAC")
    # Output folder is a fixed project convention, not derived from the resolved
    # timeline plan, so it's not a scene_range() key — but journal.set() (not a raw
    # scn.render.filepath = ...) is still the right way to write it: same as
    # fps/resolution above, reconcile stays authoritative and re-syncs it on every
    # call rather than drifting, and the write is journalled for audit either way.
    journal.set(scene, "render.filepath", "//renders/")


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
        desired: list[dict[str, Any]],
        types: tuple[str, ...],
        fields: tuple[str, ...],
        id_filter: Any = None,
    ) -> tuple[ReconcilePlan, dict[str, Any]]:
        existing = _existing_index(se, types)
        if id_filter is not None:
            # Two passes can share a strip `type` (SOUND: plain [[audio]] tracks vs. a
            # movie shot's with_audio companion) — without this, each pass's diff() sees
            # the other pass's strips as "not in my desired list" and deletes them as
            # strays, right after they were created earlier in the same batch. That's a
            # dangling reference to a live-in-batch strip and segfaults Blender, not just
            # a logic bug — found by running the with_audio blender test, not by reading.
            existing = {cid: s for cid, s in existing.items() if id_filter(cid)}
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
                name=item["id"], scene=linked, channel=item["channel"], frame_start=1
            )
        elif kind == "movie":
            path = os.path.join(project_root, source["path"])
            strip = se.strips.new_movie(
                name=item["id"], filepath=path, channel=item["channel"], frame_start=1
            )
        else:
            raise ValueError(f"unknown shot source kind: {kind!r}")
        provenance.tag(strip, item["id"])
        return strip

    def reconcile_shots(shots: list[dict[str, Any]]) -> dict[str, Any]:
        # channel alternates by position, not a fixed constant: a shot with a transition
        # must overlap the previous one in time, which requires them on different
        # channels (Blender neither validates nor blends two strips sharing a channel).
        # channel therefore has to be a synced field too — a shot inserted/removed shifts
        # every later shot's parity, so an update must be able to move an existing strip.
        # `overlay_of` shots are excluded from the alternation (they don't shift it) and
        # get their channel from _allocate_overlay_channel instead, once their target's
        # channel is known.
        fields = ("frame_start", "frame_final_duration", "channel")
        shot_ids = {s["id"] for s in shots}
        desired_by_id: dict[str, dict[str, Any]] = {}
        i = 0
        for s in shots:
            if s.get("overlay_of") is not None:
                continue
            desired_by_id[s["id"]] = {
                "id": s["id"],
                "source": s["source"],
                "frame_start": s["start_frame"],
                "frame_final_duration": s["duration_frames"],
                "channel": _SHOT_CHANNELS[i % 2],
            }
            i += 1

        # Ranges already occupied by anything not part of this shots list — other VSE
        # content (human overlays, leftovers) — so an overlay never lands on top of it.
        occupied = [
            (
                int(strip.channel),
                int(strip.frame_start),
                int(strip.frame_start) + int(strip.frame_final_duration),
            )
            for strip in se.strips
            if strip.get(const.PROP_ID) not in shot_ids
        ]

        pending = [s for s in shots if s.get("overlay_of") is not None]
        while pending:
            progressed = []
            for s in pending:
                target = desired_by_id.get(s["overlay_of"])
                if target is None:
                    continue
                frame_start = s["start_frame"]
                frame_end = frame_start + s["duration_frames"]
                channel = _allocate_overlay_channel(
                    occupied, target["channel"], frame_start, frame_end
                )
                desired_by_id[s["id"]] = {
                    "id": s["id"],
                    "source": s["source"],
                    "frame_start": frame_start,
                    "frame_final_duration": s["duration_frames"],
                    "channel": channel,
                }
                occupied.append((channel, frame_start, frame_end))
                progressed.append(s)
            if not progressed:
                raise ValueError("overlay_of: target not found in resolved shots (cycle?)")
            for s in progressed:
                pending.remove(s)

        desired = [desired_by_id[s["id"]] for s in shots]
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
        # id_filter excludes `<shot-id>:audio` companions — reconcile_shot_audio owns those.
        audio_plan, existing = plan_for(
            desired, ("SOUND",), fields, id_filter=lambda cid: not cid.endswith(":audio")
        )

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

    def reconcile_shot_audio(shots: list[dict[str, Any]]) -> None:
        """Companion SOUND strip for a movie shot with `source.with_audio` — e.g. a
        lip-synced dialogue take, where cutting the video (removing an "um", trimming
        silence) must move its own audio along with it. "Linked" here just means comonteur
        re-syncs both strips' frame range on every reconcile; Blender only creates a real
        video/audio link when both come from one `movie_strip_add` operator call, which
        `new_movie()`/`new_sound()` called separately don't give us. `:audio`-suffixed id,
        same convention as `reconcile_transitions`'s `:transition`, so it never collides
        with a `[[audio]]`-declared track's id.
        """
        fields = ("frame_start", "frame_final_duration")
        desired = [
            {
                "id": f"{s['id']}:audio",
                "path": s["source"]["path"],
                "frame_start": s["start_frame"],
                "frame_final_duration": s["duration_frames"],
            }
            for s in shots
            if s["source"].get("kind") == "movie" and s["source"].get("with_audio")
        ]
        # id_filter: only ids this pass itself could have created — the mirror image of
        # reconcile_audio's filter, for the same cross-pass-deletion reason.
        audio_plan, existing = plan_for(
            desired, ("SOUND",), fields, id_filter=lambda cid: cid.endswith(":audio")
        )

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
        # comonteur assembles the timeline in the VSE, not the 3D viewport — render
        # must read from the sequencer or `comonteur:render` produces the wrong frame.
        journal.set(scene, "render.use_sequencer", True)
        shots = resolved.get("shots", [])
        shot_strips = reconcile_shots(shots)
        reconcile_audio(resolved.get("audio", []))
        reconcile_shot_audio(shots)
        reconcile_transitions(shots, shot_strips)
        has_audio = any(s.type == "SOUND" for s in se.strips)
        apply_render_settings(scene, resolved, has_audio=has_audio)
