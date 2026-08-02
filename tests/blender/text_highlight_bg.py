"""text.measure_many()'s union bbox and text.highlight_bg()'s quad built from it — the
primitive a highlight/background box needs to span a whole word, not one glyph.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-highlight", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "ab")
    chars = cmt.text.split_chars(title)

boxes = [cmt.text.measure(c) for c in chars]
union = cmt.text.measure_many(chars)
assert union["min"][0] <= min(b["min"][0] for b in boxes) + 1e-6, union
assert union["max"][0] >= max(b["max"][0] for b in boxes) - 1e-6, union

with cmt.journal.batch("highlight"):
    bg = cmt.text.highlight_bg(scn, chars, (1.0, 0.9, 0.2, 0.4), padding=0.1)

bg_box = cmt.text.measure(bg)
assert bg_box["min"][0] < union["min"][0], (bg_box, union)  # padding grows the box
assert bg_box["max"][0] > union["max"][0], (bg_box, union)
assert cmt.provenance.origin(bg) == "agent", cmt.provenance.origin(bg)
