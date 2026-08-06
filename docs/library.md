# comonteur — The in-Blender library

Part of the [comonteur spec](../SPEC.md). Section numbers match the original SPEC.md for
continuity with existing code comments (`SPEC.md §6...`).

---

## 6. The in-Blender library (`addon/comonteur/`)

This is where all discipline lives, because the MCP server provides none (§7). It exists
equally to **reduce agent token consumption**: the agent calls
`cmt.text.reveal(scene, "Hello", start=12, ease="BACK_OUT")` (canonical alias
`import comonteur as cmt`), not forty lines of `keyframe_points.insert()`.

| Module | Responsibility |
|---|---|
| `provenance.py` | tag / flip handler / `claimed_paths` / ownership queries / take-ownership operators |
| `journal.py` | `batch()` context manager, `set()`, JSONL, snapshot, revert |
| `scene.py` | `new_scene()` — see §6.1. `add_camera()` — ortho camera for the `kind='2d'` unit convention, see §6.1. Scene params interface. |
| `anim.py` | `tween`, `stagger`, `idle_jitter` (sine wobble, pre-sampled), `hard_cut` (instant show/hide via CONSTANT hide_render/hide_viewport keyframes), easing map, F-curve helpers |
| `gn.py` | Geometry Nodes effect builders (`char_reveal`, `apply`, `input_path`) — non-baked procedural VFX, see §6.2 |
| `text.py` | text objects, styling, fit-to-box, `measure`/`measure_many` (world-space bounding box — object must be visible at the current frame, `matrix_world` freezes stale for a hidden one), per-character split (preserves color and true left edge), `alpha_path` (Alpha-input fade, distinct from `color_path`'s alpha channel which Blender ignores). `style()`/`create()` color defaults to `shading='flat'` (Emission, since `kind='2d'` scenes have no lights) — pass `shading='lit'` for plain Base Color in lit 3D scenes. |
| `color.py` | `hex_to_rgba`/`srgb_to_linear` — sRGB hex colors decoded to the linear RGBA Emission/Base Color inputs expect |
| `vse.py` | assembly, scene strips, transitions, audio |
| `library.py` | link `lib/*.blend` (component library) and `shots/*.blend` (per-shot scenes), asset catalog discovery |
| `project.py` | project-root discovery (`.comonteur/` marker) + portable `//`-relative asset path resolution, used by `library.py`/`journal.py`/`preview.py`/`reconcile.py` |
| `card.py` | `create()` — image plane + hairline border + soft shadow bundle, the HyperFrames "card" pattern. `reorigin_left()` — re-origin a plane's mesh for edge-anchored scale-growth (progress bars, underline reveals) |
| `introspect.py` | `outline`, `describe`, `animated_paths`, `find`, `drift` |
| `preview.py` | render frames for agent review |
| `reconcile.py` | timeline.toml → VSE |

### 6.1 `new_scene()` — deterministic baseline (hard requirement)

Creating a scene must **never** inherit state from `bpy.context.scene`. Every generated
scene starts from an explicit, known baseline:

```python
def new_scene(name, *, kind, fps, resolution, frame_range,
              transparent=True, view_transform=None) -> bpy.types.Scene
```

Must:
1. Create the scene, then **remove every inherited object** (default cube/camera/light).
   Verify `bpy.ops.scene.new(type=...)` semantics in M0.2 rather than assuming.
2. Set explicitly, never inherit: render engine, `resolution_x/y`,
   `resolution_percentage`, `fps`, `fps_base`, `frame_start`, `frame_end`,
   `film_transparent`, world.
3. Set `view_settings.view_transform`. **`'Standard'` for 2D/graphics scenes** — the
   default AgX will visibly shift brand colours. `'AgX'` only for 3D scenes intended to
   be photographic.
4. For `kind='2d'`, pin `scene.eevee.use_fast_gi = False`, `use_raytracing = False`,
   `indirect_light_intensity = 0.0` explicitly — `bpy.ops.scene.new(type='EMPTY')` copies
   settings from the active scene, not factory defaults, so a prior scene's GI settings
   otherwise leak in. Without this, an emissive flat-shaded plane can self-illuminate
   bounce toward washed-out colours (a pure-red test card rendering as `(255, 66, 77)`).
5. Tag `cmt_id` / `cmt_origin` / `cmt_rev`.
6. Be idempotent by `cmt_id`: if a scene with that id exists, return it rather than
   creating a duplicate.
7. For `kind='2d'`, call `add_camera(scn)`: an `ORTHO` camera, `sensor_fit='VERTICAL'`,
   `ortho_scale=const.FRAME_HEIGHT` (2.0 units) — the unit convention every `kind='2d'`
   shot builds against (`text.create(size=1.0)`, `fx.vignette()`'s frame-covering plane).
   Frame height stays fixed across landscape/portrait `resolution`; only width varies with
   aspect. `kind='3d'` scenes get no camera and no unit convention — set one up per-shot.
   `add_camera()` stays independently callable with a different `height`/`distance` for a
   shot that wants different framing (e.g. a zoom).

### 6.2 `anim.py`/`gn.py` — non-baked and tunable, by keyframe or by node graph

The hard rule is not "must literally be an F-curve" — it's **non-baked**: an effect must
stay expressed as a real, inspectable, tunable parameter (a keyframe, a driver formula, or
a GN modifier input), never as a baked/pre-sampled result that can only be regenerated, not
adjusted, by a user, an agent in a later turn, or automatically in response to another
object. Keyframes are the default expression of that for discrete, narrative-timed events —
they stay editable in the dope sheet and graph editor. `drive()` is the sanctioned exception
for continuous/procedural effects a human will retune by editing a formula rather than
dragging keyframes (an idle wobble, a decay curve). `anim.py` records every driver it
installs through `journal.record_driver()`, same as keyframe writes go through
`journal.set()`; anything that bypasses that (raw `bpy`) is still untracked drift with the
usual caveat (§4.4-4.5).

`gn.py` is a third expression of the same non-baked rule, for effects a per-object keyframe
sequence can't express cleanly — a per-character stagger being the motivating case (see
below). A GN modifier input is an ordinary Object RNA path
(`modifiers["Name"].properties.inputs.Socket_N.value` — Blender 5.2's post-idprop API; the
older `modifier["Socket_N"]` idprop form now raises `TypeError`), so `anim.tween()`/
`stagger()`/`drive()` already animate a GN input with **zero code changes**, and
`introspect.animated_paths()`/`provenance.claimed_paths()` already see a keyframed GN input
for free, the same as any other object property — confirmed live, not assumed. `gn.py`'s own
job is narrower: build the node graphs, and resolve a named input to that RNA path
(`gn.input_path()`, same "resolve the real identifier, don't hand-type it" precedent as
`text.color_path()`/`text.alpha_path()`).

`gn.char_reveal()` is the concrete case this rule was re-examined for: it reveals
String-to-Curves characters left-to-right from a **single** keyframed `Progress` input
(0-1) — each character's delay is computed from its instance `Index` *inside the node
tree* (`index * Spacing`, mapped through a `Window`), not from N per-character keyframes.
Zero per-instance keyframes, fully non-destructive, and the whole stagger is retuned by
changing one or two modifier inputs rather than touching individual objects — a compliant,
arguably purer expression of "non-baked and tunable" than per-character F-curves would be,
not a workaround. `docs/M3-FINDINGS.md` Check 1 rejected a per-instance-keyframed GN
approach for exactly this case; that rejection still holds (GN instances genuinely aren't
independently keyframeable), it just wasn't the only way to drive per-character timing from
GN. `text.split_chars()`/`split_spans()` remain the right tool when characters need
independently ownable/positionable *Objects* (e.g. per-character material overrides beyond
what a `Set Material Index` node can express) — `gn.char_reveal()` is for a uniform
timing/reveal effect across a string, not independent per-character control.

```python
anim.tween(obj, "location", index=1, frm=-0.4, to=0.0,
           start=12, dur=20, ease="BACK_OUT")
anim.stagger(objs, "location", index=1, offset=2, **tween_kwargs)
anim.idle_jitter(obj, "rotation_euler", 2, amplitude=0.02, cycles=3, start=1, dur=60)
anim.drive(obj, "rotation_euler", 2, "sin(frame*0.2)*0.02")
anim.drive_tween(obj, "location", index=1, frm=-0.4, to=0.0,
                  start=12, dur=20, ease="power2.out")
```

`drive_tween` is `tween`'s formula-driven twin: one driver expression easing between
`frm`/`to` over `[start, start+dur]`, clamped outside that range, instead of two
keyframes — often simpler for the agent to emit directly, not just easier for a human to
retune afterward. `ease` reuses `tween`'s GSAP-style names, but only `power1`-`power4`,
`sine` and `linear` have a closed form as a plain expression; `elastic`/`back`/`bounce`/
`circ`/`expo` don't (they're piecewise/recursive) and `drive_tween` raises for those —
use `tween` when the shape needs one of them.

`idle_jitter` is a pre-sampled tween, not a generic curve sampler: it bakes a base
keyframe, a peak/trough pair per cycle, and a closing base keyframe around the
path's current value — real F-curves, same as `tween`, just more of them. `drive()`
skips the sampling step entirely: the expression itself is what a human tunes.

Provenance stays whole-datablock for both: a human editing a driver's expression flips
the object's `cmt_origin` to `shared` the same way a moved keyframe or a hand-edited
value does (§4.3's `depsgraph_update_post` handler doesn't distinguish which kind of
edit it saw). `provenance.claimed_paths()`'s finer-grained value diff excludes
driver-governed paths the same way it already excludes animated ones — a driver's
live-evaluated value can't be diffed against a single "last written" value either.

Easing map (from the discussion — the sets are near-identical by design):

| GSAP | Blender `interpolation` | Blender `easing` |
|---|---|---|
| `power1` | `QUAD` | |
| `power2` | `CUBIC` | |
| `power3` | `QUART` | |
| `power4` | `QUINT` | |
| `sine` / `expo` / `circ` | `SINE` / `EXPO` / `CIRC` | |
| `back` / `elastic` / `bounce` | `BACK` / `ELASTIC` / `BOUNCE` | |
| `.in` / `.out` / `.inOut` | | `EASE_IN` / `EASE_OUT` / `EASE_IN_OUT` |
| `cubic-bezier(...)` / `CustomEase` | `BEZIER` | (computed handles) |

Reusable motion should become **Actions instanced via NLA strips with a time offset**,
not re-emitted keyframes. Far more reviewable, and it is the Blender-native equivalent
of a component with baked-in animation.

### 6.3 `introspect.py` — progressive disclosure, never dumps

One Geometry Nodes tree dumped naively will exceed the whole spec in tokens.

- `outline(scene, depth=1)` → shallow tree: collections, object names, types, counts.
  Hard cap on lines; truncate with `… +N more`.
- `describe(datapath, depth=1)` → drill down to one node.
- `animated_paths(scene)` → which RNA paths carry F-curves, key counts, frame ranges. Already
  covers a keyframed GN modifier input — no GN-specific code needed, see §6.2.
- `gn_inputs(obj)` → named inputs (identifier + current value) of every Geometry Nodes
  modifier on `obj`, so `gn.input_path()` doesn't have to be resolved by trial and error.
- `find(type=, name~=, tag=)` → targeted lookup.
- `drift()` → untracked changes vs `.comonteur/snapshot.json`.

Every function takes and enforces a token budget.

### 6.4 `preview.py` — review is visual

For G2, the agent reviews by **looking**, not by reading data.

`preview.frames(scene, frames=[start, mid, end], pct=25, engine="WORKBENCH")` →
image paths returned to the agent for multimodal inspection.

Written to `.comonteur/review/frame-NN-at-<seconds>.png`, alongside a
`descriptions.md` in which **the agent records what it saw**. Borrowed from
HyperFrames' `snapshots/` convention: writing the observation down, rather than only
looking, makes review auditable after the fact and survives context loss.

"The headline crosses title-safe at frame 40" is real review. Structural inspection
happens afterward, scoped to the one thing being fixed.

### 6.5 `card.py` — image + border + shadow bundle

```python
card.create(scn, "shot/thumb.png", w=2.0, h=1.0,
            border_color=(1, 1, 1, 1), shadow=True)
```

Returns the root Empty the image/border/shadow planes are parented to, so one
`anim.tween(card, "location", ...)` moves the whole bundle. Border and shadow are
flat offset planes with Emission-only materials, not raytraced shadows — no light is
added, since `new_scene(kind='2d')` pins `use_raytracing = False` (§6.1) and a light
for one card would break that baseline for every other object in frame.

---

## 9. Components and the asset system

Blender's asset system is the component registry — do not build one.

Mark a Scene, node group, or Action as an asset; give it a catalog, description, tags and
a preview render. That is a self-describing, human-authored, thumbnailed component
library. The agent lists catalogs, reads descriptions, looks at previews, and picks.

5.2's **remote asset library hosting** means a brand kit can be a URL rather than a
vendored folder — worth designing for even if v1 ships local.

Parameter interface, once a component is chosen: custom properties on the Scene or a
`PARAMS` empty, with subtypes and UI limits. Notes:

- Numeric params propagate cleanly via **drivers**.
- **Strings are not drivable.** A handler must sync `scene["headline"]` into the text
  object's `data.body`.
- Geometry Nodes modifier inputs are the other good interface — typed, with UI. The
  **String to Curves** node gives per-character instances, which is how GSAP-style
  `SplitText` staggers are done natively (see `gn.char_reveal()`, §6.2).
  **5.2's modifier-input API is confirmed** (M0.3 resolved): read/write via
  `modifier.properties.inputs.Socket_N.value`, keyframe via
  `obj.keyframe_insert('modifiers["Name"].properties.inputs.Socket_N.value')` — the old
  idprop form (`modifier["Socket_N"]`) raises `TypeError` on 5.2. `gn.py` builds a node
  group's `Socket_N` sockets and marks the result `asset_mark()`ed, so a project's first
  call to `gn.char_reveal()` seeds its reusable-effect catalog for free — no separate
  starter-asset file to ship or maintain.
