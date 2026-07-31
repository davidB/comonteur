"""All three introspect functions are token-budgeted, and outline()'s counter tells the truth.

SKILL.md and references/api.md both promise the introspect trio is "capped and truncated
deliberately" — that promise is why the agent is told to use them instead of walking bpy.data.
animated_paths() had no cap at all: one dict per F-curve for every object in the scene.

Separately, outline()'s truncation counter did `len(objects) - len(lines)`, mixing an object
count with a line count. The lines list starts with the scene header and can hold collection
lines too, so the "+N more" figure was short by that many — an agent trusting it would think it
had nearly seen the whole scene.
"""

import _bl
import bpy

cmt = _bl.setup()

with cmt.journal.batch("fixture: many animated objects"):
    scn = cmt.scene.new_scene("shot-caps", fps=30, frame_range=(1, 90))
    objs = [cmt.text.create(scn, f"line {i}", size=0.4) for i in range(12)]
    for i, obj in enumerate(objs):
        # Three F-curves each (x/y/z) => 36 rows, comfortably over a small cap.
        for axis in (0, 1, 2):
            cmt.anim.tween(obj, "location", axis, frm=0.0, to=float(i), start=1, dur=10)

# Two child collections, so the "+N more" arithmetic has to survive non-object lines.
for name in ("props", "lights"):
    scn.collection.children.link(bpy.data.collections.new(name))

# --- animated_paths() is capped -------------------------------------------------------

uncapped = cmt.introspect.animated_paths(scn)
assert len(uncapped) == 36, f"fixture should produce 36 F-curves, got {len(uncapped)}"

capped = cmt.introspect.animated_paths(scn, max_lines=10)
rows = [r for r in capped if "truncated" not in r]
assert len(rows) == 10, f"max_lines=10 must keep 10 rows, got {len(rows)}"
assert rows == uncapped[:10], "the cap must truncate in order, not reorder or resample"

marker = [r for r in capped if "truncated" in r]
assert marker, f"truncation must be signalled — a silently short list reads as complete: {capped}"
assert marker[0]["truncated"] == 26, f"36 rows minus 10 shown = 26, got {marker[0]}"

# Under the cap, nothing is added.
assert all("truncated" not in r for r in cmt.introspect.animated_paths(scn, max_lines=100))

# --- outline()'s "+N more" counts objects, not lines -----------------------------------

outline = cmt.introspect.outline(scn, max_lines=8)
lines = outline.splitlines()
shown = sum(1 for line in lines if line.lstrip().startswith("Object:"))
more = [line for line in lines if "more" in line]
assert more, f"outline() truncated {len(objs)} objects without saying so:\n{outline}"

reported = int("".join(c for c in more[0] if c.isdigit()))
expected = len(scn.collection.objects) - shown
assert reported == expected, (
    f"'+{reported} more' but {shown} of {len(scn.collection.objects)} objects were shown, "
    f"so {expected} remain:\n{outline}"
)
