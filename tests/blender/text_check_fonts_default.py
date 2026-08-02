"""text.check_fonts() flags FONT objects still on Blender's built-in default
(data.font is None) — the gate hyperframes-import.md's font step now points to.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-fonts", fps=30, frame_range=(1, 90))

assert cmt.text.check_fonts(scn) == [], "empty scene must not flag anything"

with cmt.journal.batch("fixture: default font"):
    obj = cmt.text.create(scn, "Ship faster", size=0.8)

flagged = cmt.text.check_fonts(scn)
assert flagged == [{"name": obj.name}], flagged
