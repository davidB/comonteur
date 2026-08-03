# M4 — VSE assembly: findings

Blender **5.2.0 LTS** (build 2026-07-15), Linux. Unknowns not covered by M0/M3, checked
via a headless spike (`blender -b -P tests/m4/run_checks.py`) before writing
`reconcile.py`. M0 already confirmed `sequence_editor.strips` (not `.sequences`),
`strips.new_scene(scene=<linked scene>, ...)` (M0.7), and that VSE strips accept custom
properties surviving save/load (M0.1). This spike closes the rest.

## Results

| Check | Result |
|---|---|
| Link a **non-asset** Scene | **PASS.** `bpy.data.libraries.load(blend_path, link=True)` — no `assets_only=True` — links a plain generated Scene by name same as any other datablock. `library.py`'s existing `link()`/`discover()` are `assets_only=True` for `lib/` component discovery; `shots/*.blend` scenes need a separate non-asset-restricted path (`library.link_scene()`, step 3 of the plan). |
| `strips.new_movie(name, filepath, channel, frame_start)` | **PASS**, exact kwargs work as expected. `frame_final_duration` is populated from the media's real length automatically (30 frames for a 1s/30fps clip). |
| `strips.new_sound(name, filepath, channel, frame_start)` | **PASS**, same shape as `new_movie`. `frame_final_duration` reflects the audio file's length in scene frames (24 frames for a 1s clip at the scene's fps — confirms frame, not sample, units). |
| `strips.new_effect(type='CROSS', ...)` crossfade | **PASS, with two API traps.** (1) `frame_start`/`length` are **strict `int`**, not float — arithmetic on other strips' `frame_start`/`frame_final_end` (which read back as `float`) must be cast with `int(...)` before passing in, or Blender raises `TypeError`. (2) The kwarg names are **`input1`/`input2`**, not `seq1`/`seq2` (some online examples/older docs use the latter — another generated-code trap, same category M0.4 already flagged for `length` vs `frame_end`). |
| Channel-overlap behaviour | **No validation/rejection.** Two strips with overlapping frame ranges on the same channel are both created without error or clamping — Blender lets you build an invalid/overlapping timeline silently. **`reconcile.py` must not rely on VSE-side validation**; it needs its own channel-allocation convention (fixed channel per role — e.g. shots on channel 1, audio on channel 2, transitions on channel 3 — is enough for v1 since shots are sequential and don't share a channel with anything that could overlap them). |
| Custom properties on movie/sound/effect strips survive save/load | **PASS** for all three strip kinds, same round-trip guarantee M0.1 already proved for Scene strips. |

## Check 2 — the automatic origin flip (§4.3) does not fire for strip edits

Found live while wiring `reconcile.apply()` end to end (not part of the original spike
list, but load-bearing enough to belong here). `bpy.app.handlers.depsgraph_update_post`
reports updates keyed by **ID datablock** (`upd.id`). VSE strips are not ID datablocks —
they're sub-data hanging off `Scene.sequence_editor`, same category as modifiers or
constraints. Editing `strip.frame_start` produces a depsgraph update whose `upd.id` is
the **Scene**, not the strip:

```python
strip.frame_start = 5
# depsgraph_update_post fires with upd.id == the Scene, never the strip itself
```

Confirmed with a minimal repro (`bpy.app.handlers.depsgraph_update_post` callback
recording `type(upd.id).__name__`): creating and editing a tagged effect strip both
report `('Scene', 'Master')` and nothing else.

**Consequence:** `provenance._on_depsgraph_update` (§4.3) checks
`id_.get("cmt_origin") == "agent"` on `upd.id` — for a strip edit that's the *Scene*,
which is not agent-tagged (the timeline scene is human-owned; only individual strips
carry `cmt_id`/`cmt_origin`). So a human dragging a strip in the timeline **never**
flips that strip's `cmt_origin` from `agent` to `shared`, unlike Object/Action edits.

This does **not** break field-level claim protection: `provenance.claimed_paths()` is
derived straight from the journal (`journal.paths_written_by_agent()` vs
`journal.last_agent_value()` vs the strip's live value) and never reads `cmt_origin` at
all, so `reconcile.diff()`'s per-field update-skip already works correctly for strips.
It **does** break delete-safety if that safety only checks `origin == "agent"` (§4.1's
literal rule): a strip a human edited but that got dropped from `timeline.toml` would
still read as agent-owned and get deleted. **Fix applied in `reconcile.diff()`**: the
delete condition is `origin == agent AND not claimed[cmt_id]` — reusing the
already-correct claim signal instead of trusting the flip for strips specifically. No
change needed to `provenance.py` itself; this is a `reconcile.py`-local adaptation for a
data kind (strips) the original §4.3 design didn't anticipate.

## Consequences for `reconcile.py` / `timeline.rs`

- Any frame number reconcile computes (whether from an absolute `start` or a resolved
  anchor) must be passed to VSE strip APIs as a plain `int`. The Rust side already
  emits integer `start_frame`/`duration_frames` (§ resolved-JSON contract), so this is a
  reminder for the Python side: cast before calling `new_effect`, and when reading back
  `frame_start`/`frame_final_end` for transition math, wrap in `int(...)` — they read
  back as `float`.
- Use `input1=`/`input2=`, not `seq1=`/`seq2=`, for `new_effect`.
- `reconcile.apply()` owns a fixed channel-per-role convention (shots / audio /
  transitions on separate channels) rather than trusting Blender to catch overlaps.
- `library.link_scene()` (new, step 3) must **not** pass `assets_only=True` — that's the
  one thing that differs from the existing `library.link()`.
