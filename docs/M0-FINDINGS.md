# M0 — API verification spike: findings

Blender **5.2.0 LTS** (build 2026-07-15), Linux. Checks scripted per `SPEC.md` §10.
Reproduce: `blender -b -P tests/m0/run_checks.py` (checks M0.1–M0.7 run automatically
and print `[M0.x] PASS/FAIL/INFO: ...` lines; M0.8's timer path needs a GUI session, see
below). M0.9–M0.11 needed the official MCP add-on installed and a running GUI Blender,
not just `-b` — see the reproduction section near the end of this doc.

## Verdict on the two highest-impact unknowns

**M0.7 PASSES.** A linked Scene can be used as a VSE Scene strip. §5.1's repo layout
(`compositions/frames/*.blend` linked into `timeline.blend`) stands — no revision to §5.1
needed.

**M0.9 PASSES.** `execute_python` on the official MCP add-on runs on Blender's main
thread. The fork trigger in §7.4 does not fire — build against the official add-on.

All 11 checks are now resolved; M0 is complete.

## Results

| # | Check | Result |
|---|---|---|
| M0.1 | VSE strips accept custom properties, survive save/load | **PASS.** Scene, Object and VSE strip custom props (`cmt_id` etc.) all round-trip through `save_as_mainfile` / `open_mainfile`. |
| M0.2 | `bpy.ops.scene.new(type=…)` semantics | `EMPTY` and `NEW` give a scene with 0 objects (genuinely empty — no inherited cube/camera/light). `LINK_COPY`/`FULL_COPY` carry objects over, as expected. **`new_scene()` should use `type='EMPTY'`** (or `'NEW'` — both empty; `EMPTY` is the more explicit intent) rather than assume the default `NEW` context-menu semantics. |
| M0.3 | Geometry Nodes modifier property API shape | **Changed in 5.2, confirmed.** Old form `mod[identifier] = value` now raises `TypeError: id properties not supported for this type`. New form: `getattr(mod.properties.inputs, identifier).value = ...`, read via `.value`. `identifier` still comes from `node_group.interface.new_socket(...).identifier` (e.g. `"Socket_0"`). Use this new form everywhere in `library.py`/`scene.py` when driving GN modifier inputs. |
| M0.4 | VSE strip API post `sequences`→`strips` rename | Confirmed: `sequence_editor.strips` exists, `.sequences` does not. `strips.new_effect(...)` takes `length`, not `frame_end` (differs from some online examples/older API docs — trap for generated code). Text strips (`type="TEXT"`) expose `.text` and `.transform`; `.blend_type`, `.channel`, `.frame_final_start` present on strips generally. |
| M0.5 | `depsgraph_update_post`: usable? `upd.id.original` reliable? selection noise? cost? | `upd.id.original` resolves correctly to the original datablock (not the evaluated copy) in both cases tested. **Noise confirmed**: selecting an object and calling `view_layer.update()` produced an update for that object with `is_updated_transform=True` even though nothing was actually moved — selection alone is not distinguishable from a real transform via this flag. The coarse-flip design in §4.3 already assumes this; do not try to filter finer than "some agent-owned datablock changed" in the handler itself. Cost was not measured at scale (small scene only) — revisit with a real production scene in M1. |
| M0.6 | Custom properties survive **linking** | **PASS.** Both Scene- and Object-level `cmt_id` survive `bpy.data.libraries.load(..., link=True)`. |
| M0.7 | Linked Scene usable as VSE Scene strip | **PASS** (see above). `sequence_editor.strips.new_scene(scene=<linked scene>, ...)` works with no special handling. |
| M0.8 | `bpy.ops.ed.undo_push` from a timer callback | **PASS, verified in a live GUI session** (previously only the non-timer path was confirmed headless). Registered `bpy.app.timers.register(timer_cb)` where `timer_cb` calls `bpy.ops.ed.undo_push(message=...)`; fired on `MainThread`, returned `{'FINISHED'}`, no context error. Safe to rely on for the batch protocol (§4.5). |
| M0.9 | Official MCP add-on: does `execute_python` run on the main thread? | **PASS, verified.** `threading.current_thread() is threading.main_thread()` → `True` inside `execute_blender_code`. **Fork trigger in §7.4 does not fire** — the official add-on is usable as-is for mutation; do not fork it. `bpy.context.window`/`.screen` are also live (not a restricted context), so operator-based code works normally, not just the data API. |
| M0.10 | `bpy.ops.render.opengl` in a running GUI session; getting the image back | **PASS, verified.** Both raw `bpy.ops.render.opengl(write_still=True)` and the MCP add-on's own `render_viewport_to_path` tool produce a real PNG. **Caveat**: the add-on's tool sandboxes output into its own temp dir (`/tmp/blender_XXXXXX/blender_mcp/...`) rather than writing to the literal `output_path` passed in — `preview.py` must read the *returned* `filepath` from the tool result, not assume the requested path. |
| M0.11 | `blender --command extension install-file` syntax | **Confirmed via `--help`, available in 5.2**: `blender --command extension install-file -r REPO [-e] [--no-prefs] FILE`. Default local repo id is `user_default` (`blender --command extension repo-list`) — use that as `-r` in `comonteur:install_addon` (M5.5) unless a dedicated repo is created. **In use since**: `comonteur:install_addon` builds the add-on with `extension build` and installs it this way; the Blender Lab MCP add-on goes in with `extension repo-add lab_blender_org --url https://lab.blender.org/` + `extension install mcp --sync --enable` (repo id and package id match what GUI drag-and-drop creates, so a hand-installed add-on is detected, not duplicated). Enabling has no `--command` equivalent — it needs `blender -b --python-expr` with `bpy.ops.preferences.addon_enable` + `wm.save_userpref()`, which a later GUI session will overwrite unless Blender is closed. **Re-verified on 5.2** when the tasks moved to Python: the subcommand list is server-generate/build/validate/list/sync/update/install/install-file/remove/repo-{list,add,remove} — still no enable/disable, and `--addons` is per-launch only. `install-file -e` covers the packaged path, so `bpy.ops` is now used *only* for the symlinked dev install. Also confirmed there: `repo-list` prints an absolute `directory:` per repository, which is how `install_addon.py` finds where to symlink instead of hardcoding `~/.config/blender/<ver>/extensions/user_default`. **Trap, hit for real:** `repo-add` can make a package that was already on disk (dropped in via the GUI before its repository was registered) appear as `mcp [installed]` immediately — so an `if installed: return` skips the install *and* its `-e`, leaving the add-on installed but **disabled**. `extension list` reports `[installed]` and never the enabled state, so it cannot tell you. Always call `enable_addon()` regardless of whether you did the installing; it is a no-op when already enabled. |

## Bug/environment note (not an M0 item, but hit during the spike)

Every `blender` invocation in this environment prints a `ModuleNotFoundError: No module
named 'cattrs'` traceback from the bundled `bl_pkg` extensions add-on
(`_bpy_internal/http/downloader.py`) on startup, and re-triggers noisy add-on
re-registration logs on every `read_factory_settings()` call. It does not block any
check above (all exit 0, all data comes through), but it pollutes stdout/stderr enough
that **`doctor` (M1) and any script parsing Blender's output should filter these lines**
rather than assume clean output. Root cause is an environment Python missing `cattrs`,
not a comonteur bug — worth a `doctor` check anyway since it will confuse users.

## Consequences for later milestones

- `scene.new_scene()` (§6.1): use `bpy.ops.scene.new(type='EMPTY')`, not `'NEW'`.
- Any GN modifier-input code (`library.py`, `scene.py`, brand params in §9): use the
  `mod.properties.inputs.<identifier>.value` form, not `mod[identifier]`.
- `vse.py` / `reconcile.py`: use `sequence_editor.strips`, and `length=` not `frame_end=`
  when creating effect strips.
- `provenance.py`'s depsgraph handler: confirmed it cannot distinguish selection from a
  real edit at the flag level — the coarse "flip on any update, refine via claimed_paths"
  design in §4.3 is the right call, not a workaround to revisit.
- M0.9 confirmed: build the batch protocol (§4.5) and `journal.py` directly against the
  official add-on. No fork needed.
- `preview.py` (§6.4): call the add-on's `render_viewport_to_path` tool (or
  `bpy.ops.render.opengl(write_still=True)` via `execute_python`) and use the *returned*
  path, not the requested one — the add-on redirects output into its own sandboxed temp
  dir.
- M5.5 (`comonteur:install_addon`): `-r user_default` confirmed as the install target for
  `extension install-file`.

## M0.9/M0.10 reproduction (needs a live Blender + MCP add-on)

Unlike M0.1–M0.8, these need a running Blender GUI with the official MCP add-on enabled
and connected (not just `blender -b`). Verified interactively via the `blender` MCP
server's `execute_blender_code` tool:

```python
import threading, bpy
result = {
    "is_main_thread": threading.current_thread() is threading.main_thread(),
    "context_window": bpy.context.window is not None,
}
# -> {"is_main_thread": true, "context_window": true}
```

```python
import bpy
r = bpy.ops.render.opengl(write_still=True)  # after setting scn.render.filepath
result = {"op_result": str(r)}
# -> {"op_result": "{'FINISHED'}"}
```
