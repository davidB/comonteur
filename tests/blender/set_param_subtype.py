"""scene.set_param() applies subtype/min/max to colours and vectors, not only to scalars.

The UI metadata block was gated on `isinstance(value, (int, float))`, so the exact call
references/api.md recommends — a 4-tuple with subtype="COLOR" — fell straight through it. The
human got a raw four-float array instead of a colour swatch, with no error to explain why.
Brand params are the one part of a shot the human is *expected* to edit by hand, so a param
they cannot find in the sidebar is the failure this whole feature exists to prevent.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-params", fps=30, frame_range=(1, 90))

with cmt.journal.batch("brand params"):
    cmt.scene.set_param(scn, "accent", (0.1, 0.6, 0.9, 1.0), subtype="COLOR")
    cmt.scene.set_param(scn, "offset", (1.0, 2.0, 3.0), subtype="TRANSLATION")
    cmt.scene.set_param(scn, "opacity", 0.5, min=0.0, max=1.0)
    cmt.scene.set_param(scn, "headline", "Ship faster")

assert tuple(scn["accent"]) == (0.1, 0.6, 0.9, 1.0)
assert scn.id_properties_ui("accent").as_dict()["subtype"] == "COLOR"
assert scn.id_properties_ui("offset").as_dict()["subtype"] == "TRANSLATION"

# The scalar path already worked — this pins it so the widened gate does not break it.
scalar_ui = scn.id_properties_ui("opacity").as_dict()
assert (scalar_ui["min"], scalar_ui["max"]) == (0.0, 1.0), scalar_ui

# Strings have no id_properties_ui subtype to set; they must not raise on the way through.
assert scn["headline"] == "Ship faster"

# Booleans are ints in Python; treating one as a slider would be nonsense.
with cmt.journal.batch("bool param"):
    cmt.scene.set_param(scn, "loop", True)
assert scn["loop"] is True or scn["loop"] == 1
