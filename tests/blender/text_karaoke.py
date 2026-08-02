"""text.karaoke() sweeps highlight per word, not per character — the bundled version
of the eval-observed hand-rolled pattern (split_chars() + group-by-word + shared
per-word start), so word-granularity stagger is the easy path.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-karaoke", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "ab cd")

with cmt.journal.batch("karaoke"):
    quads = cmt.text.karaoke(
        scn, title, (1.0, 0.9, 0.2, 1.0), start=1, word_gap=6, dur=10, ease="power2.out"
    )

assert len(quads) == 2, [q.name for q in quads]  # one per word, not one per character
for q in quads:
    assert cmt.provenance.origin(q) == "agent", (q.name, cmt.provenance.origin(q))


def first_keyframe(quad: object) -> float:
    target = cmt.text.color_target(quad)
    path = cmt.text.color_path(quad)
    fc = target.animation_data.action.fcurve_ensure_for_datablock(target, path, index=3)
    return fc.keyframe_points[0].co[0]


starts = sorted(first_keyframe(q) for q in quads)
assert starts == [1.0, 7.0], starts  # staggered by word_gap=6
