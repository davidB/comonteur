# M3 — Scene authoring: findings

Blender **5.2.0 LTS** (build 2026-07-15), Linux. Two unknowns not covered by M0, checked
via a headless spike (`blender -b -P`) before writing `anim.py`/`text.py`/`library.py`.

## Check 1 — String to Curves GN construction, per-character stagger

**Node exists and is scriptable headless.** `bpy.data.node_groups.new(..., "GeometryNodeTree")`
+ `nodes.new("GeometryNodeStringToCurves")` works from a plain `-b` script, no GUI needed.
Its `outputs` are `Curve Instances` / `Remainder` / `Line` / `Word` / `Pivot Point`;
inputs include `String`, `Size`, `Font`, `Align X/Y`, `Character Spacing`,
`Text Box Width/Height`. `evaluated_get(depsgraph).to_mesh()` on the host object returns
0 vertices — the output is curve instances, not mesh geometry, so `to_mesh()` is the
wrong read path (would need `to_curve()` or a Mesh to Curve conversion node upstream of
realize, and even then the result is **one object with N splines**, not N separately
transformable objects).

**Consequence — split_chars() does not use GN.** Real per-character *keyframeable*
stagger needs N independent Objects (§6.2's "real F-curves, non-negotiable" — GN
instances aren't keyframeable per-instance without drivers/fields, which is exactly the
"no drivers-as-animation" rule GN would otherwise tempt). `text.split_chars()` instead
creates one `FONT` object per character directly via the data API (each object's
`data.body` is a single character), positioned left-to-right using each character's
measured `dimensions` (advance width) after a `view_layer.update()` — same fit-to-box
measurement technique as §11's "no layout engine" rule, just applied per glyph. This is
simpler than wiring GN and satisfies the F-curve mandate directly; String to Curves
stays available for future *procedural* (non-keyframed) text effects but is not on
`text.py`'s critical path.

**Amendment (post-M3):** the rejection above is about *per-instance* keyframing
specifically — still correct, GN instances aren't independently keyframeable. It is not a
rejection of GN for per-character *timing* in general: `gn.char_reveal()` (docs/library.md
§6.2) drives a per-character stagger from **one** keyframed `Progress` modifier input, with
each character's delay computed from its instance `Index` inside the node tree instead of
from a per-instance keyframe. Confirmed working live (build, keyframe, save/reload,
`introspect`/`provenance` visibility) before that module was written. `split_chars()` is
still the right tool when characters need independent Objects; `gn.char_reveal()` is for a
uniform timing effect across a string.

## Check 2 — Asset catalog discovery, headless

**Scriptable headless via `assets_only`.** `bpy.data.libraries.load()` takes an
`assets_only: bool` param (confirmed via `help()`, not in the SPEC docs) — "If True, only
list data-blocks marked as assets." Listing (without `link=True`) gives datablock names;
appending/linking with `assets_only=True, link=True` gives real datablocks whose
`.asset_data.description` / `.asset_data.tags` / `.asset_data.catalog_id` are readable
without any window or Asset Browser UI open. `bpy.context.window` is also non-`None` even
under `-b` in this Blender build (a headless dummy window context) — not verified further
here since preview/render context handling was already settled in M0.9/M0.10.

**Consequence — `library.py.discover()` is real, not best-effort.** It can enumerate
assets in `lib/*.blend` by linking with `assets_only=True` and reading `.asset_data`
directly; no GUI-only fallback needed. Catalog *names* (vs. the UUID in `catalog_id`) live
in the library's `blender_assets.cats.txt` sidecar — resolving UUID→name is a small file
read, not part of the asset API; `discover()` does this lookup itself rather than
returning raw UUIDs to the agent.

## Check 3 (found live, not part of the pre-build spike) — Action API is layered in 5.2

Discovered while wiring `anim.tween()`: **`Action.fcurves` no longer exists.** 5.2's
layered-animation rework replaced it with `action.layers[].strips[].channelbags[].fcurves`
(a `ActionKeyframeStrip` per layer, one `channelbag` per action slot). Walking that
structure to find "the fcurve for this object's `location[1]`" would be exactly the kind
of API-version-fragile code `docs/M0-FINDINGS.md` warns about.

**Fix — use the documented accessor instead of walking the structure:**
`action.fcurve_ensure_for_datablock(datablock, data_path, index=0, group_name="")`
creates the layer/strip/slot as needed and returns the fcurve directly. `anim.py` uses
this exclusively; nothing in the addon reads `action.layers` directly.

## Consequences for later code

- `text.split_chars()`: per-character real Objects, not a GN node tree.
- `library.py`: `bpy.data.libraries.load(path, link=True, assets_only=True)`, then read
  `.asset_data` on each returned datablock; resolve `catalog_id` against
  `blender_assets.cats.txt` next to the library file.
- GN modifier-input API (M0.3's `mod.properties.inputs.<id>.value` form) still applies if
  `anim.py`/`library.py` ever drive numeric component params through a modifier — not
  needed for the String to Curves path since that path was dropped per Check 1.
- `anim.py`: always go through `action.fcurve_ensure_for_datablock(...)`, never
  `action.fcurves` directly (removed in 5.2's layered-Action model).
