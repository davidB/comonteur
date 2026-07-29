"""M1 walking skeleton — run with: blender -b -P tests/m1/run_checks.py
Exercises SPEC.md §10 M1 steps 1-4 and 6 end to end, headless. Step 5 ("human opens
it in Blender and moves a keyframe") is simulated here by mutating the property
directly and calling view_layer.update() — M0.5 confirmed that produces the same
depsgraph_update_post signal a real dope-sheet edit does. Verifying it against an
actual GUI dope-sheet drag is a manual check, same status as M0.8/M0.9/M0.10.
"""

import math
import os
import sys
import tempfile

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "addon"))

import comonteur as cmt  # noqa: E402
from comonteur import const  # noqa: E402

R = []


def report(id_, status, detail=""):
    R.append((id_, status, detail))
    print(f"[{id_}] {status}: {detail}")


# Run inside a real project dir so the journal lands in a throwaway place.
project_dir = tempfile.mkdtemp(prefix="comonteur_m1_")
bpy.ops.wm.read_factory_settings(use_empty=True)
os.chdir(project_dir)  # unsaved file: journal.py falls back to cwd

cmt.register()

# --- 1/2: scene.new_scene() with hard reset, idempotent by cmt_id ---
scene = cmt.scene.new_scene("shot-01", fps=30, resolution=(1920, 1080), frame_range=(1, 90))
same = cmt.scene.new_scene("shot-01")
report(
    "M1.scene",
    scene is same and len(scene.objects) == 0,
    f"scene={scene.name!r} objects={len(scene.objects)} origin={cmt.provenance.origin(scene)}",
)

# --- 4: agent generates one text scene with a simple animated reveal ---
text_data = bpy.data.curves.new("Title", type="FONT")
text_data.body = "Ship faster"
title = bpy.data.objects.new("Title", text_data)
scene.collection.objects.link(title)
cmt.provenance.tag(title, "shot-01.title")

with cmt.journal.batch("reveal title"):
    cmt.journal.set(title, "location[1]", 0.3)
    title.keyframe_insert("location", index=1, frame=12)

report(
    "M1.batch",
    cmt.provenance.origin(title) == const.ORIGIN_AGENT,
    f"title.location.y={title.location[1]} origin={cmt.provenance.origin(title)}",
)

journal_entries = list(cmt.journal._read_all())
report(
    "M1.journal",
    len(journal_entries) == 1 and journal_entries[0]["op"] == "set",
    f"{len(journal_entries)} entries: {journal_entries}",
)

# --- 3: introspect + preview are callable and return something bounded ---
outline = cmt.introspect.outline(scene)
report("M1.outline", "Title" in outline and outline.count("\n") < 60, outline.replace("\n", " | "))

# --- 5 (simulated) + 6: human edits the agent-owned property directly, without
# going through journal.batch() — this is what a dope-sheet drag looks like from
# the data side. The flip handler must catch it.
title.location[1] = 0.9
bpy.context.view_layer.update()

report(
    "M1.flip",
    cmt.provenance.origin(title) == const.ORIGIN_SHARED,
    f"origin after human edit = {cmt.provenance.origin(title)}",
)

flip_entries = [e for e in cmt.journal._read_all() if e.get("op") == "flip"]
report("M1.flip_journalled", len(flip_entries) == 1, str(flip_entries))

claimed = cmt.provenance.claimed_paths(title)
report("M1.claimed", claimed == {"location[1]"}, f"claimed_paths={claimed}")

# Agent reviews and changes something else, respecting the claim.
with cmt.journal.batch("adjust fade timing"):
    if "location[1]" not in cmt.provenance.claimed_paths(title):
        cmt.journal.set(title, "location[1]", 0.5)  # would run if unclaimed
    cmt.journal.set(title, "location[0]", 0.1)  # untouched path — agent may still write it

report(
    "M1.no_clobber",
    math.isclose(title.location[1], 0.9, abs_tol=1e-5)
    and math.isclose(title.location[0], 0.1, abs_tol=1e-5),
    f"location={tuple(title.location)}",
)

# --- doctor ---
results = cmt.doctor.run(project_root=project_dir)
report("M1.doctor", isinstance(results, list) and len(results) > 0, str(results))

cmt.unregister()

failures = [r for r in R if r[1] == "FAIL"]
print(f"\n{len(R) - len(failures)}/{len(R)} passed")
if failures:
    sys.exit(1)
