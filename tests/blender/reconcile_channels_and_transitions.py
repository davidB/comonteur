"""reconcile.apply() end-to-end: channel layout, transition overlap, and with_audio companion
strip (see addon/comonteur/reconcile.py, skills/comonteur/references/timeline.md). Media
paths don't need to exist — new_movie()/new_sound() accept a missing file and just default
frame_final_duration to 1 until reconciled to an explicit value, which this resolved plan
always does, so no media fixtures are needed.
"""

import _bl
import bpy

cmt = _bl.setup()

scn = bpy.context.scene
resolved = {
    "fps": 30,
    "resolution": [1920, 1080],
    "shots": [
        {
            "id": "shot-01",
            "source": {"kind": "movie", "path": "raw/a.mp4"},
            "start_frame": 0,
            "duration_frames": 90,
            "in_frame": None,
            "transition": None,
        },
        {
            "id": "shot-02",
            # 90 -> 75 / 120 -> 135: pre-shifted by the resolver's 15-frame (0.5s@30fps)
            # transition overlap, same as skills/.../reconcile.py::resolve() would produce.
            "source": {"kind": "movie", "path": "raw/b.mp4", "with_audio": True},
            "start_frame": 75,
            "duration_frames": 135,
            "in_frame": None,
            "transition": {"type": "cross", "duration_frames": 15},
        },
    ],
    "audio": [{"id": "vo", "path": "audio/narration.wav", "start_frame": 10}],
}

cmt.reconcile.apply(scn, resolved, "/project")
se = scn.sequence_editor
strips = {s.name: s for s in se.strips}

# apply() must point the render at the VSE, not the 3D viewport, or comonteur:render
# produces the wrong output.
assert scn.render.use_sequencer is True

shot1 = strips["shot-01"]
assert shot1.type == "MOVIE"
assert shot1.channel == cmt.reconcile.CHANNEL_SHOTS_A == 6
assert shot1.frame_start == 0
assert int(shot1.frame_final_duration) == 90

shot2 = strips["shot-02"]
assert shot2.type == "MOVIE"
assert shot2.channel == cmt.reconcile.CHANNEL_SHOTS_B == 7
assert shot2.frame_start == 75
assert int(shot2.frame_final_duration) == 135

# The two shots must actually overlap for the CROSS effect to have a real blend range.
assert shot1.frame_start < shot2.frame_start < shot1.frame_start + shot1.frame_final_duration

transition = strips["shot-02:transition"]
assert transition.type == "CROSS"
assert transition.channel == cmt.reconcile.CHANNEL_TRANSITIONS == 8
assert transition.frame_start == 75
assert int(transition.frame_final_duration) == 15

companion_audio = strips["shot-02:audio"]
assert companion_audio.type == "SOUND"
assert companion_audio.channel == cmt.reconcile.CHANNEL_AUDIO == 1
assert companion_audio.frame_start == 75
assert int(companion_audio.frame_final_duration) == 135

vo = strips["vo"]
assert vo.type == "SOUND"
assert vo.channel == cmt.reconcile.CHANNEL_AUDIO == 1
assert vo.frame_start == 10

# resolved carries no explicit encode.audio_codec — apply() finds SOUND strips in the
# reconciled VSE and defaults the container scene's output to AAC.
assert scn.render.ffmpeg.audio_codec == "AAC"

# Re-running reconcile against the same plan is a no-op: nothing new created or deleted.
strip_count = len(se.strips)
cmt.reconcile.apply(scn, resolved, "/project")
assert len(se.strips) == strip_count

# Dropping shot-02 deletes its strips (agent-owned, unclaimed).
resolved_one_shot = {**resolved, "shots": resolved["shots"][:1], "audio": []}
cmt.reconcile.apply(scn, resolved_one_shot, "/project")
remaining = {s.name for s in se.strips}
assert remaining == {"shot-01"}

# No SOUND strips left (shot-01 has no with_audio companion, audio list is empty) —
# apply() must mute the output track instead of leaving a stale/default AAC codec.
assert scn.render.ffmpeg.audio_codec == "NONE"

# --- overlay_of: intent in the resolved plan, channel allocated dynamically by apply() ---
# Only shot-01 (channel 6) remains in the scene. Two overlays both target it and are
# resolved in the same apply() call, so they must land on different channels even though
# neither exists yet when allocation starts.
resolved_with_overlays = {
    **resolved_one_shot,
    "shots": [
        resolved["shots"][0],
        {
            "id": "overlay-01",
            "source": {"kind": "movie", "path": "raw/caption.mp4"},
            "start_frame": 0,
            "duration_frames": 90,
            "in_frame": None,
            "transition": None,
            "overlay_of": "shot-01",
        },
        {
            "id": "overlay-02",
            "source": {"kind": "movie", "path": "raw/watermark.mp4"},
            "start_frame": 0,
            "duration_frames": 90,
            "in_frame": None,
            "transition": None,
            "overlay_of": "shot-01",
        },
    ],
}
cmt.reconcile.apply(scn, resolved_with_overlays, "/project")
strips = {s.name: s for s in se.strips}
overlay1 = strips["overlay-01"]
overlay2 = strips["overlay-02"]
assert overlay1.channel == 9  # max(shot-01's channel 6 + 1, CHANNEL_TRANSITIONS + 1)
assert overlay2.channel == 10  # 9 already claimed by overlay-01 within the same apply()

# Idempotent: re-applying the same plan doesn't move either overlay.
cmt.reconcile.apply(scn, resolved_with_overlays, "/project")
strips = {s.name: s for s in se.strips}
assert strips["overlay-01"].channel == 9
assert strips["overlay-02"].channel == 10

# A human strip sitting on channel 11, overlapping the overlays' time range, must not be
# clobbered — a third overlay targeting shot-01 has to skip past it to channel 12.
se.strips.new_effect(name="human-pip", type="COLOR", channel=11, frame_start=0, length=90)
resolved_with_third_overlay = {
    **resolved_with_overlays,
    "shots": [
        *resolved_with_overlays["shots"],
        {
            "id": "overlay-03",
            "source": {"kind": "movie", "path": "raw/logo.mp4"},
            "start_frame": 0,
            "duration_frames": 90,
            "in_frame": None,
            "transition": None,
            "overlay_of": "shot-01",
        },
    ],
}
cmt.reconcile.apply(scn, resolved_with_third_overlay, "/project")
strips = {s.name: s for s in se.strips}
assert strips["overlay-01"].channel == 9
assert strips["overlay-02"].channel == 10
assert strips["overlay-03"].channel == 12
assert strips["human-pip"].channel == 11  # untouched — not agent-owned
