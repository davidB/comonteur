"""preview.frames() leaves the human's render settings exactly as it found them.

It restored the active scene and the render engine but not `render.filepath` or the current
frame. Since comonteur:render uses "the file's own output settings", one preview silently
redirected the human's next render into .comonteur/review/ — a data-loss-shaped bug they would
only notice after a long render landed in the wrong place.

This asserts restoration on the *error* path, which is the stronger guarantee and the one that
runs here: `bpy.ops.render.opengl` cannot work in background mode ("Cannot use OpenGL render in
background mode"), so frames() raises. State must survive that, not just the happy path.
"""

import _bl

cmt = _bl.setup()

with cmt.journal.batch("fixture"):
    scn = cmt.scene.new_scene("shot-preview", fps=30, frame_range=(1, 90))
    cmt.text.create(scn, "Ship faster", size=0.8)

# references/api.md tells the agent to pass engine="BLENDER_EEVEE_NEXT" — that enum does not
# exist on the pinned 5.2, so following the doc raises on first use. Pin the real name here so
# the doc cannot drift back. (enum_items on the RNA type lists only static entries, so assign
# and see rather than introspecting.)
assert _bl.raises(TypeError, lambda: setattr(scn.render, "engine", "BLENDER_EEVEE_NEXT")), (
    "BLENDER_EEVEE_NEXT is accepted again — api.md's engine name is valid, update this test"
)

SENTINEL = "//renders/final_####"
scn.render.filepath = SENTINEL
scn.render.engine = "BLENDER_EEVEE"
scn.frame_set(42)

try:
    cmt.preview.frames(scn, [1, 45, 90])
except RuntimeError as e:
    # Expected headless: no OpenGL context. Any other RuntimeError is a real failure.
    assert "background" in str(e).lower() or "opengl" in str(e).lower(), e

assert scn.render.filepath == SENTINEL, (
    f"preview.frames() left render.filepath at {scn.render.filepath!r} — "
    f"the human's next render would go there"
)
assert scn.frame_current == 42, f"preview.frames() left the playhead at {scn.frame_current}"
assert scn.render.engine == "BLENDER_EEVEE", scn.render.engine
