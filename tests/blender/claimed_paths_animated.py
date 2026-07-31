"""claimed_paths() must not report the agent's own animation as a human claim.

claimed_paths() decides a path is the human's when its live value no longer matches what the
agent last journalled. For an *animated* path that comparison is meaningless: the live value is
whatever the F-curve evaluates to at the current playhead, so it matches only in the single
frame where the tween happens to land on its journalled value. Everywhere else the agent's own
tween reported itself as claimed by the human.

That is the worst possible direction for this bug to fail in. Per SKILL.md the agent must not
touch a claimed path — so after animating anything, the agent would refuse to adjust its own
work and report to the human that they had taken it over.

A human editing keyframes is a real thing to detect, but it has to be detected on the keyframes
themselves; the live value cannot carry that signal. Until then a false negative is correct and
a false positive is not.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture: animated + static"):
    scn = cmt.scene.new_scene("shot-claims", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "Ship faster", size=0.8)
    cmt.anim.tween(title, "location", 1, frm=-0.4, to=0.0, start=1, dur=18)
    cmt.journal.set(title, "location[0]", 0.25)  # static, not animated

# Anywhere along the tween, location[1] is mid-flight and differs from the journalled end
# value. That is the animation working, not a human edit.
for frame in (1, 5, 12, 19, 40):
    scn.frame_set(frame)
    claimed = cmt.provenance.claimed_paths(title)
    assert "location[1]" not in claimed, (
        f"at frame {frame} the agent's own tween reports as human-claimed: {claimed}"
    )

# The static path the agent wrote is likewise still the agent's.
scn.frame_set(5)
assert cmt.provenance.claimed_paths(title) == set(), cmt.provenance.claimed_paths(title)

# ...and a real human edit to a static path is still caught.
title.location[0] = 9.0
assert "location[0]" in cmt.provenance.claimed_paths(title), (
    "a human edit to a non-animated path must still be detected"
)
