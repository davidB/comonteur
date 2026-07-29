# M1 — Walking skeleton: findings

Built `addon/comonteur/{const,paths,journal,provenance,scene,introspect,preview,doctor,ui}.py`.
Reproduce: `blender -b -P tests/m1/run_checks.py` (9/9 checks) and `uv run pytest`
(pure-logic path resolver, 5/5).

## Verdict

**Step 6 holds.** Agent batch-writes a path, human overwrites it directly (simulating
a dope-sheet drag), the flip handler marks the object `shared` and journals it, and a
second agent batch correctly skips the claimed path while still writing an unclaimed
one on the same object. Undo stays one labelled push per batch (guarded to no-op
headless, per M0.8 — no window to push to outside a GUI session).

## One real finding: the flip gate in §4.3's pseudocode misfires

`depsgraph_update_post` is not synchronous with property writes — Blender defers it
until the depsgraph is actually evaluated (e.g. `view_layer.update()`, `frame_set()`,
or the next operator/redraw). §4.3's pseudocode gates the handler on
`journal.batch_active()`, but if evaluation happens *after* the batch's `with` block
has already exited, `batch_active()` has already flipped back to `False` and the
batch's own writes get misread as a human edit on the next unrelated evaluation.

Caught live: in the first run, `journal.batch()`'s writes (a location set +
`keyframe_insert`) hadn't triggered an evaluation by the time the block exited. The
*next* evaluation was the test's own `view_layer.update()` simulating the human edit —
which then flipped both the object *and* the scene, and journalled two spurious flips.

**Fix, applied in `journal.py`:** `batch()` calls `bpy.context.view_layer.update()`
once at the end of its `finally`, before releasing the gate (`active = False`). This
forces any pending updates from the batch's own writes to be evaluated — and ignored —
while `batch_active()` is still true. Cheap (one eval per batch, not per write) and
makes the gate correctness match the pseudocode's intent instead of just its literal
code.

Consequence for later milestones: any code path that mutates agent-owned data outside
`journal.batch()` (there shouldn't be one, per §4.2/§4.4) would reintroduce this gap.
`anim.tween`/`stagger` (M3) and `reconcile` (M4) must go through `journal.set()`
inside a batch, not raw `bpy` calls, or this bug comes back per-module.

## Deferred out of M1 scope (not on the walking-skeleton checklist)

- `introspect.drift()` / `.comonteur/snapshot.json` — needs `reconcile` (M4) to have
  something worth diffing against. `claimed_paths()` alone doesn't need a snapshot; it
  derives from the journal directly, per §4.3.
- `anim.py`, `text.py`, Actions/NLA — M3.
- Packaged install (`blender --command extension install-file`) — `mise-tasks/install-addon`
  symlinks into the user extensions repo for dev iteration instead; M5.5 does the zip.
