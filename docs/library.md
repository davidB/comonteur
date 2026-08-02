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
| `scene.py` | `new_scene()` — see §6.1. Scene params interface. |
| `anim.py` | `tween`, `stagger`, `idle_jitter` (sine wobble, pre-sampled), easing map, F-curve helpers |
| `text.py` | text objects, styling, fit-to-box, `measure` (world-space bounding box), per-character split. `style()`/`create()` color defaults to `shading='flat'` (Emission, since `kind='2d'` scenes have no lights) — pass `shading='lit'` for plain Base Color in lit 3D scenes. |
| `vse.py` | assembly, scene strips, transitions, audio |
| `library.py` | link `lib/*.blend` (component library) and `compositions/frames/*.blend` (per-shot scenes), asset catalog discovery |
| `card.py` | `create()` — image plane + hairline border + soft shadow bundle, the HyperFrames "card" pattern |
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

### 6.2 `anim.py` — real F-curves preferred

The agent's animation output should be editable in the dope sheet and graph editor,
so real keyframes on real data paths are the preferred path — not drivers-as-animation
or baked transforms. `anim.py` only ships keyframe tweens; a driver or baked bake via
raw `bpy` is a valid escape hatch when a tween can't express the motion, with the same
untracked/drift caveat as any other raw `bpy` write (§4.4-4.5).

```python
anim.tween(obj, "location", index=1, frm=-0.4, to=0.0,
           start=12, dur=20, ease="BACK_OUT")
anim.stagger(objs, "location", index=1, offset=2, **tween_kwargs)
anim.idle_jitter(obj, "rotation_euler", 2, amplitude=0.02, cycles=3, start=1, dur=60)
```

`idle_jitter` is a pre-sampled tween, not a generic curve sampler: it bakes a base
keyframe, a peak/trough pair per cycle, and a closing base keyframe around the
path's current value — real F-curves, same as `tween`, just more of them.

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
- `animated_paths(scene)` → which RNA paths carry F-curves, key counts, frame ranges.
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
  `SplitText` staggers are done natively.
  **⚠ The GN modifier property Python API changed in 5.2 — verify before building on it (M0.3).**
