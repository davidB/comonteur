# comonteur library — API and recipes

Every call below runs inside `with cmt.journal.batch("label"):` unless marked *read-only*.
Signatures in `addon/comonteur/` are the source of truth; if one disagrees with this file,
the source wins — say so, don't work around it.

## `cmt.scene` — the shot

```python
new_scene(name, *, kind="2d", fps=30, resolution=(1920, 1080),
          frame_range=(1, 90), transparent=True, view_transform=None) -> Scene
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
`view_transform="Standard"` (colours come out as authored); anything else gets `AgX`.
`transparent=True` by default, since shots composite in the VSE.

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
create(scene, body, *, name=None, size=1.0, font=None, color=None) -> Object
style(obj, *, size=None, font=None, color=None) -> Object
fit_to_box(obj, width, height, *, min_size=0.01, step=0.9) -> Object
split_chars(obj, *, spacing=0.0, space_width_factor=0.3) -> list[Object]
```

`color` is RGB or RGBA floats. `style()` creates a Principled BSDF material named
`<obj>.color` on first use and writes `Base Color`.

`fit_to_box()` is a measure-and-shrink loop, not a layout engine: it multiplies `data.size` by
`step` until the object fits, forcing a depsgraph update each pass. So call it before
animating, since it mutates `data.size` — and it only ever shrinks, never grows.

`split_chars()` replaces `obj` with one FONT object per character, named `<base>.0`,
`<base>.1`, … positioned left to right by each glyph's measured advance width. The original
object is removed — keep the returned list, not the original reference. Space glyphs measure
zero width and fall back to `size * space_width_factor`; raise that factor if spacing looks
tight. Reason it exists: Geometry Nodes *String to Curves* yields one multi-spline object
whose instances can't be keyframed independently — real per-character animation needs real
per-character objects.

## `cmt.anim` — motion

```python
tween(obj, path, index, frm, to, start, dur, ease=None)
stagger(objs, path, index, offset, **tween_kwargs)   # tween_kwargs must include start=
instance_as_nla(obj, track_name, frame_offset) -> NlaStrip
```

`tween()` writes two real keyframes — `frm` at `start`, `to` at `start + dur` — both editable
by the human in the Graph Editor. Frames, not seconds. `index` is the array index:
`location` X/Y/Z = 0/1/2, `rotation_euler` and `scale` likewise. For a scalar property with no
components (e.g. `empty_display_size`), pass `index=None` — the journal then records the bare
path, the same string a human edit would touch.

No baked transforms, no drivers-as-animation, no custom evaluator. If motion can't be
expressed as keyframes, it doesn't belong in comonteur.

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
  `lib/brand.blend`, `lib/titles.blend`.
- `link_scene()` is not — for agent-generated shot scenes in `compositions/frames/*.blend`,
  which are plain scenes, never asset-marked (`library.py:83`).

Both link, never append, so the data stays read-only where used. Both tag provenance only if
the datablock isn't tagged already — a human's component keeps its `human` origin across the
link.

## `cmt.introspect` — read before you write *(read-only)*

```python
outline(scene, max_lines=60) -> str
describe(id_block, path="", max_lines=40) -> str
animated_paths(scene, max_lines=60) -> list[dict]
```

`outline()` gives collections and objects with their origin tag — start here.
`describe(obj, "data")` walks a dotted path and lists attribute names, capped.
`animated_paths()` returns `{object, data_path, index, keys, frame_range}` per F-curve — how
you find what's already animated before adding to it. When the cap bites it appends a final
`{"truncated": N}` entry — check for that before assuming you've seen the whole scene; raise
`max_lines` or narrow the scene if you need the rest.

All three are capped and truncated on purpose. `drift()` and `find()` don't exist yet — don't
call them.

## `cmt.preview` — look at your work *(read-only, but see below)*

```python
frames(scene, frame_numbers, engine="WORKBENCH") -> list[str]
```

Renders OpenGL stills to `.comonteur/review/frame-<NNN>-at-<S.SS>.png` (frame number and
seconds, matching HyperFrames' snapshot convention) and returns the paths. Read the images.

It swaps the window's active scene, render engine, output filepath, and current frame,
restoring all four in a `finally` — a preview never redirects the human's next render.
`WORKBENCH` is fast and correct for layout, spacing, timing; pass `engine="BLENDER_EEVEE"`
only when materials or lighting are the actual question. (5.2 names it `BLENDER_EEVEE`, not
`BLENDER_EEVEE_NEXT`; valid set is `BLENDER_EEVEE`, `BLENDER_WORKBENCH`, `CYCLES`.)

Preview at least three frames of a shot — start, middle, end. One frame can't show motion.

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
