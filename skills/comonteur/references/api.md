# comonteur library — API and recipes

Every call below runs inside `with cmt.journal.batch("label"):` unless marked *read-only*.
Signatures are the source of truth in `addon/comonteur/`; if one disagrees with this file,
the source wins — say so rather than working around it.

## `cmt.scene` — the shot

```python
new_scene(name, *, kind="2d", fps=30, resolution=(1920, 1080),
          frame_range=(1, 90), transparent=True, view_transform=None) -> Scene
find(cmt_id) -> Scene | None                                    # read-only
set_param(scn, name, value, *, min=None, max=None, subtype=None)
bind_param(obj, name)
```

`new_scene()` is **idempotent on `cmt_id`** — it returns the existing scene untouched if
one is already tagged with that name. Call it freely; never delete a scene to "start
clean".

It starts from `bpy.ops.scene.new(type="EMPTY")`, so nothing is inherited from whatever
scene the human was looking at, and it **switches the window's active scene**. `kind="2d"`
sets `view_transform="Standard"` (colours come out as authored); anything else gets `AgX`.
`transparent=True` is the default because shots are composited in the VSE.

Brand params (`set_param` / `bind_param`) are scene custom properties. Numeric ones
propagate through drivers; strings are not drivable, so `bind_param(text_obj, "headline")`
tags the object and a handler mirrors `scn["headline"]` into `obj.data.body`
(`scene.py:76`). Use `min`/`max`/`subtype` so the human gets a usable slider rather than a
raw float field.

```python
cmt.scene.set_param(scn, "accent", (0.1, 0.6, 0.9, 1.0), subtype="COLOR")
cmt.scene.set_param(scn, "headline", "Ship faster")
cmt.scene.bind_param(title, "headline")   # human retypes it once, in the sidebar
```

## `cmt.text` — type

```python
create(scene, body, *, name=None, size=1.0, font=None, color=None) -> Object
style(obj, *, size=None, font=None, color=None) -> Object
fit_to_box(obj, width, height, *, min_size=0.01, step=0.9) -> Object
split_chars(obj, *, spacing=0.0, space_width_factor=0.3) -> list[Object]
```

`color` is RGB or RGBA floats; `style()` creates a Principled BSDF material named
`<obj>.color` on first use and writes `Base Color`.

`fit_to_box()` is a measure-and-shrink loop, not a layout engine (§11): it multiplies
`data.size` by `step` until the object's dimensions fit, forcing a depsgraph update each
pass. Consequences: **call it before animating**, because it mutates `data.size`; and it
only ever shrinks, never grows.

`split_chars()` **replaces** `obj` with one FONT object per character, named
`<base>.0`, `<base>.1`, …, positioned left to right by each glyph's measured advance
width. The original object is removed — keep the returned list, not the original
reference. Space glyphs measure zero width and fall back to `size * space_width_factor`;
raise that factor if the spacing looks tight. It exists because Geometry Nodes *String to
Curves* yields one multi-spline object whose instances are not independently keyframeable
(`docs/M3-FINDINGS.md` Check 1) and §6.2 requires real F-curves.

## `cmt.anim` — motion

```python
tween(obj, path, index, frm, to, start, dur, ease=None)
stagger(objs, path, index, offset, **tween_kwargs)   # tween_kwargs must include start=
instance_as_nla(obj, track_name, frame_offset) -> NlaStrip
```

`tween()` writes **two real keyframes** — `frm` at `start`, `to` at `start + dur` — both
editable by the human in the Graph Editor. Frames, not seconds. `index` is the array
index: `location` X/Y/Z = 0/1/2, `rotation_euler` likewise, `scale` likewise, and scalar
paths like `data.size` still take `index=0`.

No baked transforms, no drivers-as-animation, no custom evaluator. If a motion cannot be
expressed as keyframes, it does not belong in comonteur.

### Ease names (GSAP vocabulary)

`ease` is a GSAP name: a base name selects Blender's interpolation, the `.in` / `.out` /
`.inOut` suffix selects the easing direction (`anim.py:14-31`).

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

Fallbacks, all silent — check your spelling:

- unknown base name → `BEZIER`
- unknown or missing suffix → `EASE_IN_OUT`
- `ease=None`, `"cubic-bezier(...)"`, `"CustomEase"` → `BEZIER` / `EASE_IN_OUT`

`BEZIER` keyframes get `AUTO_CLAMPED` handles on both sides — a real editable Bezier the
human can drag, which is the whole point.

**`back.out` overshoot is the single loudest tell of agent-made motion**, and it is almost
never executed well. Reach for `power2.out` or `power3.out` for entrances by default. Use
`back`, `elastic` and `bounce` rarely, deliberately, and only when the piece is playful.

### Stagger

`stagger()` pops `start` from the kwargs and increments it by `offset` per object; every
other kwarg goes straight through to `tween()`.

```python
chars = cmt.text.split_chars(title)
cmt.anim.stagger(chars, "location", index=1, offset=2,
                 frm=-0.3, to=0.0, start=10, dur=14, ease="power2.out")
```

### Reuse motion as an NLA instance, not copied keyframes

`instance_as_nla()` pushes the object's current Action onto a new NLA track at
`frame_offset` and clears the active action. Reusable motion should be one Action
instanced N times (§6.2), not N copies of the same F-curves — the human edits it once.
Raises `ValueError` if the object has no action to instance.

## `cmt.library` — components from `lib/*.blend`

```python
discover(blend_path, kinds=("actions", "scenes", "node_groups")) -> list[dict]  # read-only
link(blend_path, kind, name) -> ID
link_scene(blend_path, scene_name) -> Scene
```

`discover()` returns `{kind, name, description, tags, catalog}` per asset, reading the
`blender_assets.cats.txt` sidecar for human-readable catalog names (falling back to the
raw UUID if it's missing). Run it before inventing a component — the human's `lib/` is
usually where the right one already lives.

Two link functions, and picking the wrong one fails:

- `link()` is `assets_only=True` — for **human-authored, asset-marked** components in
  `lib/brand.blend`, `lib/titles.blend`.
- `link_scene()` is not — for **agent-generated shot scenes** in
  `compositions/frames/*.blend`, which are plain scenes and never asset-marked
  (`library.py:83`).

Both link (never append), so the data stays read-only where it is used, and both tag
provenance only if the datablock isn't tagged already — a human's component keeps its
`human` origin across the link.

## `cmt.introspect` — read before you write *(read-only)*

```python
outline(scene, max_lines=60) -> str
describe(id_block, path="", max_lines=40) -> str
animated_paths(scene) -> list[dict]
```

`outline()` gives collections and objects with their origin tag — start here.
`describe(obj, "data")` walks a dotted path and lists that object's attribute names, capped.
`animated_paths()` returns `{object, data_path, index, keys, frame_range}` per F-curve —
this is how you find out what is already animated before adding to it.

All three are capped and truncated deliberately. `drift()` and `find()` appear in
`docs/library.md` but do **not** exist yet; do not call them.

## `cmt.preview` — look at your work *(read-only, but see below)*

```python
frames(scene, frame_numbers, engine="WORKBENCH") -> list[str]
```

Renders OpenGL stills to `.comonteur/review/frame-<NNN>-at-<S.SS>.png` (frame number and
seconds, matching HyperFrames' snapshot convention) and returns the paths. Read the images.

It temporarily swaps the window's active scene and the render engine, restoring both in a
`finally`. `WORKBENCH` is fast and correct for layout, spacing and timing; pass
`engine="BLENDER_EEVEE_NEXT"` only when materials or lighting are actually the question.

Preview at least three frames of a shot — start, middle, end. One frame cannot show motion.

## `cmt.journal` — the audit surface

```python
batch(label) -> contextmanager
set(id_block, path, value)
paths_written_by_agent(id_block) -> set[str]        # read-only
last_agent_value(id_block, path)                    # read-only
```

`set()` is the escape hatch for any property the typed helpers don't cover: it resolves the
dotted path, writes it, and records old and new values in `.comonteur/journal.jsonl`.

```python
cmt.journal.set(obj, "data.extrude", 0.02)
cmt.journal.set(scn, "render.fps", 25)
```

Prefer it over a bare assignment for **every** write you want the human to be able to see,
diff and revert. A bare `obj.data.extrude = 0.02` works and is invisible.

## `cmt.provenance` — ownership

```python
tag(id_block, cmt_id, origin="agent", rev=1)
origin(id_block) -> str | None                      # read-only
is_agent_owned(id_block) -> bool                    # read-only
claimed_paths(id_block) -> set[str]                 # read-only
```

`scene.new_scene()`, `text.create()`, `library.link*()` tag for you. Call `tag()` yourself
only when you created a datablock through raw `bpy` and are bringing it into the system.

`claimed_paths()` is derived, not observed: for each path you wrote, it compares the live
value against what you last wrote there. A mismatch means the human changed it since.
Consult it before rewriting a property on a `shared` datablock, and report what you skipped.

## `cmt.reconcile` — assembly

See `references/timeline.md`. `diff()` is pure logic; `apply()` opens its own batch, so
call it **outside** one.
