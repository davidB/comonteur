# comonteur — Milestones

Part of the [comonteur spec](../SPEC.md). Section numbers match the original SPEC.md for
continuity with existing code comments (`SPEC.md §10...`). See `M0-FINDINGS.md` and
`M1-FINDINGS.md` in this directory for results.

---

## 10. Milestones

Ordering follows the production workflow: **scenes/frames first, assembly second.**

### M0 — API verification spike (do this first, half a day)

Do not write architecture against unverified 5.2 API. Each item is a scriptable check:

| # | Check |
|---|---|
| M0.1 | Do VSE strips accept custom properties, and do they survive save/load? |
| M0.2 | `bpy.ops.scene.new(type=…)` semantics — which variant gives a genuinely empty scene? |
| M0.3 | Geometry Nodes modifier property API shape in 5.2 (changed this release) |
| M0.4 | VSE strip API post `sequences`→`strips` rename: collection names, strip types, `transform`, text strip properties |
| M0.5 | `depsgraph_update_post`: are `updates` usable, is `upd.id.original` reliable, does it fire on selection-only changes, what is the cost? |
| M0.6 | Custom properties on Scene/Object survive **linking** (not just append) |
| M0.7 | **Can a linked Scene be used as a VSE Scene strip?** (highest-impact unknown) |
| M0.8 | `bpy.ops.ed.undo_push` called from a timer callback — does it behave? |
| M0.9 | Official MCP add-on: does `execute_python` run on the main thread? |
| M0.10 | `bpy.ops.render.opengl` in a running GUI session; how to get the image back to the agent |
| M0.11 | `blender --command extension install-file` — exact syntax and behaviour in 5.2 (needed for M5.5) |

Output: `docs/M0-FINDINGS.md`. If M0.7 fails, revise §5.1 before proceeding.

### M1 — Walking skeleton (validates the thesis)

The minimum that proves the whole design:

1. `journal` + `provenance` + batch protocol + flip handler.
2. `scene.new_scene()` with hard reset.
3. `introspect.outline` / `describe`, `preview.frames`.
4. Agent generates one text scene with a simple animated reveal.
5. **Human opens it in Blender and moves a keyframe in the dope sheet.**
6. Agent reviews visually, changes something *else*, and **does not clobber the human's
   edit** — the touched path shows as claimed, the flip is journalled, the undo stack is
   clean.

If step 6 works, everything above is buildable. If the provenance flip proves unreliable,
stop and revise §4.3 before building further.

Also in M1: **`comonteur doctor`**. Not user-facing polish — it is the debugging tool for the
risky milestones. Checks: Blender is exactly 5.2; official MCP addon and `comonteur` addon
both enabled; MCP socket reachable; `ffmpeg`/`ffprobe` on PATH; git-lfs initialized;
project layout valid; journal readable. Cheap to write, pays for itself immediately.

### M2 — Production contract
`narrative.yaml` + manifest ingest, ffprobe, TTS timing-mark captions, Whisper fallback.

Shipped as `cli/` — a Rust crate, ingest-only (`comonteur ingest {narrative,manifest,
captions}`), not the full M5.5 CLI shape. First outside-Blender code in the repo; see
§7.5/§8 for the language-policy decision this pulled forward. Whisper transcription
itself stays an external pipeline (§5.7) — `captions` ingest normalizes its
`transcript.json` output rather than invoking `whisper`.

### M3 — Scene authoring
`anim.py`, `text.py`, fit-to-box, per-character stagger via String to Curves, Actions/NLA,
asset-library component discovery, brand params.

### M4 — VSE assembly
`reconcile.py`, `timeline.yaml` → strips, scene strips from `compositions/frames/*`, audio,
transitions.

### M5 — Validation

Two acceptance cases, deliberately different:

**(a) `artifact-timeline-video`** — small, human-recorded VO, already has a hand-made
`vse.blend` to compare against. Exercises the anchor pipeline (§5.2) and the audio tasks
(§5.7). Do this one **first**: it is smaller and there is a known-good result to diff.

**(b) `cdviz-cloud-launch`** — 8 shots, screen-capture driven, BGM + SFX,
no voiceover. Run the §5.4 adapter over it, then rebuild the full deliverable (video,
title, description, thumbnail) in comonteur.

Measure: adapter fidelity (how much needed manual fixup, especially timing), effort vs.
the HyperFrames original, and — the one that actually matters — **how it feels to
hand-tune a shot** once it is in Blender.

### M5.5 — `comonteur setup` (before M6, not after)

Launching publicly means external users hit the three-step manual install (§7.4). Reduce
it to one command.

In scope:
- Install both Blender extensions — the Blender Lab MCP addon and the `comonteur` addon.
  **Done in bash already** (`skills/comonteur/templates/mise-tasks/comonteur/setup`): the MCP
  add-on via `extension repo-add` + `extension install --sync --enable`, comonteur via
  `extension build` + `extension install-file -r user_default -e`, both enabled with
  `bpy.ops.preferences.addon_enable` (there is no `--command` for enabling). The Rust
  `comonteur setup` inherits the same sequence; keep the copy-into-extensions-dir fallback
  for a machine with no `blender` on PATH.
- Register the MCP server: `claude mcp add`, or write a project-local `.mcp.json`.
- Install the Claude Code skill into `.claude/skills/`.
- Scaffold a new project (`comonteur init` — additive, never overwrites; §8.2).

**Partly shipped early, in the skill**: `setup`, `init` and `doctor` exist now as bash scripts
in `skills/comonteur/scripts/` (scaffold in `skills/comonteur/templates/`, symlinked as
`mise run comonteur:*` for contributors), because the workflows documentation needed something
real to point at and users must be able to start without cloning this repo (§8.2). M5.5
replaces them with Rust subcommands **under the same names**, and takes over the
release-asset-first delivery the scripts already assume.

Out of scope — **detect and report, never install**: Blender itself, `ffmpeg`, git-lfs.
Platform package managers own these; silently installing them is user-hostile.

Ends by running `doctor` and printing the result.

### M6 — Launch video
A product-launch video **about comonteur, made with comonteur**. Published to YouTube,
embedded in the README. Dogfooding as acceptance test.
