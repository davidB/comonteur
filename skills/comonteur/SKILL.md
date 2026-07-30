---
name: comonteur
description: >
  Build and edit video scenes, shots, animations and timelines inside Blender through the
  comonteur helper library, in a project that has `master.blend`, `timeline.yaml` or
  `.comonteur/`, or starting one from scratch. Use for: scaffolding a new video project,
  creating or changing a shot (`compositions/frames/*.blend`),
  title cards and kinetic text, keyframes and GSAP-named eases, staggered reveals,
  linking components from `lib/*.blend`, rendering review frames, assembling the VSE
  timeline from `timeline.yaml`, and importing an existing HyperFrames project. Read this
  before writing any `bpy` code against such a project — raw `bpy` bypasses the ownership
  and journal system that lets a human edit the same `.blend` at the same time.
---

# comonteur — start here

A human is editing this `.blend` at the same time as you, live. Everything below exists to
make that safe. The scene is the source of truth; you never regenerate it, you only mutate
it.

You reach Blender through the official Blender MCP server's `execute_python` only. There is
no comonteur MCP tool — the library *is* the typed surface.

## The one code shape

Every piece of Python you send starts like this:

```python
try:
    from bl_ext.user_default import comonteur as cmt
except ImportError:  # dev checkouts that put addon/ on sys.path
    import comonteur as cmt

with cmt.journal.batch("shot-03: title fade-up"):
    scn = cmt.scene.new_scene("shot-03", fps=30, frame_range=(1, 90))
    title = cmt.text.create(scn, "Ship faster", size=0.8)
    cmt.anim.tween(title, "location", 1, frm=-0.4, to=0.0, start=1, dur=18, ease="power2.out")
```

The batch is not a convention you can skip. `journal.set()` and `anim.tween()` **raise**
outside one (`journal.py:86`, `anim.py:82`). The batch is what produces the journal entries,
bumps `cmt_rev`, gates the human-edit detector so your own writes aren't misread as theirs,
and emits exactly one labelled undo step the human can undo in one keystroke.

Label batches with what a human would want to see in an undo menu: `"shot-03: title
fade-up"`, not `"batch 1"`.

## Hard rules

Each of these is a silent-corruption bug, not a style preference.

- **Never save the `.blend`.** No `bpy.ops.wm.save_mainfile()`, ever. Saving is a human
  action; saving under them can destroy unsaved work you cannot see.
- **Never regenerate.** Your only operation on existing data is mutation.
  `scene.new_scene()` returns the existing scene when the `cmt_id` already exists
  (`scene.py:20`) — that is deliberate, don't work around it by deleting first.
  Delete-and-recreate throws away every human edit and breaks journal continuity.
- **Untagged data is human data.** Anything without `cmt_origin` was made by the human.
  Do not modify or delete it unless the current instruction names it. Check with
  `cmt.provenance.origin(id_block)` before touching anything you did not create in this
  session.
- **`shared` means the human has touched it.** You may mutate paths you have not lost —
  `cmt.provenance.claimed_paths(id_block)` returns the ones you have — and you may
  **never** delete it.
- **Prefer `cmt.*` over raw `bpy`.** Raw `bpy` is not forbidden and is sometimes the only
  way, but it is untracked: it never reaches the journal, `revert` cannot undo it, and the
  human's ownership view will not show it. If you must, keep it to reads, or do the write
  through `cmt.journal.set(obj, "path", value)` so it is recorded.
- **`batch()` does not nest** (`journal.py:61`). One batch per logical unit of work; not
  one per property write, not one for the whole session.

## The loop

This is the loop for **one shot**. For the work around it — starting a project, ingesting
upstream material, assembling, delivering — read `references/workflows.md` first.

1. **Read the intent** — `narrative.yaml` (and `STORYBOARD.md` if present) for what the
   shot says; `timeline.yaml` for where it sits.
2. **Read the scene before writing to it** — `cmt.introspect.outline(scn)`,
   `describe(obj, "data")`, `animated_paths(scn)`. These are capped and truncated on
   purpose (`introspect.py:1`). Never dump `bpy.data` or walk a whole tree; you will burn
   the context you need for the actual work.
3. **Build, in one batch.** See `references/api.md`.
4. **Look at it.** `cmt.preview.frames(scn, [1, 45, 90])` returns PNG paths under
   `.comonteur/review/`. Read those images.
5. **Adjust and re-preview**, then report what you did and stop.

**Gate: never say a shot is done without having read a rendered frame of it.** Blender
fails silently and visually — text off-canvas, a material that never got assigned, an
F-curve on the wrong array index. Code that ran without error proves nothing here.

**Tell the human to save** when you finish. You cannot, and their Blender session holds
your work in memory only.

## Routing

| Read | When |
|---|---|
| `references/workflows.md` | Starting a project, or deciding which workflow a directory is: project-level order of work, ingest, rendering and delivery. |
| `references/api.md` | Writing any scene content: scenes, text, animation, eases, components, preview, provenance. |
| `references/timeline.md` | Assembling or changing the edit: `timeline.yaml`, anchors, `reconcile`, VSE strips, audio, transitions. |
| `references/hyperframes-import.md` | Converting an existing HyperFrames project into a comonteur project. |

Read the matching reference before the first call in that area — these are command
contracts, not background reading. Do not read them all speculatively.

## Ownership, in eight lines

Every datablock you create carries `cmt_id` (stable logical id), `cmt_origin`, and
`cmt_rev` (bumped once per batch).

| `cmt_origin` | You may |
|---|---|
| `agent` | mutate and delete freely |
| `shared` | mutate paths not in `claimed_paths()`; **never** delete |
| `human` | mutate only when the current instruction names it; never delete |
| *(absent)* | treat as `human` |

The flip from `agent` to `shared` is automatic: a `depsgraph_update_post` handler catches
human edits to your data (`provenance.py:36`). The human can also override either way from
the comonteur sidebar panel in Blender (*Take ownership* / *Return to agent*).

When a human has claimed a property you wanted to change, **route around it and say so** in
your report. Do not overwrite it back, and do not ask them to undo their edit.
