"""text.style_spans() colors index ranges of split_chars() output independently —
color/font live on individual objects (one material per FONT object), so multi-color
inline spans go through split_chars() + a per-range style() loop.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-spans", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "ab cd")
    chars = cmt.text.split_chars(title)

RED = (0.8, 0.1, 0.1, 1.0)
BLUE = (0.1, 0.1, 0.8, 1.0)

with cmt.journal.batch("style spans"):
    cmt.text.style_spans(chars, [(0, 2, {"color": RED}), (3, 5, {"color": BLUE})])


def close(a: tuple, b: tuple) -> bool:
    return all(abs(x - y) < 1e-5 for x, y in zip(a, b))


for i in (0, 1):
    bsdf = chars[i].data.materials[0].node_tree.nodes["Principled BSDF"]
    got = tuple(bsdf.inputs["Emission Color"].default_value)
    assert close(got, RED), (i, got)
for i in (3, 4):
    bsdf = chars[i].data.materials[0].node_tree.nodes["Principled BSDF"]
    got = tuple(bsdf.inputs["Emission Color"].default_value)
    assert close(got, BLUE), (i, got)
assert len(chars[2].data.materials) == 0, "the space glyph was outside both spans"
