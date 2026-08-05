"""text.split_spans() splits into one FONT object per (start, end[, props]) span, not one
per character -- the word-granularity counterpart to split_chars() + style_spans().
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-spans2", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "ab cd")

RED = (0.8, 0.1, 0.1, 1.0)
BLUE = (0.1, 0.1, 0.8, 1.0)

words = cmt.text.word_spans(title.data.body)
assert words == [(0, 2), (3, 5)], words

with cmt.journal.batch("split spans"):
    parts = cmt.text.split_spans(title, [(*words[0], {"color": RED}), (*words[1], {"color": BLUE})])

assert len(parts) == 2, [p.name for p in parts]
assert parts[0].data.body == "ab", parts[0].data.body
assert parts[1].data.body == "cd", parts[1].data.body
assert parts[1].location.x > parts[0].location.x, (parts[0].location.x, parts[1].location.x)


def close(a: tuple, b: tuple) -> bool:
    return all(abs(x - y) < 1e-5 for x, y in zip(a, b))


bsdf0 = parts[0].data.materials[0].node_tree.nodes["Principled BSDF"]
assert close(tuple(bsdf0.inputs["Emission Color"].default_value), RED)
bsdf1 = parts[1].data.materials[0].node_tree.nodes["Principled BSDF"]
assert close(tuple(bsdf1.inputs["Emission Color"].default_value), BLUE)

# Issue #7: a partial span list (not covering the whole body) used to silently drop the
# uncovered text instead of passing it through unstyled.
FIRE_ORANGE = (0.9, 0.4, 0.1, 1.0)

with cmt.journal.batch("fixture 2"):
    accent_title = cmt.text.create(scn, "leading text and weekly status")

accent_body = accent_title.data.body
accent_start = accent_body.index("weekly")
with cmt.journal.batch("split spans partial"):
    accent_parts = cmt.text.split_spans(
        accent_title, [(accent_start, len(accent_body), {"color": FIRE_ORANGE})]
    )

assert len(accent_parts) == 2, [p.name for p in accent_parts]
assert accent_parts[0].data.body == accent_body[:accent_start], accent_parts[0].data.body
assert accent_parts[1].data.body == "weekly status", accent_parts[1].data.body
assert accent_parts[1].location.x > accent_parts[0].location.x, (
    accent_parts[0].location.x,
    accent_parts[1].location.x,
)
