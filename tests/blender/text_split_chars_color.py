"""text.split_chars() must preserve a style()'d source object's color and its true
left edge (measure()'s world-space min.x, not obj.location.x) -- a regression test
for a real bug: the previous version dropped color entirely (leaving karaoke()'s
per-word chars invisible/black) and ignored align_x='CENTER', shifting centered text
right by half its own width once split.
"""

import _bl

cmt = _bl.setup()

RED = (0.8, 0.1, 0.1, 1.0)

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-split-color", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "ab", color=RED)
    title.data.align_x = "CENTER"

before_box = cmt.text.measure(title)
before_center_x = (before_box["min"][0] + before_box["max"][0]) / 2
before_width = before_box["max"][0] - before_box["min"][0]

with cmt.journal.batch("split"):
    chars = cmt.text.split_chars(title)


def close(a: tuple, b: tuple) -> bool:
    return all(abs(x - y) < 1e-5 for x, y in zip(a, b))


for c in chars:
    assert c.data.materials, f"{c.name} lost its color across split_chars()"
    bsdf = c.data.materials[0].node_tree.nodes["Principled BSDF"]
    got = tuple(bsdf.inputs["Emission Color"].default_value)
    assert close(got, RED), (c.name, got)

after_min_x = min(cmt.text.measure(c)["min"][0] for c in chars)
after_max_x = max(cmt.text.measure(c)["max"][0] for c in chars)
after_center_x = (after_min_x + after_max_x) / 2

# The bug: split_chars() ignored align_x='CENTER' and laid chars out left-anchored
# from obj.location.x, shifting a centered string right by ~half its own width.
# A generous tolerance since split_chars()'s per-glyph advance-width sum is an
# approximation of the source object's true glyph-outline bounding box.
assert abs(after_center_x - before_center_x) < 0.3 * before_width, (
    after_center_x,
    before_center_x,
    before_width,
)
