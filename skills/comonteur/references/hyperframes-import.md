# Importing a HyperFrames project

HyperFrames composes video by writing HTML/CSS/JS; comonteur composes it in Blender. The root
layouts are deliberately almost identical, so most of an import is copying. What's left is
genuinely lossy — HTML → timeline is not a lossless conversion, and this procedure must not
pretend otherwise.

Nothing about rendering crosses the line. You aren't transpiling GSAP into Blender; you're
recovering intent — what plays, when, for how long, in what style — and rebuilding it as
scenes and keyframes.

## Order of work

Do these in order. Stop at the first thing you can't resolve.

1. **Copy the identity-mapped tree.**
2. **Translate the metadata files** (table below).
3. **Recover the timing** and get it confirmed — this is the gate.
4. **Convert the fonts.**
5. **Rebuild each shot** as a Blender scene, one at a time, previewing each.
6. **Write `timeline.toml`** and reconcile into `master.blend`.

Steps 1–2 are mechanical — see "Delegate the mechanical pass" below. Step 3 is a gate that
needs judgment and human confirmation — keep it in the foreground.

## 1. Identity mapping

Carried over unchanged: `assets/**`, `capture/`, `renders/`, `thumbnail/`, root `meta.json`,
`CLAUDE.md` / `AGENTS.md`, `frame.md`.

`CLAUDE.md` / `AGENTS.md` stay exactly as they are. comonteur ships its contract in this skill
and never writes or edits a project's agent-instruction files.

`compositions/frames/NN-slug.html` → `compositions/frames/NN-slug.blend`, same path, one
Blender scene each, `cmt_id = NN-slug`.

Two exclusions:

- **Never copy `renders/work-*/`.** Ephemeral scratch — worker dirs, retry attempts, a
  symlink into `/tmp`. Never copy it, never archive it.
- **Gitignore `renders/BL_proxy/`** if the project has one (VSE proxies, regenerable).

Assets are duplicated between `assets/` (curated) and `capture/assets/` (full scrape), names
truncated to ~40 chars. Dedupe by sha256 content hash, keep the curated name, carry the
human-readable description from `capture/extracted/asset-descriptions.md` into the manifest's
`description` field.

## 2. Translated files

| HyperFrames | comonteur |
|---|---|
| `STORYBOARD.md` | `narrative.toml` — keep the `.md` verbatim alongside, it's the human-readable intent |
| `hyperframes.json` | `timeline.toml` (fps, resolution, duration) + `master.blend` |
| `index.html` | `timeline.toml` + `master.blend` |
| `audio_meta.json` | `audio/meta.json` |
| `capture/extracted/tokens.json` | brand parameters in `lib/brand.blend` (`cmt.scene.set_param`) |
| `capture/extracted/asset-descriptions.md` | `description` per asset in `assets/manifest.json` |
| `snapshots/` + `descriptions.md` | `.comonteur/review/` |

Use the tasks for the ingest steps rather than hand-writing outputs (`comonteur:init` installs
them — see `workflows.md`):

```bash
mise run comonteur:ingest_narrative    # validate what you wrote
mise run comonteur:convert_fonts       # web fonts are .woff2; Blender cannot load those
mise run comonteur:ingest_manifest     # assets/ -> assets/manifest.json
```

Some projects use `youtube.yaml` instead of root `meta.json`, and `design.md` instead of
`STORYBOARD.md`. That convention split isn't settled — follow whatever the source project
uses and flag it; don't silently normalise to one.

## 3. Timing — the gate

There's no timeline data file in a HyperFrames project. Shot order is the filename's numeric
prefix. Shot durations and all GSAP timing live inside the HTML/JS — a parsing problem, not a
data-reading problem.

Three sources, increasing order of trust:

1. `hyperframes.json` — fps, resolution, overall duration.
2. Duration attributes on `[data-composition-id]` in `index.html`.
3. **`snapshots/frame-NN-at-<seconds>.png` filenames** — these timestamps come from the actual
   render and are ground truth for cut positions.

Reconcile (1) and (2) against (3). Where they disagree, or nothing is parseable, stop and ask
the human. Don't guess, don't average, don't pick the source that needs less work.

Present the recovered cut list as a table — shot, start, duration, which source each number
came from — and get it confirmed before building any scene. Every downstream piece of work
depends on it, and it's much cheaper to fix here.

If the project has a voiceover, prefer anchors over absolute starts in the resulting
`timeline.toml` (see `timeline.md`) — the imported absolute timings are the least durable
thing you're carrying over.

## 4. Fonts

Assets ship `.woff2`. Blender can't load `.woff` or `.woff2`. Convert during ingest and record
both paths in the manifest, so the converted file's provenance is traceable:

```bash
mise run comonteur:convert_fonts        # defaults to assets/fonts
```

Use the task rather than `fonttools` directly — its CLI has a `decompress` verb for woff2
only, and plain `.woff` has none, so the raw command quietly converts half your fonts.

A shot built with a silently-substituted default font looks wrong in a way that's easy to
miss in a low-res preview. Check the fonts resolved before you build the first title.

## 5. Rebuild the shots

One shot per `execute_python` call, one `journal.batch()` each, previewed before moving on
(see `../SKILL.md` — the loop and its gate apply here unchanged).

Read the shot's HTML for intent, not structure: what text appears, in what order, with what
emphasis, entering how. Then express that with `cmt.text` and `cmt.anim`. The GSAP ease names
carry straight across (`api.md`); the DOM structure doesn't.

Build the shared brand pieces into `lib/brand.blend` first and link them, rather than
rebuilding the same lockup eight times.

## 6. Assemble

Write `timeline.toml` from the confirmed cut list, then run the two-step in `timeline.md`.

No-voiceover projects (BGM + SFX only) are a first-class case, not a degraded one. Word-level
caption timing simply doesn't apply; on-screen text duration and the music itself drive the
pacing.

Finally: the deliverable is video + title + description + thumbnail, not video alone.
`thumbnail/thumbnail.png` renders from a dedicated `compositions/frames/thumbnail.blend`
reusing the components already in `lib/` — a still from the real project, not a screenshot.

## Delegate the mechanical pass

Steps 1 and 2 above — copying the identity-mapped tree, translating metadata files — are
mechanical: fixed file mappings, no judgment calls, no human confirmation needed. Run them in
a background `Agent` call with a cheaper model (e.g. `haiku`) instead of doing the copying
yourself. Give that subagent:

- the source project root and target project root
- the identity-mapping list and the translated-files table above, verbatim
- instruction to run the three ingest/font-conversion tasks listed in step 2
  (`mise run comonteur:ingest_narrative`, `ingest_manifest`, `convert_fonts`), and to report
  back what it copied, translated, and skipped (missing files, files it wasn't sure how to
  map)

Keep everything from step 3 onward — timing recovery, shot rebuild, the confirmation gate —
in the foreground. Those need the fuller model's judgment and the human's sign-off; don't
push them into the cheap-model subagent.

## Report honestly

End the import with what didn't survive: every timing number you had to ask about, every font
that needed converting, every GSAP effect you approximated rather than reproduced. A list of
known lossy spots is worth more to the human than a claim that it all came across.
