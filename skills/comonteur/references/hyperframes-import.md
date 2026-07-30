# Importing a HyperFrames project

HyperFrames composes video by writing HTML/CSS/JS; comonteur composes it in Blender. The
root layouts are deliberately almost identical, so most of an import is copying. What is
left is genuinely lossy — **HTML → timeline is not a lossless conversion and this procedure
must not pretend otherwise.**

Nothing about rendering crosses the line. You are not transpiling GSAP into Blender; you are
recovering *intent* (what plays, when, for how long, in what style) and rebuilding it as
scenes and keyframes.

## Order of work

Do these in order and stop at the first thing you cannot resolve.

1. **Copy the identity-mapped tree.**
2. **Translate the metadata files** (table below).
3. **Recover the timing** and get it confirmed — this is the gate.
4. **Convert the fonts.**
5. **Rebuild each shot** as a Blender scene, one at a time, previewing each.
6. **Write `timeline.toml`** and reconcile into `master.blend`.

## 1. Identity mapping

Carried over unchanged: `assets/**`, `capture/`, `renders/`, `thumbnail/`, root
`meta.json`, `CLAUDE.md` / `AGENTS.md`, `frame.md`.

`compositions/frames/NN-slug.html` → `compositions/frames/NN-slug.blend`, **same path**,
one Blender scene each, `cmt_id = NN-slug`.

Two exclusions:

- **Never copy `renders/work-*/`.** It is ephemeral scratch — worker dirs, retry attempts,
  and a symlink into `/tmp`. Never copy it, never archive it.
- **Gitignore `renders/BL_proxy/`** if the project has one (VSE proxies, regenerable).

Assets are duplicated between `assets/` (curated) and `capture/assets/` (full scrape), with
names truncated to ~40 chars. Dedupe by sha256 content hash, keep the curated name, and
carry the human-readable description from `capture/extracted/asset-descriptions.md` into
the manifest's `description` field.

## 2. Translated files

| HyperFrames | comonteur |
|---|---|
| `STORYBOARD.md` | `narrative.toml` — **keep the `.md` verbatim alongside**, it is the human-readable intent |
| `hyperframes.json` | `timeline.toml` (fps, resolution, duration) + `master.blend` |
| `index.html` | `timeline.toml` + `master.blend` |
| `audio_meta.json` | `audio/meta.json` |
| `capture/extracted/tokens.json` | brand parameters in `lib/brand.blend` (`cmt.scene.set_param`) |
| `capture/extracted/asset-descriptions.md` | `description` per asset in `assets/manifest.json` |
| `snapshots/` + `descriptions.md` | `.comonteur/review/` |

Use the tasks for the ingest steps rather than hand-writing the outputs (`comonteur:init`
installs them — see `workflows.md`):

```bash
mise run comonteur:ingest_narrative    # validate what you wrote
mise run comonteur:ingest_manifest     # assets/ -> assets/manifest.json
```

Some projects use `youtube.yaml` instead of root `meta.json`, and `design.md` instead of
`STORYBOARD.md` (`docs/data-contracts.md` §5.7). That convention split is **not settled**.
Follow whatever the source project uses and flag it; do not silently normalise to one.

## 3. Timing — the gate

**There is no timeline data file in a HyperFrames project.** Shot order is the filename's
numeric prefix. Shot durations and all GSAP timing live inside the HTML/JS. This is a
parsing problem, not a data-reading problem.

Three sources, in increasing order of trust:

1. `hyperframes.json` — fps, resolution, overall duration.
2. Duration attributes on `[data-composition-id]` in `index.html`.
3. **`snapshots/frame-NN-at-<seconds>.png` filenames** — these timestamps come from the
   actual render and are **ground truth** for cut positions.

Reconcile (1) and (2) against (3). Where they disagree, or where nothing is parseable,
**stop and ask the human**. Do not guess, do not average, do not pick the source that
requires less work.

Present the recovered cut list as a table — shot, start, duration, and which source each
number came from — and get it confirmed before building any scene. Every downstream frame
of work depends on it, and it is much cheaper to fix here.

If the project has a voiceover, prefer **anchors over absolute starts** in the resulting
`timeline.toml` (see `timeline.md`) — the imported absolute timings are the least durable
thing you are carrying over.

## 4. Fonts

Assets ship `.woff2`. **Blender cannot load `.woff2`.** Convert to TTF or OTF with
`fonttools` during ingest and record both paths in the manifest, so the provenance of the
converted file is traceable.

```bash
uvx --from fonttools fonttools ttLib.woff2 decompress fonts/Inter.woff2
```

A shot built with a silently-substituted default font looks wrong in a way that is easy to
miss in a low-res preview. Check the fonts resolved before you build the first title.

## 5. Rebuild the shots

One shot per `execute_python` call, one `journal.batch()` each, previewed before moving on
(see `../SKILL.md` — the loop and its gate apply here unchanged).

Read the shot's HTML for *intent*, not for structure: what text appears, in what order,
with what emphasis, entering how. Then express that with `cmt.text` and `cmt.anim`. The
GSAP ease names carry straight across (`references/api.md`); the DOM structure does not.

Build the shared brand pieces into `lib/brand.blend` first and link them, rather than
rebuilding the same lockup eight times.

## 6. Assemble

Write `timeline.toml` from the confirmed cut list, then run the two-step in `timeline.md`.

No-voiceover projects (BGM + SFX only) are a **first-class case, not a degraded one**.
Word-level caption timing simply does not apply; on-screen text duration and the music
itself drive the pacing.

Finally: the deliverable is video **+ title + description + thumbnail**, not video alone.
`thumbnail/thumbnail.png` renders from a dedicated `compositions/frames/thumbnail.blend`
reusing the components already in `lib/` — a still from the real project, not a screenshot.

## Report honestly

End the import with what did not survive: every timing number you had to ask about, every
font that needed converting, every GSAP effect you approximated rather than reproduced. A
list of known lossy spots is worth more to the human than a claim that it all came across.
