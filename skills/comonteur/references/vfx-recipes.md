# VFX recipes — named look → which calls to combine

A named "look" (from a storyboard, a brief, or a HyperFrames import) is almost always a
combination of a few `cmt.*` primitives, not a missing feature. Check here before reaching
for a new node group or a custom evaluator — `references/api.md` documents the primitives
themselves; this file documents the combinations.

## Spring-pop entrance

An element overshoots then settles (a wordmark, a CTA card).

```python
cmt.anim.tween(wordmark, "scale", None, frm=0.0, to=1.0, start=start, dur=dur, ease="back.out")
```

`back`/`elastic` are real Blender F-curve interpolation types (`_INTERPOLATION` in `anim.py`)
— an editable Bezier-equivalent keyframe, not a custom evaluator. `back.out(1.6)`-style tuned
overshoot amounts from a GSAP source don't carry over numerically; retime by eye instead.

## Underline / progress-bar draw (a growing bar from one fixed edge)

```python
line = card._plane(scn, "underline", w, h)   # or any _plane()-based quad
card.reorigin_left(line)
cmt.anim.tween(line, "scale", 0, frm=0.0, to=1.0, start=start, dur=dur, ease="power2.out")
```

`reorigin_left()` shifts a plane's mesh so local X spans `0..w` instead of `-w/2..w/2` —
world position unchanged — so a `scale.x` tween from 0 grows the plane from its left edge
instead of from its center. Same recipe for a caption-card progress bar, a rule/divider
draw-on, or any "line grows from a fixed point" look — including an SVG
`stroke-dashoffset`-style draw on a *straight* line from a GSAP/HyperFrames source; those are
visually identical to this.

## Card tilt (a 3D `rotateY`/`rotateX` look, e.g. "split-tilt-cards")

```python
cmt.anim.tween(card_root, "rotation_euler", 1, frm=..., to=..., start=start, dur=dur, ease="power3.out")
```

Ordinary object rotation — no new primitive. To match a CSS `perspective: ...` reference's
convergence, build the shot as a `kind="3d"` scene with its own perspective camera
(`new_scene(kind="2d")`'s camera is orthographic and has no such convergence — see
`references/api.md`'s `cmt.scene` section). Orthographic rotation still reads as a tilt (the
silhouette foreshortens), just without the vanishing-point depth cue.

## Scale-swap transition (handoff between two elements at the same anchor)

```python
cmt.anim.tween(outgoing, "scale", None, frm=1.0, to=0.7, start=t, dur=0.35, ease="power2.in")
cmt.anim.tween(cmt.text.color_target(outgoing), cmt.text.alpha_path(outgoing), None,
                frm=1.0, to=0.0, start=t, dur=0.35, ease="power2.in")
cmt.anim.tween(incoming, "scale", None, frm=0.7, to=1.0, start=t+0.15, dur=0.5, ease="back.out")
cmt.anim.tween(cmt.text.color_target(incoming), cmt.text.alpha_path(incoming), None,
                frm=0.0, to=1.0, start=t+0.15, dur=0.5, ease="back.out")
```

Two independent tweens (scale + opacity) on the outgoing and incoming elements, overlapping
by a small offset — no new primitive. `color_target()`/`alpha_path()` work on any
`style()`-built material (text or a `card._plane()`-based object), despite living in
`cmt.text` — the material shape (Principled BSDF Base/Emission Color + Alpha) is the same.

## Typewriter reveal (character-by-character typing + blinking cursor)

```python
ng = cmt.gn.typewriter()
mod = cmt.gn.apply(caption, ng)
cmt.introspect.gn_inputs(caption)  # find String's Socket_N, set it inside a batch
cmt.anim.tween(caption, cmt.gn.input_path(mod, "Progress"), None,
                frm=0.0, to=1.0, start=start, dur=dur, ease="linear")
```

`String`, `Progress`, and the cursor's `CursorWidth`/`CursorHeight`/`CursorAdvance`/`BlinkHz`
are all ordinary modifier inputs — a human can retype the line or rescrub the timing directly
in Blender's Modifier panel, no agent call needed to change copy after the shot is built.
`CursorAdvance` (a per-character pitch in local units) tracks the reveal edge exactly for a
monospace font and approximately for a proportional one — Geometry Nodes has no font-metrics
query to do better.

## Shatter / fracture (per-face explode)

```python
ng = cmt.gn.fracture()
mod = cmt.gn.apply(mesh_obj, ng)
cmt.anim.tween(mesh_obj, cmt.gn.input_path(mod, "Progress"), None,
                frm=0.0, to=1.0, start=start, dur=dur, ease="power2.in")
```

`Distance`/`Scale`/`Seed` tune the explode radius, per-fragment gap, and random direction
seed. One keyframed `Progress` input, same shape as `char_reveal()`.

## Installing and reusing the GN asset library

`gn.char_reveal()`/`typewriter()`/`fracture()` only exist in whichever `.blend` calls them —
gone the moment a new project starts fresh. To make them a persistent, project-independent
catalog (browsable in Blender's Asset Browser, reusable from a *different* future project —
useful if you reuse effects/branding across videos):

```bash
mise run comonteur:init_gn_library   # add-only: creates lib/gn-vfx.blend, or leaves it alone
```

Then, from this project or any other:

```python
cmt.library.discover("lib/gn-vfx.blend", kinds=("node_groups",))          # list what's there
ng = cmt.library.link("lib/gn-vfx.blend", "node_groups", "CMT Char Reveal")
mod = cmt.gn.apply(title, ng)
```

A linked node group behaves identically under `gn.apply()`/`input_path()` — no special-casing
for linked vs. locally-built groups.
