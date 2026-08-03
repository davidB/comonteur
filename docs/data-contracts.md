# comonteur — Data contracts

Part of the [comonteur spec](../SPEC.md). Section numbers match the original SPEC.md for
continuity with existing code comments (`SPEC.md §5...`).

---

## 5. Data contracts

### 5.1 Repository layout

Two distinct layouts share this document: the tool's own repository (this codebase),
and the layout of a video project the tool creates and operates on. Keep them apart —
`addon/`, `skills/` and friends belong to comonteur itself, never to a project directory.

#### 5.1a This repository (comonteur, the tool)

```
.
├── addon/comonteur/     # the in-Blender library + addon (§6). bpy-locked, Python.
│   └── pyproject.toml/mise.toml   # own uv project + venv (ruff only, no pytest)
├── skills/              # Claude Code skills, one dir per skill (`skills/comonteur/`),
│                         #   installed into a project's .claude/skills/ (§M5.5). Also holds
│                         #   everything outside the Blender process: the comonteur:* task
│                         #   scripts, uv run --script Python, one per task (§7.5, §8).
├── docs/                # DESIGN-RATIONALE.md, ADDONS.md, M0-FINDINGS.md
├── tests/
│   └── pyproject.toml/mise.toml   # own uv project + venv (pytest + ruff)
├── mise.toml             # monorepo root only — no code, no tasks of its own to run
├── README.md
└── SPEC.md
```

No production data, no `.blend`, no git-lfs here.

#### 5.1b Video project layout

One instance per video, initialized by the skill's `scripts/init.py` (also `mise run
comonteur:init` in a checkout) and operated on by the addon/skill at runtime. `init` is
**add-only**: every file below is created only when absent, so pointing it at a folder that
already holds footage, a `.blend` or another mise project is a normal operation (§8.2).
Note what is *not* below: no `AGENTS.md`/`CLAUDE.md`. The agent contract lives in the skill
(`skills/comonteur/SKILL.md` + `references/`), which is what an agent loads anyway; a
project's own agent-instruction files are the human's, and comonteur never writes or edits
them.

```
.
├── mise.toml                # pinned tools (ffmpeg, uv) — written only if absent
├── mise-tasks/comonteur/    # every comonteur:* task, uv run --script Python (+ _common.py)
├── assets/                 # same as HyperFrames — manifest.json generated alongside
├── audio/
├── captions/
├── narrative.toml          # HyperFrames-equivalent: STORYBOARD.md kept alongside verbatim
├── capture/                # copied unchanged, if imported from a HyperFrames project — §5.4
├── compositions/
│   └── frames/              # agent-generated scenes, one per shot, persistent & versioned
│       └── shot-03.blend    #   cmt_id = shot-03 — same purpose as HyperFrames' *.html here
├── lib/                     # reusable, human-authored component library. git-lfs.
│   ├── design.blend         #   colours, fonts, node groups (assets)
│   └── titles.blend         #   human-authored components
├── master.blend              # VSE assembly only. Links compositions/** + lib/**. git-lfs.
│                              # `comonteur:edit` creates it on first run if missing —
│                              # the one exception to "the agent never saves" (§4.5).
├── timeline.toml             # authoritative for assembly (§5.2)
├── .comonteur/
│   ├── journal.jsonl
│   ├── snapshot.json         # last agent-written values, for drift/claim derivation
│   └── review/                # preview.frames() output + descriptions.md — §6.4
├── renders/                  # outputs. gitignored.
├── thumbnail/
│   └── thumbnail.png
└── meta.json                 # title, description, tags, chapters — §5.6
```

This is the same root layout as a HyperFrames project — see §5.4 for the field-by-field
adapter and the two reference project trees it's built from. `lib/`, `master.blend`,
`timeline.toml`, `.comonteur/` are the only new names, needed because HyperFrames has no
equivalent of a reusable Blender component library, `index.html`, `hyperframes.json`, or
a mutation journal.

Agent-generated scenes live in their own `compositions/frames/*.blend` and are **linked**
into `master.blend`, not appended. Linked data is read-only in the master, which is
exactly the guarantee wanted. Library Overrides are the escape hatch when the master
genuinely needs a local tweak.

**M0.7 must verify: can a linked Scene be used as a VSE Scene strip?** If not, the
layout collapses to a single `master.blend` and the "never write the same file" property
is lost. This is the highest-impact unknown in the design.

`*.blend` and all media are LFS-sized; `init` ships LFS attribute patterns for them, but
tracking/using git-lfs is entirely up to whoever manages git for the project — comonteur
never runs `git`/`git lfs` itself.

### 5.2 `timeline.toml` — authoritative

The only file the agent treats as desired-state. Governs assembly only; says nothing
about scene interiors.

```toml
fps = 30
resolution = [1920, 1080]

[encode]
video_codec = "H265"        # optional, default "H265" — any scene.render.ffmpeg.codec identifier
video_container = "MPEG4"   # optional — auto-picked per codec when omitted
audio_codec = "AAC"          # optional — only set on the scene when given

[[shots]]
id = "shot-01"
source = {kind = "scene", blend = "compositions/frames/shot-01.blend", scene = "GEN_hook"}
start = 0
duration = 90

[[shots]]
id = "shot-02"
source = {kind = "movie", path = "assets/broll_terminal.mp4"}
anchor = {word = "observability", occurrence = 1, offset = -0.2}
duration = 120
in = 45
transition = {type = "cross", duration = 0.4}

[[shots]]
id = "caption-card"
source = {kind = "scene", blend = "compositions/frames/caption-card.blend", scene = "GEN_caption"}
overlay_of = "shot-02"      # inherits shot-02's start/duration; addon picks the channel

[[audio]]
id = "vo"
path = "audio/narration.wav"
start = 0
```

`transition` (optional, on a shot) applies a crossfade between that shot and the one
immediately before it; `duration` is seconds, like `anchor.offset` — both are timed
relative to the transcript/audio, not the edit grid. `cross` is the only type as of M4
(`docs/M4-FINDINGS.md`); more VSE effect-strip types can be added to the enum later.

`overlay_of = "<shot-id>"` (optional, on a shot) makes `start`/`anchor`/`duration`
optional overrides instead of requirements — omitted, they inherit the target shot's
resolved values. There is no `channel` field: `timeline.toml` expresses the relationship
(this shot overlays that one), and `addon/comonteur/reconcile.py`'s
`_allocate_overlay_channel` owns picking an actual free VSE channel above the target,
skipping the shot/transition rows and anything else already occupying that time range
(see `skills/comonteur/references/timeline.md` "Channel layout").

`[encode]` is optional and, unlike `transition.type`, its values are **not** enum-checked
by `reconcile.py` — `video_codec`/`video_container`/`audio_codec` pass straight through to
`scene.render.ffmpeg.codec`/`.format`/`.audio_codec` and Blender itself rejects an invalid
identifier at apply time. Omitting `[encode]` entirely is equivalent to
`video_codec = "H265"` with its container auto-picked and audio settings left untouched.

Reconcile: match VSE strips by `cmt_id`, update owned fields, delete agent strips no
longer listed, never touch untagged strips. Reconcile is not exempt from provenance
(§4.1/§4.3) — it writes through `journal.set()` like any other agent batch, so a field a
human has since edited (e.g. dragging a strip's duration in the dope sheet) is claimed and
reconcile skips it rather than overwriting it back to the spec's value. "Authoritative for
assembly" (§4.2) means authoritative for what the agent proposes, not a license to clobber
a human edit — same rule as everywhere else in this document.

**The task resolves, `addon/` applies (M4).** `timeline.toml` needs validating and its
anchors need a real word-timing lookup against `audio/transcript.json` — both are handled by
`mise run comonteur:reconcile` (`skills/comonteur/templates/mise-tasks/comonteur/reconcile.py`),
which validates the doc and resolves
every `anchor` to a plain integer `start_frame` (fail loudly, per above, if the anchor
word or its occurrence count doesn't match). It writes a resolved plan — no more TOML, no
more anchors — to `.comonteur/timeline.resolved.json` by default (same directory as the
journal; derived/ephemeral like `snapshot.json`, not a new top-level project file). The
addon (`addon/comonteur/reconcile.py`) never parses a spec file: it reads that JSON with the
stdlib `json` module and reconciles it into VSE strips. This is the same split as §5.3's
production-contract ingest (the task normalizes upstream input into a plain file; the
agent/addon consumes the file). Both sides are Python now, but the boundary is unchanged and
binding: parsing, validation and anchor resolution are the outside step's job, so the addon's
input is the resolved plan and never the source document. `tomllib` is stdlib and Blender
could technically read `timeline.toml` — that is not a reason to; the split exists so
validation has exactly one home. Importing a task script stays impossible regardless:
Blender's interpreter cannot see a uv environment (§8).

#### Anchor-relative timing (required)

A shot's position may be given as absolute `start` **or** as an `anchor` — a word in the
transcript, plus an occurrence index and a signed offset in seconds.

This exists because **audio processing shifts every downstream timing.** Silence removal,
re-recording, or a re-cut invalidates every absolute `start` in the project. Anchoring to
transcript words instead means: re-transcribe, re-resolve, done.

Resolution pipeline:

1. Capture anchors **before** any destructive audio edit (see `vo:retime` in §5.7).
2. Process audio.
3. Re-transcribe → `audio/transcript.json` (word-level).
4. `reconcile` resolves each anchor to an absolute frame and writes strip `frame_start`.

Anchors resolve at reconcile time; the resolved value is journalled like any other agent
write, so a human override of `frame_start` is claimed normally (§4.3) and survives
subsequent re-resolution.

Fail loudly, never silently, when an anchor word is missing or its occurrence count
changed — that means the script drifted from the recording and needs a human.

### 5.3 Production contract — pluggable upstream

No rendering instructions cross this line. The boundary is conceptual — which root-level
files an agent is allowed to treat as upstream-authored input — not a directory: unlike
earlier drafts, these live at project root (§5.1b), same as in a HyperFrames project.

- `narrative.toml` — shots: intent, target duration, VO reference, b-roll reference.
- `assets/manifest.json` — content-addressed; per asset: sha256, path, duration, fps,
  resolution, has_alpha, codec (from `ffprobe`).
- `audio/*.wav`
- `captions/*.json` — **word-level timing**.

**Three voiceover modes. All are first-class; none is a degraded path.**

| Mode | Word timing source |
|---|---|
| Synthesized (TTS) | Provider synthesis timing marks — exact by construction |
| **Human-recorded** | **Whisper word-level. There are no timing marks to take.** |
| No voiceover | On-screen text duration and the music track drive timing |

Human-recorded VO is the primary mode in the reference projects (`sox`/`rec` capture,
see §5.7), so Whisper is a primary path, not a fallback. Use synthesis timing marks
whenever the audio *was* synthesized, since they avoid ASR error on proper nouns and
technical terms.

**Implementation (M2):** `mise-tasks/comonteur/ingest_{narrative,manifest,captions}.py` —
a first-cut
`narrative.toml` schema (`shots: [{id, intent, target_duration, vo, broll}]`),
`ffprobe`-backed manifest building, and word-level caption normalization into
`{"words": [{"word", "start", "end"}]}`. Caption ingest normalizes JSON that already
exists (Whisper's `segments[].words[]`, or upstream-supplied TTS timing marks) — it does
not invoke `whisper` itself; that stays an external pipeline per §5.7.

### 5.4 HyperFrames project adapter

Reference layout: `cdviz-cloud-launch` (8 shots, screen-capture driven, music + SFX, no
voiceover). The adapter must handle this project without manual fixups — it is the M5
acceptance case.

**Structural mapping** (mostly mechanical, because both systems use one file per shot):

Most of the root is now an **identity mapping** — `assets/**`, `capture/`, `renders/`,
`thumbnail/`, root `meta.json`, `CLAUDE.md`/`AGENTS.md` carry over unchanged — the last two
literally so: comonteur neither generates nor edits them. Shot files
carry over 1:1 too: `compositions/frames/NN-slug.html` becomes
`compositions/frames/NN-slug.blend`, same path, one Blender scene each,
`cmt_id = NN-slug`. What remains is genuinely translated:

| HyperFrames | comonteur |
|---|---|
| `STORYBOARD.md` | `narrative.toml` — keep the `.md` verbatim alongside; it is the human-readable intent |
| `hyperframes.json` | `timeline.toml` (fps, resolution, duration) + `master.blend` |
| `audio_meta.json` | `audio/meta.json` |
| `capture/extracted/tokens.json` | brand parameters in `lib/design.blend` |
| `capture/extracted/asset-descriptions.md` | `description` field per asset in the manifest |
| `index.html` | `timeline.toml` + `master.blend` |
| `snapshots/` + `descriptions.md` | `.comonteur/review/` |
| `frame.md` | same convention, generated by the skill |

**Known-hard: timing.** There is no timeline data file. Shot **order** is the filename
numeric prefix; shot **durations** and all GSAP timing live inside the HTML/JS. Import is
therefore a parsing problem, not a data-reading problem.

- Read `hyperframes.json` and any duration attributes on `[data-composition-id]`.
- **Cross-check against `snapshots/frame-NN-at-<seconds>.png`** — those filenames carry
  real timestamps from the actual render and are ground truth for cut positions.
- Where the two disagree, or where nothing is parseable, **stop and ask the human**. Do
  not guess. HTML → timeline is not lossless and the adapter must not pretend otherwise.

**Known-hard: fonts.** Assets ship `.woff2`, which Blender cannot load. Convert to
TTF/OTF (`fonttools`) during ingest and record both paths in the manifest.

**Assets are duplicated** between `assets/` (curated subset) and `capture/assets/`
(full scrape), with names truncated to ~40 chars. Content-addressing by sha256 makes
dedup automatic; carry the human-readable description from
`capture/extracted/asset-descriptions.md`.

**`renders/work-*/`** is ephemeral scratch containing worker directories, retry attempts
and a symlink into `/tmp`. Never copy it; never archive it.

### 5.5 The no-voiceover case is first-class

The reference project has BGM and SFX but **no voiceover**. Word-level caption timing
(§5.3) therefore does not apply to it at all.

When there is no VO, the primary timing drivers are on-screen text duration and, where
useful, the music itself — 5.2's Sound socket and Sample Sound Frequencies node can drive
motion directly from the BGM track. Treat this as a normal mode, not a degraded one.

### 5.6 Publishing artifacts

The deliverable is video **+ title + description + thumbnail**, not video alone.

Root `meta.json` carries title, description, tags, chapters. `thumbnail/thumbnail.png`
is rendered from a dedicated Blender scene (`compositions/frames/thumbnail.blend`) — a
still render from the real project beats an HTML screenshot, and reuses the brand
components already in `lib/`.

### 5.7 Second reference project: `artifact-timeline-video`

Smaller, **with human-recorded voiceover**, and — importantly — it already contains a
hand-made `vse.blend`. The Blender-as-final-mix step is proven, not speculative. This is
the closest existing thing to comonteur's output and the better M1 fixture.

| Item | Meaning for comonteur |
|---|---|
| `vse.blend` / `.blend1` | Human-authored VSE mix of `renders/raw.mp4` + narration + music |
| `renders/BL_proxy/` | VSE proxies, per media file. **Gitignore.** |
| `audio/narration{,-orig}.wav` | Pre- and post-silence-cut. Both needed for anchor resolution |
| `audio/transcript{,-orig}.json` | Whisper word-level output, pre and post |
| `audio/scene-anchors.json` | Anchor words (§5.2), captured **before** the cut |
| `audio/music-01.strudel.txt` | Strudel source for the BGM — music is reproducible from code. Preserve as an asset **with source**; don't treat the `.wav` as opaque |
| `fonts/*.woff2` | Again woff2 → conversion required (§5.4) |
| `youtube.yaml` | Publishing metadata. **Use `youtube.yaml` at root, not `meta.json`** |
| `design.md` | This project's intent doc; the other uses `STORYBOARD.md`. Settle on one convention and migrate |

#### Reuse the existing audio pipeline verbatim

The `sox` / `ffmpeg` chains already in the project's `mise.toml` are working and tuned.
Lift them; do not reinvent:

- `vo:record` — `rec -r 48000 -c 1 -b 32`, 48 kHz mono 32-bit float
- `vo:process` — noise profile from the first 0.5 s → `noisered` → `norm -1` → `compand`
- `vo:cut` — `silenceremove` at −40 dB then `apad`; preserves `-orig`
- `vo:transcribe` — Whisper word-level → `transcript.json`
- `vo:retime` / `vo:retime:apply` — the anchor capture/resolve pair

In HyperFrames, `vo:retime:apply` rewrote `var S[]` inside `index.html` — codegen into
composition source. In comonteur the same step is a **normal reconcile pass over strip
`frame_start`** (§5.2). No codegen.

#### Do not fight `mise`

Both reference projects drive everything through `mise` tasks, with a shared `mise.toml`
symlinked across projects. comonteur ships task files that projects symlink or include —
not a competing entry point.

System dependencies stay system dependencies: `sox`, `ffmpeg`, `blender` via the platform
package manager. `doctor` checks them; `install` never installs them.

#### `vse.blend` is the M1 fixture

A **human-authored Blender project with zero comonteur tags** — exactly the G2 case,
available before any code is written. Point `introspect.outline` and `preview.frames` at
it first. If progressive disclosure and visual review don't work on this file, they won't
work on anything.
