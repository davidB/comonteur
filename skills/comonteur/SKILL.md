---
name: comonteur
category: video-editing
description: >
  Build and edit video scenes, shots, animations and timelines inside Blender through the
  comonteur helper library, in a project that has `master.blend`, `timeline.toml` or
  `.comonteur/`, or starting one from scratch. Use for: scaffolding a new video project,
  creating or changing a shot (`compositions/frames/*.blend`),
  title cards and kinetic text, keyframes and GSAP-named eases, staggered reveals,
  linking components from `lib/*.blend`, rendering review frames, assembling the VSE
  timeline from `timeline.toml`, and importing an existing HyperFrames project. Read this
  before writing any `bpy` code against such a project — raw `bpy` bypasses the ownership
  and journal system that lets a human edit the same `.blend` at the same time.
tags: ["blender", "vse", "video", "animation", "montage"]
---

# comonteur — start here

A human edits this `.blend` live, at the same time as you. Everything below exists to keep
that safe. The scene is the source of truth. You mutate it. You never regenerate it.

Reach Blender through the official Blender MCP server's `execute_python` only. There is no
comonteur MCP tool — the library is the typed surface.

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

The batch is not optional. `journal.set()` and `anim.tween()` raise outside one (`journal.py:86`,
`anim.py:82`). The batch writes the journal entries, bumps `cmt_rev`, gates the human-edit
detector so your own writes aren't misread as theirs, and produces one labelled undo step.

Label batches for a human reading an undo menu: `"shot-03: title fade-up"`, not `"batch 1"`.

## Hard rules

Break one of these and you corrupt the project silently.

- **Never save the `.blend`.** No `bpy.ops.wm.save_mainfile()`. Saving is the human's call —
  saving under them can destroy work you can't see.
- **Never regenerate.** Mutate existing data, never delete-and-recreate it.
  `scene.new_scene()` returns the existing scene when `cmt_id` already exists (`scene.py:20`)
  — that's deliberate, don't route around it. Delete-and-recreate throws away every human
  edit and breaks the journal's history.
- **Untagged data is human data.** No `cmt_origin` means a human made it. Don't touch it
  unless the current instruction names it. Check `cmt.provenance.origin(id_block)` before
  touching anything you didn't create this session.
- **`shared` means the human touched it.** `cmt.provenance.claimed_paths(id_block)` returns
  every path a human has claimed since — anything whose live value no longer matches what you
  last wrote there. Those paths are lost to you: mutate anything else, and never delete a
  `shared` datablock. (Mechanism and limits: `references/api.md`.)
- **Prefer `cmt.*` over raw `bpy`.** Raw `bpy` isn't forbidden, but it's untracked — it never
  hits the journal, `revert` can't undo it, the human's ownership view won't show it. If you
  must, keep it to reads, or route the write through `cmt.journal.set(obj, "path", value)`.
- **Prefer `mise run comonteur:<task>` over raw shell**, in a project that has them (check
  `mise tasks`). A task is what the human can re-run and what pins the tools — a command in a
  chat log is neither. Add a task instead of improvising a repeat. Ask permission, then run it
  yourself — don't tell the human to open a terminal.
- **`batch()` does not nest** (`journal.py:61`). One batch per logical unit of work. Not one
  per write, not one for the whole session.

## The loop

This is the loop for one shot. For work around it — starting a project, ingest, assembly,
delivery — read `references/workflows.md` first.

1. **Read the intent.** `narrative.toml` (and `STORYBOARD.md` if present) for what the shot
   says; `timeline.toml` for where it sits.
2. **Read the scene before writing to it.** `cmt.introspect.outline(scn)`,
   `describe(obj, "data")`, `animated_paths(scn)`. These are capped and truncated on purpose
   (`introspect.py:1`). Never dump `bpy.data` or walk a whole tree — that burns the context
   you need for the actual work.
3. **Build, in one batch.** See `references/api.md`.
4. **Look at it.** `cmt.preview.frames(scn, [1, 45, 90])` returns PNG paths under
   `.comonteur/review/`. Read those images.
5. **Adjust, re-preview, report, stop.** For a structural fix (wrong object, wrong path,
   missing keyframe), re-check with `introspect.animated_paths`/`describe` first — free, and
   catches the same mistakes a render would. Only call `preview.frames()` again once you've
   actually changed the scene, not to re-confirm what you already saw.

**Gate: never call a shot done without reading a rendered frame of it.** Blender fails
silently and visually — text off-canvas, a missing material, an F-curve on the wrong array
index. Code that ran without error proves nothing here.

**Tell the human to save when you finish.** You can't, and their Blender session holds your
work in memory only.

**Hit a real gap or bug in comonteur itself** — a missing helper, a wrong doc, a broken mise
task — tell the human and offer to draft a GitHub issue at
`https://github.com/davidB/comonteur/issues`. Propose it, don't file it yourself.

## Routing

| Read | When |
|---|---|
| `references/workflows.md` | Starting a project, or deciding which workflow a directory is: order of work, ingest, rendering, delivery. Also covers delegating shots to a subagent when building more than a couple in one session. |
| `references/api.md` | Writing any scene content: scenes, text, animation, eases, components, preview, provenance. |
| `references/timeline.md` | Assembling or changing the edit: `timeline.toml`, anchors, `reconcile`, VSE strips, audio, transitions. |
| `references/hyperframes-import.md` | Converting an existing HyperFrames project into a comonteur project. |
| `references/troubleshooting.md` | A previously-working project shows broken/missing data after reopening a `.blend` — fonts, links, or other external references. |

Read the matching reference before the first call in that area — these are command
contracts, not background reading. Don't read them all speculatively.

## Ownership, in eight lines

Every datablock you create carries `cmt_id` (stable id), `cmt_origin`, `cmt_rev` (bumped per
batch). A text object bound with `scene.bind_param()` also carries `cmt_param`.

| `cmt_origin` | You may |
|---|---|
| `agent` | mutate and delete freely |
| `shared` | mutate paths not in `claimed_paths()`; never delete |
| `human` | mutate only when the current instruction names it; never delete |
| *(absent)* | treat as `human` |

The flip from `agent` to `shared` is automatic — a `depsgraph_update_post` handler catches
human edits to your data (`provenance.py:36`). The human can override either way from the
comonteur sidebar panel (*Take ownership* / *Return to agent*), acting on the active object —
scenes and actions only ever flip automatically.

When a human has claimed a property you wanted to change, route around it and say so in your
report. Don't overwrite it back, don't ask them to undo their edit.
