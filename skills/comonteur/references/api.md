# comonteur library — API and recipes

Every call below runs inside `with cmt.journal.batch("label"):` unless marked *read-only*.
Signatures in `addon/comonteur/` are the source of truth; if one disagrees with this file,
the source wins — say so, don't work around it.

## `cmt.scene` — the shot

```python
new_scene(name, *, kind="2d", fps=30, resolution=(1920, 1080),
          frame_range=(1, 90), transparent=True, view_transform=None) -> Scene
add_camera(scn, *, height=const.FRAME_HEIGHT, distance=5.0) -> Camera
find(cmt_id) -> Scene | None                                    # read-only
set_param(scn, name, value, *, min=None, max=None, subtype=None)
bind_param(obj, name)
```

`new_scene()` is idempotent on `cmt_id` — returns the existing scene untouched if one's
already tagged with that name. Call it freely. Never delete a scene to "start clean".

On creation it starts from `bpy.ops.scene.new(type="EMPTY")` — nothing inherited from
whatever scene the human was looking at — and it switches the window's active scene. On the
idempotent path it returns early and leaves the window wherever the human had it, so don't
assume `bpy.context.scene` is your shot — pass the returned scene explicitly. `kind="2d"` sets
`view_transform="Standard"` (colours come out as authored) and pins EEVEE
`use_fast_gi`/`use_raytracing`/`indirect_light_intensity` off (no lights in a fresh scene, so
indirect GI just self-illuminates a flat-shaded plane); anything else gets `AgX` and default GI.
`transparent=True` by default, since shots composite in the VSE.

**Unit convention (`kind="2d"` only):** `new_scene(kind="2d")` also calls `add_camera()` for
you — an orthographic camera `sensor_fit="VERTICAL"` with `ortho_scale=const.FRAME_HEIGHT`
(2.0 Blender units). Frame height is always `FRAME_HEIGHT` units regardless of landscape or
portrait `resolution` — only width varies with aspect. Build shot content in these units
(`text.create(size=1.0)` is about half the frame height; `fx.vignette()` sizes itself off the
same constant). Call `add_camera()` again with a different `height`/`distance` if a shot needs
a different framing (e.g. a zoom). `kind="3d"` scenes get no camera and no unit convention —
set one up per-shot.

Brand params (`set_param` / `bind_param`) are scene custom properties. Numeric ones propagate
through drivers; strings don't drive, so `bind_param(text_obj, "headline")` tags the object
and a handler mirrors `scn["headline"]` into `obj.data.body` (`scene.py:76`). Set `min`/`max`/
`subtype` so the human gets a usable slider, not a raw float field.

```python
cmt.scene.set_param(scn, "accent", (0.1, 0.6, 0.9, 1.0), subtype="COLOR")
cmt.scene.set_param(scn, "headline", "Ship faster")
cmt.scene.bind_param(title, "headline")   # human retypes it once, in the sidebar
```

## `cmt.text` — type

```python
create(scene, body, *, name=None, size=1.0, font=None, color=None, shading="flat") -> Object
style(obj, *, size=None, font=None, color=None, shading="flat") -> Object
fit_to_box(obj, width, height, *, min_size=0.01, step=0.9) -> Object
split_chars(obj, *, spacing=0.0, space_width_factor=0.3) -> list[Object]
split_spans(obj, spans, *, spacing=0.0, space_width_factor=0.3) -> list[Object]
style_spans(chars, spans) -> list[Object]        # spans = [(start, end, style_kwargs), ...]
word_spans(body) -> list[tuple[int, int]]                       # read-only
measure(obj) -> dict
measure_many(objs) -> dict                                      # read-only
highlight_bg(scn, objs, color, *, padding=0.05, name=None) -> Object
color_target(obj) -> ShaderNodeTree                              # read-only
color_path(obj, shading="flat") -> str                            # read-only
karaoke(scn, obj, color, *, start, word_gap, dur, ease=None) -> list[Object]
check_fonts(scn) -> list[dict]                                  # read-only
```

`color` is RGB or RGBA floats. `style()` creates a Principled BSDF material named
`<obj>.color` on first use. `shading="flat"` (default) writes `Emission Color`/`Strength=1`
and zeroes `Base Color` — matches `kind="2d"` scenes, which have no lights. Pass
`shading="lit"` for plain `Base Color` in a lit 3D scene; re-styling flips both inputs, so
switching an object between the two is idempotent.

Fonts live in `lib/design.blend`, asset-marked, alongside brand colours and node groups —
never `bpy.data.fonts.load()` a `.ttf` straight from `assets/fonts/` into a shot. A path
loaded that way is only as good as the process's current working directory at load time; a
`lib/design.blend` link travels with the project instead. Load once and reuse the
`VectorFont` across every `create()`/`style()` call — `link()` makes a new datablock only
the first time, so guard repeats with `.get()`:

```python
vfont = bpy.data.fonts.get("Inter-Bold") or cmt.library.link("lib/design.blend", "fonts", "Inter-Bold")
cmt.text.create(scn, "Ship faster", font=vfont)
cmt.text.check_fonts(scn)   # [] once every FONT object has a real font
```

`check_fonts()` flags any FONT object still on Blender's built-in default ("Bfont Regular") —
a silently-substituted default is easy to miss in a low-res preview. Run it before calling a
shot done.

`fit_to_box()` is a measure-and-shrink loop, not a layout engine: it multiplies `data.size` by
`step` until the object fits, forcing a depsgraph update each pass. So call it before
animating, since it mutates `data.size` — and it only ever shrinks, never grows.

`split_chars()` replaces `obj` with one FONT object per character, named `<base>.0`,
`<base>.1`, … positioned left to right by each glyph's measured advance width. The original
object is removed — keep the returned list, not the original reference. Space glyphs measure
zero width and fall back to `size * space_width_factor`; raise that factor if spacing looks
tight. Reason it exists: Geometry Nodes *String to Curves* yields one multi-spline object
whose instances can't be keyframed independently, so *independent* per-character
animation/positioning needs real per-character objects. For a uniform reveal/stagger across a
whole string — most "letters fly in one after another" asks — prefer `cmt.gn.char_reveal()`
instead: one keyframed input, no per-character objects at all. Reach for `split_chars()` when
characters need independent control beyond timing (e.g. per-character material overrides).

`measure()` is a read-only bounding box in world space — `{"width", "height", "depth", "min",
"max"}`, `min`/`max` as `(x, y, z)` tuples. Use it to position an underline or accent against
real metrics (`min[0]`..`max[0]` at `y = min[1] - gap`) without splitting the object into
per-character pieces just to measure it.

### Multi-color / multi-style inline spans

Color and font live on individual objects (one material per `FONT` object), so styling part
of a string means splitting it first. Reach for `split_spans()` when you don't need
per-character objects — one object per span, not per glyph:

```python
words = cmt.text.word_spans(title.data.body)  # [(0, 5), (6, 11)]
cmt.text.split_spans(title, [
    (*words[0], {"color": (0.8, 0.8, 0.8, 1.0)}),
    (*words[1], {"color": (0.9, 0.4, 0.1, 1.0)}),
])
```

`word_spans(body)` gives whitespace-delimited `(start, end)` pairs; pass hand-picked indices
instead for spans finer than a whole word — a partial span list is fine, since any text your
spans don't cover (leading, trailing, or between spans) is kept as its own unstyled
pass-through object in the original base color/font. Only a pure-whitespace gap is collapsed
into spacing instead of becoming an object.

Only fall back to `split_chars()` + `style_spans()` when the granularity itself needs to be
per-character — real letter-level animation (typewriter reveal, per-letter stagger/tilt), not
just per-letter styling. `style_spans()` applies `style()` per index range over
`split_chars()`'s output — `chars[i]` is `body[i]`:

```python
chars = cmt.text.split_chars(title)
cmt.text.style_spans(chars, [(0, 3, {"color": (0.9, 0.2, 0.2, 1.0)}), (4, 9, {"font": vfont})])
```

`measure_many(objs)` unions `measure()`'s bbox across several objects — size a
highlight/background around a whole word, not one glyph:

```python
words = cmt.text.split_spans(title, cmt.text.word_spans(title.data.body))
bg = cmt.text.highlight_bg(scn, [words[0]], (1.0, 0.9, 0.2, 0.4))
```

Color lives on the object's material's node tree, which is its own ID-block — `keyframe_insert`
can't cross from the Object into it, so `tween()`/`stagger()` must target `color_target(obj)`
(the node tree), not `obj`, with the path from `color_path(obj)`:

```python
target = cmt.text.color_target(styled_obj)
cmt.anim.tween(target, cmt.text.color_path(styled_obj), 3, frm=0.0, to=1.0, start=1, dur=10)
```

`color_path(obj, shading="flat")` don't hand-type the node/input path — it must match
`style()`'s naming exactly, and Blender itself stores a node input's F-curve path by numeric
index, not name, so `color_path()` resolves that index for you. `index` picks the channel:
`0`/`1`/`2`/`3` = R/G/B/A.

`karaoke(scn, obj, color, *, start, word_gap, dur, ease=None)` bundles the whole word-by-word
highlight sweep — `word_spans()` + `split_spans()` + one `highlight_bg()` per word + a
`stagger()` on alpha — into one call:

```python
cmt.text.karaoke(scn, title, (1.0, 0.9, 0.2, 1.0), start=1, word_gap=6, dur=10, ease="power2.out")
```

Reach for this instead of hand-rolling per-word grouping — matching a GSAP `SplitText`
word-stagger's granularity is the point, not a whole-line fade or a per-letter ripple.

## `cmt.anim` — motion

```python
tween(obj, path, index, frm, to, start, dur, ease=None)
stagger(objs, path, index, offset, **tween_kwargs)   # tween_kwargs must include start=
idle_jitter(obj, path, index, amplitude, cycles, start, dur, ease=None)
pulse(obj, path, index, peak, start, dur, ease=None)
instance_as_nla(obj, track_name, frame_offset) -> NlaStrip
```

`tween()` writes two real keyframes — `frm` at `start`, `to` at `start + dur` — both editable
by the human in the Graph Editor. Frames, not seconds. `index` is the array index:
`location` X/Y/Z = 0/1/2, `rotation_euler` and `scale` likewise. For a scalar property with no
components (e.g. `empty_display_size`), pass `index=None` — the journal then records the bare
path, the same string a human edit would touch.

A `rotateY`-equivalent 3D tilt is just `tween()` on `rotation_euler` index `1`:

```python
cmt.anim.tween(obj, "rotation_euler", 1, frm=0.4, to=0.0, start=1, dur=12, ease="power2.out")
```

Prefer `tween`/`stagger`/`idle_jitter` over a raw-`bpy` driver or hand-baked keyframes: real
keyframes are journaled and land in the dope sheet/graph editor exactly where the human
expects to find and edit them. `idle_jitter()` covers the common "breathing hold" case — a
sine-like oscillation around the path's current value, baked as `2*cycles + 2` real
keyframes, no driver involved. If a motion still can't be expressed as a tween or a jitter, a
driver or hand-baked keyframes via raw `bpy` is a valid escape hatch — same untracked/drift
caveat as any other raw `bpy` write (`SKILL.md` Hard rules).

### Ease names (GSAP vocabulary)

`ease` is a GSAP name: a base name picks Blender's interpolation, the `.in` / `.out` /
`.inOut` suffix picks the direction (`anim.py:14-31`).

| `ease` base | Blender interpolation |
|---|---|
| `power1` | `QUAD` |
| `power2` | `CUBIC` |
| `power3` | `QUART` |
| `power4` | `QUINT` |
| `sine` | `SINE` |
| `expo` | `EXPO` |
| `circ` | `CIRC` |
| `back` | `BACK` |
| `elastic` | `ELASTIC` |
| `bounce` | `BOUNCE` |
| `linear` | `LINEAR` |

Suffix → `.in` = `EASE_IN`, `.out` = `EASE_OUT`, `.inOut` = `EASE_IN_OUT`.

Fallbacks, all silent — check spelling:

- unknown base name → `BEZIER`
- unknown or missing suffix → `EASE_IN_OUT`
- `ease=None`, `"cubic-bezier(...)"`, `"CustomEase"` → `BEZIER` / `EASE_IN_OUT`

`BEZIER` keyframes get `AUTO_CLAMPED` handles both sides — a real editable Bezier the human
can drag. That's the point.

**`back.out` overshoot is the loudest tell of agent-made motion**, and it's almost never
executed well. Default to `power2.out` or `power3.out` for entrances. Use `back`, `elastic`,
`bounce` rarely, deliberately, only when the piece is playful.

### Stagger

`stagger()` pops `start` from the kwargs and increments it by `offset` per object; every other
kwarg passes straight through to `tween()`.

```python
chars = cmt.text.split_chars(title)
cmt.anim.stagger(chars, "location", index=1, offset=2,
                 frm=-0.3, to=0.0, start=10, dur=14, ease="power2.out")
```

### Reuse motion as an NLA instance, not copied keyframes

`instance_as_nla()` pushes the object's current Action onto a new NLA track at
`frame_offset` and clears the active action. Reusable motion should be one Action instanced N
times, not N copies of the same F-curves — the human edits it once. Raises `ValueError` if
the object has no action to instance.

### Idle jitter (breathing holds)

```python
cmt.anim.idle_jitter(obj, "rotation_euler", 2, amplitude=0.02, cycles=3, start=1, dur=60)
```

Reads `path[index]`'s current value as the center, then bakes a base keyframe, a
peak/trough pair per cycle, and a closing base keyframe — `2*cycles + 2` real keyframes
total, same `_keyframe()`/easing machinery as `tween()`. Must run inside `journal.batch()`.

### Flash-pulse (one-shot)

```python
cmt.anim.pulse(obj, "data.materials[0].node_tree.nodes[\"Principled BSDF\"].inputs[\"Emission Strength\"].default_value", None, peak=3.0, start=1, dur=6)
```

`pulse()` is a single spike — base → `peak` at 30% of `dur` → back to base at `dur` — not a
repeating wobble. Use it for a flash/pop; use `idle_jitter()` for a sustained breathing hold.

## `cmt.gn` — Geometry Nodes effects (non-baked, tunable)

```python
char_reveal(name="CMT Char Reveal") -> NodeTree
apply(obj, node_group, name=None) -> Modifier
input_path(mod, socket_name) -> str
```

`char_reveal()` builds (once — idempotent by name) a reusable node group that reveals a
string's characters left to right from a **single** `Progress` input (0-1); each
character's delay comes from its instance index inside the node tree, not from a
per-character keyframe. Non-destructive and asset-marked, so it joins the project's
reusable-effect catalog (Blender's Asset Browser, "Current File") the first time it's built.
Use this — not `split_chars()` + `stagger()` — for a uniform reveal/wipe-in across a whole
string; see `cmt.text`'s `split_chars()` entry for when independent per-character objects
are still the right call.

```python
ng = cmt.gn.char_reveal()
mod = cmt.gn.apply(title, ng)
cmt.anim.tween(title, cmt.gn.input_path(mod, "Progress"), None,
                frm=0.0, to=1.0, start=1, dur=40, ease="power2.out")
```

`apply()` adds the node group as a `NODES` modifier and returns it. `input_path(mod,
"Progress")` resolves the socket's real `Socket_N` identifier to the RNA path
`anim.tween()`/`stagger()`/`drive()` need — **don't hand-type `Socket_N`**, it's
auto-generated and not stable across rebuilds. Set a non-animated input (e.g. `String`,
`Spacing`, `Window`) the same way any other object property is set inside a batch:

```python
cmt.introspect.gn_inputs(title)          # list current inputs by name, to find what to set
```

A GN modifier input is an ordinary object RNA path — `anim.tween()`/`stagger()`/`drive()`
animate it exactly like `location` or any other property, no special calls needed. Once
built, other effects (shapes, not just text) can reuse the same `apply()`/`input_path()`
pair with a different node group.

## `cmt.card` — image + border + shadow bundle

```python
create(scn, image_path, w, h, border_color=None, *,
       border_width=0.02, shadow=True, name=None) -> Object
```

Builds the common HyperFrames "card" pattern in one call: an image plane, an optional
hairline border plane, and an optional soft shadow plane, all parented to a returned root
Empty — `anim.tween(card, "location", ...)` on the root moves the whole bundle. Border and
shadow are flat offset planes with Emission-only materials, not raytraced shadows: `kind="2d"`
scenes have no lights (same reason `cmt.text` defaults to `shading="flat"`), and adding a
light for one card would break that baseline for every other object in frame. Pass
`border_color=None` (default) to skip the border; `shadow=False` to skip the shadow.

## `cmt.fx` — frame-level overlay effects

```python
vignette(scn, *, color=(0.0, 0.0, 0.0), strength=0.6, name=None) -> Object
```

A camera-facing plane whose alpha/emission falls off toward the edges via a radial gradient —
the darken-the-corners overlay a CSS/GSAP vignette usually is. `strength` is the alpha at the
frame edge; center stays fully transparent.

## `cmt.library` — components from `lib/*.blend`

```python
discover(blend_path, kinds=("actions", "scenes", "node_groups")) -> list[dict]  # read-only
link(blend_path, kind, name) -> ID
link_scene(blend_path, scene_name) -> Scene
```

`discover()` returns `{kind, name, description, tags, catalog}` per asset, reading the
`blender_assets.cats.txt` sidecar for human-readable catalog names (falls back to the raw UUID
if missing). Run it before inventing a component — the right one is usually already in the
human's `lib/`.

Two link functions, and picking the wrong one fails:

- `link()` is `assets_only=True` — for human-authored, asset-marked components in
  `lib/design.blend`, `lib/titles.blend`.
- `link_scene()` is not — for agent-generated shot scenes in `shots/*.blend`,
  which are plain scenes, never asset-marked (`library.py:83`).

Both link, never append, so the data stays read-only where used. Both tag provenance only if
the datablock isn't tagged already — a human's component keeps its `human` origin across the
link.

Brand values set once via `set_param()` on a `PARAMS` scene in `lib/design.blend` come back the
same way as any other custom property — `link()` returns the Scene, index it directly. Don't
re-hardcode brand hex/font values per shot; link and read:

```python
brand = cmt.library.link("lib/design.blend", "scenes", "PARAMS")
cmt.text.create(scn, "Ship faster", color=brand["ink_black"], font=vfont)
```

## `cmt.introspect` — read before you write *(read-only)*

```python
outline(scene, max_lines=60) -> str
describe(id_block, path="", max_lines=40) -> str
animated_paths(scene, max_lines=60) -> list[dict]
gn_inputs(obj, max_lines=60) -> list[dict]
```

`outline()` gives collections and objects with their origin tag — start here.
`describe(obj, "data")` walks a dotted path and lists attribute names, capped.
`animated_paths()` returns `{object, data_path, index, keys, frame_range}` per F-curve — how
you find what's already animated before adding to it. Already covers a keyframed Geometry
Nodes modifier input, same as any other object property — no separate GN call needed there.
`gn_inputs(obj)` returns `{modifier, name, identifier, value}` per named input across every
Geometry Nodes modifier on `obj` — use it to see current values before calling
`cmt.gn.input_path()`. When the cap bites it appends a final `{"truncated": N}` entry — check
for that before assuming you've seen the whole scene; raise `max_lines` or narrow the scene
if you need the rest.

All four are capped and truncated on purpose. `drift()` and `find()` don't exist yet — don't
call them.

## `cmt.preview` — look at your work *(read-only, but see below)*

```python
frames(scene, frame_numbers, engine=None) -> list[str]
```

Renders stills through the scene's own camera to `.comonteur/review/frame-<NNN>-at-<S.SS>.png`
(frame number and seconds, matching HyperFrames' snapshot convention) and returns the paths.
Read the images.

Works on any scene — the timeline scene, a human-owned scene, an agent-built shot — regardless
of which workspace or viewport the human currently has open: it renders by scene name into the
in-memory Render Result, not the ambient interactive viewport, so it needs no `VIEW_3D` area
and no camera-locked view. The only state it touches is the current frame, restored in a
`finally` — it never redirects the human's render output or switches the active window scene.
Leave `engine` unset to render with whatever the scene is already configured for; pass
`engine="BLENDER_EEVEE"` only when you need a specific one for this preview (materials,
lighting) without changing the scene's own setting. (5.2 names it `BLENDER_EEVEE`, not
`BLENDER_EEVEE_NEXT`; valid set is `BLENDER_EEVEE`, `BLENDER_WORKBENCH`, `CYCLES`.)

Preview at least three frames of a shot — start, middle, end. One frame can't show motion.
A re-preview confirms a fix you just made — not a habit. If nothing changed since the last
call, don't call it again.

## `cmt.journal` — the audit surface

```python
batch(label) -> contextmanager
set(id_block, path, value)
batch_active() -> bool                              # read-only
target_of(id_block) -> str                          # read-only — "Type:cmt_id", the journal key
paths_written_by_agent(id_block) -> set[str]        # read-only
last_agent_value(id_block, path)                    # read-only
created_by_agent(id_block) -> bool                  # read-only
```

`set()` is the escape hatch for any property the typed helpers don't cover: it resolves the
dotted path, writes it, records old and new values in `.comonteur/journal.jsonl`.

```python
cmt.journal.set(obj, "data.extrude", 0.02)
cmt.journal.set(scn, "render.fps", 25)
cmt.journal.set(obj, "modifiers[0].levels", 2)   # paths index too: a.b[1].c
```

Prefer it over a bare assignment for every write you want the human to see, diff, and revert.
A bare `obj.data.extrude = 0.02` works and is invisible.

`batch_active()` is how you check before calling something that raises outside a batch, rather
than opening a second one. `batch()` does not nest — see `../SKILL.md` Hard rules.

Constructors journal a `create` entry (what `created_by_agent()` reads), so a batch that only
creates is still recorded, still bumps `cmt_rev`, still leaves one undo step. The journal
lands in `.comonteur/` next to the `.blend` — in a session whose file was never saved it falls
back to Blender's working directory, so save first if you care where it lands.

## `cmt.provenance` — ownership

```python
tag(id_block, cmt_id, origin="agent", rev=1)
origin(id_block) -> str | None                      # read-only
is_agent_owned(id_block) -> bool                    # read-only
claimed_paths(id_block) -> set[str]                 # read-only
```

`scene.new_scene()`, `text.create()`, `library.link*()` tag for you. Call `tag()` yourself
only when you created a datablock through raw `bpy` and are bringing it into the system.

`claimed_paths()` returns what a human has claimed — see `../SKILL.md` Hard rules for the rule
itself. Mechanism: for each path you wrote, it compares the live value against what you last
wrote there; a mismatch means the human changed it since. Two limits worth knowing:

- **Animated paths are excluded.** An F-curve's live value depends on the playhead, so it
  carries no signal about who edited it. A human dragging your keyframes goes undetected — if
  a `shared` datablock's motion looks hand-tuned, ask before re-tweening it.
- **It only knows what went through the journal.** `text.style(color=...)` writes the
  material directly, so colour has no claim record — the material it creates is untagged,
  `origin(mat)` returns `None`, which the rules say to treat as the human's.

Datablocks carry `cmt_id` / `cmt_origin` / `cmt_rev`, plus `cmt_param` on a text object bound
with `scene.bind_param()`. The sidebar's *Take ownership* / *Return to agent* act on the
active object only — Scenes, Actions, and VSE strips have no override UI, so their ownership
only ever changes through the automatic flip.

## `cmt.reconcile` — assembly

See `references/timeline.md`.

```python
diff(desired, existing, claimed, fields) -> ReconcilePlan   # .to_create/.to_update/.to_delete
apply(resolved_plan, project_root)
```

`diff()` is pure logic — call it first for a dry run and report what would change before you
touch anything. `apply()` opens its own batch, so call it outside one.
