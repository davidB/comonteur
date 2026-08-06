"""reconcile.apply()'s `[[background]]` handling: sequential non-overlapping segments on
CHANNEL_BACKGROUND, below every shot channel (see addon/comonteur/reconcile.py,
skills/comonteur/references/timeline.md). Media paths don't need to exist — same as shots
(reconcile_channels_and_transitions.py's docstring).
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
            "duration_frames": 150,
            "in_frame": None,
            "transition": None,
        },
    ],
    "audio": [],
    "background": [
        {
            "id": "bg-intro",
            "source": {"kind": "color", "value": [0.1, 0.1, 0.1]},
            "start_frame": 0,
            "duration_frames": 60,
        },
        {
            "id": "bg-body",
            "source": {"kind": "image", "path": "assets/bg_body.png"},
            "start_frame": 60,
            "duration_frames": 90,
        },
    ],
}

cmt.reconcile.apply(scn, resolved, "/project")
se = scn.sequence_editor
strips = {s.name: s for s in se.strips}

bg_intro = strips["bg:bg-intro"]
assert bg_intro.type == "COLOR"
assert bg_intro.channel == cmt.reconcile.CHANNEL_BACKGROUND == 5
assert bg_intro.frame_start == 0
assert int(bg_intro.frame_final_duration) == 60
assert all(abs(c - 0.1) < 1e-6 for c in bg_intro.color)  # float32 strip storage, not exact

bg_body = strips["bg:bg-body"]
assert bg_body.type == "IMAGE"
assert bg_body.channel == cmt.reconcile.CHANNEL_BACKGROUND == 5
assert bg_body.frame_start == 60
assert int(bg_body.frame_final_duration) == 90

# Background sits strictly below the shot channel — never on top of it.
shot1 = strips["shot-01"]
assert shot1.channel == cmt.reconcile.CHANNEL_SHOTS_A == 6
assert bg_intro.channel < shot1.channel
assert bg_body.channel < shot1.channel

# Shot creation must not delete the background strips, and vice versa — this is the
# regression the "bg:" id prefix + id_filter exist to prevent (both passes create
# SCENE/MOVIE-capable strip types and would otherwise see each other's strips as
# unrecognized strays).
strip_count = len(se.strips)
cmt.reconcile.apply(scn, resolved, "/project")
assert len(se.strips) == strip_count

# Dropping bg-intro from the list deletes only its strip (agent-owned, unclaimed).
resolved_one_bg = {**resolved, "background": resolved["background"][1:]}
cmt.reconcile.apply(scn, resolved_one_bg, "/project")
remaining = {s.name for s in se.strips}
assert "bg:bg-intro" not in remaining
assert "bg:bg-body" in remaining
assert "shot-01" in remaining

# A human-claimed field (edited outside journal.set, so its live value no longer matches
# what the agent last journalled) is left alone on the next reconcile.
bg_body = {s.name: s for s in se.strips}["bg:bg-body"]
bg_body.frame_final_duration = 45
resolved_bg_body_moved = {
    **resolved_one_bg,
    "background": [{**resolved["background"][1], "duration_frames": 200}],
}
cmt.reconcile.apply(scn, resolved_bg_body_moved, "/project")
bg_body = {s.name: s for s in se.strips}["bg:bg-body"]
assert int(bg_body.frame_final_duration) == 45  # claimed — reconcile did not overwrite it
