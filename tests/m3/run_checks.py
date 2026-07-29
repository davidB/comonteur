"""M3 scene authoring — run with: blender -b -P tests/m3/run_checks.py
Exercises anim.py, text.py, scene.py brand params, and library.py end to end,
headless. Mirrors tests/m1/run_checks.py's report format.
"""

import math
import os
import sys
import tempfile

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "addon"))

import comonteur as cmt  # noqa: E402

R = []


def report(id_, status, detail=""):
    R.append((id_, status, detail))
    print(f"[{id_}] {status}: {detail}")


project_dir = tempfile.mkdtemp(prefix="comonteur_m3_")
bpy.ops.wm.read_factory_settings(use_empty=True)
os.chdir(project_dir)

cmt.register()
scene = cmt.scene.new_scene("shot-01", fps=30, resolution=(1920, 1080), frame_range=(1, 90))

# --- anim.tween: real keyframes, correct easing, must run inside a batch ---
title = cmt.text.create(scene, "Ship faster", name="Title")
try:
    cmt.anim.tween(title, "location", index=1, frm=-0.4, to=0.0, start=12, dur=20, ease="back.out")
    report("M3.tween_guard", False, "tween() should have raised outside a batch")
except RuntimeError:
    report("M3.tween_guard", True, "raised RuntimeError outside journal.batch()")

with cmt.journal.batch("reveal title"):
    cmt.anim.tween(title, "location", index=1, frm=-0.4, to=0.0, start=12, dur=20, ease="back.out")

fc = title.animation_data.action.fcurve_ensure_for_datablock(title, "location", index=1)
kf0, kf1 = fc.keyframe_points[0], fc.keyframe_points[1]
scene.frame_set(32)  # the curve now drives location — read its evaluated value at frame 32
report(
    "M3.tween_keyframes",
    len(fc.keyframe_points) == 2
    and kf0.co[0] == 12
    and kf1.co[0] == 32
    and kf0.interpolation == "BACK"
    and kf0.easing == "EASE_OUT"
    and math.isclose(title.location[1], 0.0, abs_tol=1e-5),
    f"keys={[(k.co[0], k.co[1]) for k in fc.keyframe_points]} interp={kf0.interpolation}/{kf0.easing}",
)
scene.frame_set(1)

# --- anim.stagger over several objects ---
letters = [cmt.text.create(scene, ch, name=f"L{ch}") for ch in "AB"]
with cmt.journal.batch("stagger letters"):
    cmt.anim.stagger(letters, "location", index=1, offset=5, frm=-0.2, to=0.0, start=1, dur=10)
starts = [
    obj.animation_data.action.fcurve_ensure_for_datablock(obj, "location", index=1)
    .keyframe_points[0]
    .co[0]
    for obj in letters
]
report("M3.stagger", starts == [1, 6], f"starts={starts}")

# --- text.fit_to_box: shrinks until it fits ---
big = cmt.text.create(scene, "A very long headline that overflows", name="Headline", size=2.0)
cmt.text.fit_to_box(big, width=3.0, height=1.0)
report(
    "M3.fit_to_box",
    big.dimensions.x <= 3.0 + 1e-3 and big.dimensions.y <= 1.0 + 1e-3,
    f"dimensions={tuple(big.dimensions)} size={big.data.size}",
)

# --- text.split_chars: real per-character objects, left to right ---
word = cmt.text.create(scene, "Hi", name="Word")
chars = cmt.text.split_chars(word)
report(
    "M3.split_chars",
    len(chars) == 2
    and chars[0].data.body == "H"
    and chars[1].data.body == "i"
    and chars[1].location.x > chars[0].location.x
    and "Word" not in scene.objects,
    f"chars={[(c.name, c.data.body, c.location.x) for c in chars]}",
)

# --- scene.py brand params: string param syncs into bound text object ---
headline = cmt.text.create(scene, "Draft", name="Headline2")
cmt.scene.bind_param(headline, "headline")
cmt.scene.set_param(scene, "headline", "Final copy")
bpy.context.view_layer.update()
report("M3.brand_param_sync", headline.data.body == "Final copy", f"body={headline.data.body!r}")

# --- library.py: discover + link, provenance survives linking (M0.6) ---
lib_path = os.path.join(project_dir, "component.blend")
bpy.data.actions.new("_unused")  # keep the save from being a totally empty file
bounce = bpy.data.actions.new("BounceIn")
bounce.asset_mark()
bounce.asset_data.description = "Bounce-in reveal"
bounce.asset_data.tags.new("reveal")
bpy.ops.wm.save_as_mainfile(filepath=lib_path)

cmt.unregister()
bpy.ops.wm.read_factory_settings(use_empty=True)
cmt.register()
found = cmt.library.discover(lib_path, kinds=("actions",))
report(
    "M3.library_discover",
    any(a["name"] == "BounceIn" and a["description"] == "Bounce-in reveal" for a in found),
    str(found),
)

linked = cmt.library.link(lib_path, "actions", "BounceIn")
report(
    "M3.library_link",
    linked.name == "BounceIn" and cmt.provenance.origin(linked) == cmt.const.ORIGIN_AGENT,
    f"name={linked.name} origin={cmt.provenance.origin(linked)}",
)

cmt.unregister()

failures = [r for r in R if r[1] is False]
print(f"\n{len(R) - len(failures)}/{len(R)} passed")
if failures:
    sys.exit(1)
