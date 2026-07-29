# comonteur — Technical Specification

> **Name: `comonteur`.** From the French *monteur* (video editor) plus *co-*, as in
> co-pilot / coworker. Verified unclaimed on PyPI, crates.io and npm, with no GitHub
> repositories of that name (checked 2026-07-29).
>
> Derive everything from a **single constant** — package name, custom-property prefix
> (`cmt_`), addon id, journal filename, CLI name. A rename must remain a one-line change,
> not a find-replace across the tree.

Status: **draft for implementation**. Target reader: Claude Code, working locally.
Author context: distilled from a design discussion; see `docs/DESIGN-RATIONALE.md`
(to be written from this spec's "Why" notes).

---

## 1. Thesis

Build a video production system in which an **AI agent and a human edit the same
Blender project, in both directions, without either destroying the other's work.**

This is the Claude Code collaboration property — human edits files in their editor,
agent edits the same files, git mediates — transposed from text files to a `.blend`,
which is binary, unmergeable, and unreadable to an agent without a Python round-trip.

Everything else in this document exists to manufacture that property.

---

## 2. Goals

- **G1** Agent creates scenes (2D text, motion graphics, 3D) that the human can open in
  Blender and edit with the full normal toolset — dope sheet, graph editor, viewport.
- **G2** Agent can review and edit scenes the human authored, without needing to
  comprehend them in full.
- **G3** Neither party silently clobbers the other. Every agent mutation is attributable,
  reviewable and revertible.
- **G4** Human-in-the-loop is the normal mode: a running Blender session with a human
  attached. Headless is for CI and batch render only.
- **G5** Production upstream (script, storyboard, TTS, captions, assets) is pluggable —
  HyperFrames, a bespoke harness, or a human with a folder of footage all satisfy the
  same contract.

## 3. Non-goals

Explicitly rejected during design. Do not reintroduce without a decision record.

- **NG1** HTML/CSS/JS/GSAP anywhere in the final render path.
- **NG2** Transpiling HTML/GSAP into Blender.
- **NG3** A two-backend intermediate representation (dropped once HTML ceased to be a
  renderer — an intersection format would cap expressiveness at the browser's).
- **NG4** A third-party "video orchestrator". Claude Code + a skill + the Blender MCP
  server *is* the orchestrator.
- **NG5** Real-time concurrent multi-writer. Turn-taking is sufficient and much simpler.
- **NG6** A general-purpose Blender agent. This is video production, scoped.
- **NG7** A custom MCP server (for now — see §7).

---

## 4. Core architecture

### 4.1 Ownership is per-datablock provenance

Field-level locking was considered and rejected: it works for VSE strips, whose
properties are enumerable, but does not scale to objects, node trees, actions, grease
pencil layers, or arbitrary RNA. Strict scene-level partition (agent scenes vs human
scenes, neither looking inside the other) was also rejected — it contradicts G1 and G2.

Every datablock the agent creates carries:

| Property      | Type  | Meaning |
|---------------|-------|---------|
| `cmt_id`      | str   | Stable logical id, e.g. `shot-03.lower-third`. Survives renames. |
| `cmt_origin`  | str   | `agent` \| `human` \| `shared` |
| `cmt_rev`     | int   | Monotonic, bumped on each agent batch that touches this id |

Rules:

- **Untagged data is human data.** Never modified, never deleted, without an explicit
  instruction naming it.
- `origin == "agent"` — agent may mutate or delete freely.
- `origin == "shared"` — human has touched it. Agent may mutate only paths **not** in
  the claimed set (§4.3), and may **never** delete it.
- `origin == "human"` — agent may read and may mutate only when explicitly instructed
  in the current turn. Never on its own initiative.

Applies to: Scene, Object, Collection, Action, NodeTree, Material, GreasePencil, Text,
and VSE strips (**verify strips accept custom properties — M0.1**).

### 4.2 The agent never regenerates

Direct consequence of G1. If the human can edit `GEN_lower_third_03`, then regenerating
it destroys their work. The agent's only operation on existing data is **mutation**.

Reconcile therefore means: update agent-owned data still present in spec, remove
agent-owned data dropped from spec, leave everything else untouched.

**The scene is the source of truth. The spec is an intent log** — authoritative for
timeline assembly only (§5.2). This is the central trade of the design: reviewability is
bought back by the journal (§4.4), not by the ability to rebuild.

### 4.3 Automatic provenance flip

A `depsgraph_update_post` handler detects human edits to agent-owned data.

```python
@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph):
    if journal.batch_active():
        return                      # agent's own writes — not a human edit
    for upd in depsgraph.updates:
        id_ = getattr(upd.id, "original", upd.id)
        if id_.get("cmt_origin") == "agent":
            id_["cmt_origin"] = "shared"
            journal.record_flip(id_)
```

**Known limitation, do not paper over it:** `DepsgraphUpdate` exposes `is_updated_geometry`,
`is_updated_transform`, `is_updated_shading` — it does **not** report which RNA path
changed. So the handler can only flip coarsely.

Fine-grained claimed paths are **derived, not observed**:

```
claimed_paths(id) = { p : p ∈ journal.paths_written_by_agent(id)
                          ∧ resolve(p) != journal.last_agent_value(id, p) }
```

This works because the agent only needs to know which of *its own* paths it has lost.
Compute on demand in `provenance.claimed_paths()`, not in the handler — the handler must
stay cheap; it runs on every depsgraph evaluation.

Risks to validate in M0: handler noise (does it fire on selection-only changes?),
performance with many datablocks, correctness of `upd.id.original` for linked data.
A manual `Take ownership` / `Return to agent` operator pair in the sidebar is required
regardless, as an override.

### 4.4 The mutation journal

Mandatory. Since rebuild is no longer the recovery mechanism, the journal is the entire
audit / diff / revert surface.

`.comonteur/journal.jsonl`, append-only:

```json
{"ts":"2026-07-29T10:31:02Z","batch":"b_0f3a","actor":"agent","op":"set",
 "target":"bpy.data.scenes['GEN_lower_third_03'].objects['Title']","path":"location[1]",
 "old":0.0,"new":0.34}
{"ts":"2026-07-29T10:33:41Z","batch":null,"actor":"human","op":"flip",
 "target":"bpy.data.scenes['GEN_lower_third_03'].objects['Title']",
 "from":"agent","to":"shared"}
```

Every agent write goes through `journal.set()` — there is no other sanctioned path.
`exec_python` bypassing it produces **untracked drift**, surfaced by
`introspect.drift()` as the equivalent of `git status`, to be promoted into the journal
or discarded.

### 4.5 Batch protocol

```python
with journal.batch("retime shot-03"):
    anim.tween(...)
    cmt.set(obj, "location", ...)
# on exit: flush JSONL, bump cmt_rev, bpy.ops.ed.undo_push(message="comonteur: retime shot-03")
```

- Exactly **one** `undo_push` per batch, labelled. Without this the agent poisons the
  human's undo stack and the tool becomes unusable.
- `batch_active()` gates the provenance handler.
- Defer if a modal operator is running (transform/grab). Queue and retry.
- **The agent never saves the `.blend`.** Save is a human action, always.

---

## 5. Data contracts

### 5.1 Repository layout

Two distinct layouts share this document: the tool's own repository (this codebase),
and the layout of a video project the tool creates and operates on. Keep them apart —
`addon/`, `skill/` and friends belong to comonteur itself, never to a project directory.

#### 5.1a This repository (comonteur, the tool)

```
.
├── addon/comonteur/     # the in-Blender library + addon (§6)
├── skill/               # Claude Code skill
├── docs/                # DESIGN-RATIONALE.md, ADDONS.md, M0-FINDINGS.md
├── tests/
├── pyproject.toml / mise.toml
├── README.md
└── SPEC.md
```

No production data, no `.blend`, no git-lfs here.

#### 5.1b Video project layout

One instance per video, scaffolded by `comonteur new` (§M5.5) and operated on by the
addon/skill at runtime:

```
.
├── AGENTS.md / CLAUDE.md   # generated by the skill, HyperFrames convention
├── assets/                 # same as HyperFrames — manifest.json generated alongside
├── audio/
├── captions/
├── narrative.yaml          # HyperFrames-equivalent: STORYBOARD.md kept alongside verbatim
├── capture/                # copied unchanged, if imported from a HyperFrames project — §5.4
├── compositions/
│   └── frames/              # agent-generated scenes, one per shot, persistent & versioned
│       └── shot-03.blend    #   cmt_id = shot-03 — same purpose as HyperFrames' *.html here
├── lib/                     # reusable, human-authored component library. git-lfs.
│   ├── brand.blend          #   colours, fonts, node groups (assets)
│   └── titles.blend         #   human-authored components
├── master.blend              # VSE assembly only. Links compositions/** + lib/**. git-lfs.
├── timeline.yaml             # authoritative for assembly (§5.2)
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
`timeline.yaml`, `.comonteur/` are the only new names, needed because HyperFrames has no
equivalent of a reusable Blender component library, `index.html`, `hyperframes.json`, or
a mutation journal.

Agent-generated scenes live in their own `compositions/frames/*.blend` and are **linked**
into `master.blend`, not appended. Linked data is read-only in the master, which is
exactly the guarantee wanted. Library Overrides are the escape hatch when the master
genuinely needs a local tweak.

**M0.7 must verify: can a linked Scene be used as a VSE Scene strip?** If not, the
layout collapses to a single `master.blend` and the "never write the same file" property
is lost. This is the highest-impact unknown in the design.

Git LFS is mandatory for `*.blend` and all media.

### 5.2 `timeline.yaml` — authoritative

The only file the agent treats as desired-state. Governs assembly only; says nothing
about scene interiors.

```yaml
fps: 30
resolution: [1920, 1080]
shots:
  - id: shot-01
    source: {kind: scene, blend: compositions/frames/shot-01.blend, scene: GEN_hook}
    start: 0
    duration: 90
  - id: shot-02
    source: {kind: movie, path: assets/broll_terminal.mp4}
    anchor: {word: "observability", occurrence: 1, offset: -0.2}
    duration: 120
    in: 45
audio:
  - id: vo
    path: audio/narration.wav
    start: 0
```

Reconcile: match VSE strips by `cmt_id`, update owned fields, delete agent strips no
longer listed, never touch untagged strips. Reconcile is not exempt from provenance
(§4.1/§4.3) — it writes through `journal.set()` like any other agent batch, so a field a
human has since edited (e.g. dragging a strip's duration in the dope sheet) is claimed and
reconcile skips it rather than overwriting it back to the spec's value. "Authoritative for
assembly" (§4.2) means authoritative for what the agent proposes, not a license to clobber
a human edit — same rule as everywhere else in this document.

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

- `narrative.yaml` — shots: intent, target duration, VO reference, b-roll reference.
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

### 5.4 HyperFrames project adapter

Reference layout: `cdviz-cloud-launch` (8 shots, screen-capture driven, music + SFX, no
voiceover). The adapter must handle this project without manual fixups — it is the M5
acceptance case.

**Structural mapping** (mostly mechanical, because both systems use one file per shot):

Most of the root is now an **identity mapping** — `assets/**`, `capture/`, `renders/`,
`thumbnail/`, root `meta.json`, `CLAUDE.md`/`AGENTS.md` carry over unchanged. Shot files
carry over 1:1 too: `compositions/frames/NN-slug.html` becomes
`compositions/frames/NN-slug.blend`, same path, one Blender scene each,
`cmt_id = NN-slug`. What remains is genuinely translated:

| HyperFrames | comonteur |
|---|---|
| `STORYBOARD.md` | `narrative.yaml` — keep the `.md` verbatim alongside; it is the human-readable intent |
| `hyperframes.json` | `timeline.yaml` (fps, resolution, duration) + `master.blend` |
| `audio_meta.json` | `audio/meta.json` |
| `capture/extracted/tokens.json` | brand parameters in `lib/brand.blend` |
| `capture/extracted/asset-descriptions.md` | `description` field per asset in the manifest |
| `index.html` | `timeline.yaml` + `master.blend` |
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
symlinked across projects. comonteur ships a task file that projects symlink or include,
with the CLI (§M5.5) underneath — not a competing entry point.

System dependencies stay system dependencies: `sox`, `ffmpeg`, `blender` via the platform
package manager. `doctor` checks them; `setup` never installs them.

#### `vse.blend` is the M1 fixture

A **human-authored Blender project with zero comonteur tags** — exactly the G2 case,
available before any code is written. Point `introspect.outline` and `preview.frames` at
it first. If progressive disclosure and visual review don't work on this file, they won't
work on anything.

---

## 6. The in-Blender library (`addon/comonteur/`)

This is where all discipline lives, because the MCP server provides none (§7). It exists
equally to **reduce agent token consumption**: the agent calls
`cmt.text.reveal(scene, "Hello", start=12, ease="BACK_OUT")` (canonical alias
`import comonteur as cmt`), not forty lines of `keyframe_points.insert()`.

| Module | Responsibility |
|---|---|
| `provenance.py` | tag / flip handler / `claimed_paths` / ownership queries / take-ownership operators |
| `journal.py` | `batch()` context manager, `set()`, JSONL, snapshot, revert |
| `scene.py` | `new_scene()` — see §6.1. Scene params interface. |
| `anim.py` | `tween`, `stagger`, easing map, F-curve helpers |
| `text.py` | text objects, styling, fit-to-box, per-character split |
| `vse.py` | assembly, scene strips, transitions, audio |
| `library.py` | link `lib/*.blend` (component library) and `compositions/frames/*.blend` (per-shot scenes), asset catalog discovery |
| `introspect.py` | `outline`, `describe`, `animated_paths`, `find`, `drift` |
| `preview.py` | render frames for agent review |
| `reconcile.py` | timeline.yaml → VSE |

### 6.1 `new_scene()` — deterministic baseline (hard requirement)

Creating a scene must **never** inherit state from `bpy.context.scene`. Every generated
scene starts from an explicit, known baseline:

```python
def new_scene(name, *, kind, fps, resolution, frame_range,
              transparent=True, view_transform=None) -> bpy.types.Scene
```

Must:
1. Create the scene, then **remove every inherited object** (default cube/camera/light).
   Verify `bpy.ops.scene.new(type=...)` semantics in M0.2 rather than assuming.
2. Set explicitly, never inherit: render engine, `resolution_x/y`,
   `resolution_percentage`, `fps`, `fps_base`, `frame_start`, `frame_end`,
   `film_transparent`, world.
3. Set `view_settings.view_transform`. **`'Standard'` for 2D/graphics scenes** — the
   default AgX will visibly shift brand colours. `'AgX'` only for 3D scenes intended to
   be photographic.
4. Tag `cmt_id` / `cmt_origin` / `cmt_rev`.
5. Be idempotent by `cmt_id`: if a scene with that id exists, return it rather than
   creating a duplicate.

### 6.2 `anim.py` — real F-curves, non-negotiable

The agent's animation output **must** be editable in the dope sheet and graph editor.
That means real keyframes on real data paths — no drivers-as-animation, no baked
transforms, no custom evaluation.

```python
anim.tween(obj, "location", index=1, frm=-0.4, to=0.0,
           start=12, dur=20, ease="BACK_OUT")
anim.stagger(objs, "location", index=1, offset=2, **tween_kwargs)
```

Easing map (from the discussion — the sets are near-identical by design):

| GSAP | Blender `interpolation` | Blender `easing` |
|---|---|---|
| `power1` | `QUAD` | |
| `power2` | `CUBIC` | |
| `power3` | `QUART` | |
| `power4` | `QUINT` | |
| `sine` / `expo` / `circ` | `SINE` / `EXPO` / `CIRC` | |
| `back` / `elastic` / `bounce` | `BACK` / `ELASTIC` / `BOUNCE` | |
| `.in` / `.out` / `.inOut` | | `EASE_IN` / `EASE_OUT` / `EASE_IN_OUT` |
| `cubic-bezier(...)` / `CustomEase` | `BEZIER` | (computed handles) |

Reusable motion should become **Actions instanced via NLA strips with a time offset**,
not re-emitted keyframes. Far more reviewable, and it is the Blender-native equivalent
of a component with baked-in animation.

### 6.3 `introspect.py` — progressive disclosure, never dumps

One Geometry Nodes tree dumped naively will exceed the whole spec in tokens.

- `outline(scene, depth=1)` → shallow tree: collections, object names, types, counts.
  Hard cap on lines; truncate with `… +N more`.
- `describe(datapath, depth=1)` → drill down to one node.
- `animated_paths(scene)` → which RNA paths carry F-curves, key counts, frame ranges.
- `find(type=, name~=, tag=)` → targeted lookup.
- `drift()` → untracked changes vs `.comonteur/snapshot.json`.

Every function takes and enforces a token budget.

### 6.4 `preview.py` — review is visual

For G2, the agent reviews by **looking**, not by reading data.

`preview.frames(scene, frames=[start, mid, end], pct=25, engine="WORKBENCH")` →
image paths returned to the agent for multimodal inspection.

Written to `.comonteur/review/frame-NN-at-<seconds>.png`, alongside a
`descriptions.md` in which **the agent records what it saw**. Borrowed from
HyperFrames' `snapshots/` convention: writing the observation down, rather than only
looking, makes review auditable after the fact and survives context loss.

"The headline crosses title-safe at frame 40" is real review. Structural inspection
happens afterward, scoped to the one thing being fixed.

---

## 7. MCP layer

**Use the official Blender Foundation MCP server.** Do not fork
`anan0110692/blender-mcp-vse` or any other unless a concrete need appears that cannot be
met from the helper library — record the reason if so.

- Add-on: Blender Lab extension, requires Blender 5.1+. Installed by dragging the
  extension into Blender **twice** (first adds the Blender Lab repository, then installs
  the add-on), or via Install from Disk.
- Server: `.mcpb` bundle for clients that support it, else from source.

Consequences to design around:

1. **It is `execute_python`-centric and analysis-oriented.** There is no provenance,
   batching or journaling in it and none is coming. All of that lives in
   `addon/comonteur/`, and the skill's job is to make the agent call the library rather
   than write raw `bpy`.
2. **It executes LLM-generated code with no guards.** Blender's own documentation
   recommends running it on a VM or a machine without sensitive data. Say so in the
   README; do not soften it.
3. Raw `bpy` remains available and is sometimes correct. It is not forbidden — it is
   **quarantined**: effects show up in `introspect.drift()` and must be promoted or
   discarded.

### 7.4 Build vs. buy — decision record

The transport decision is **deferred past M1** and deliberately kept reversible.

Three separable layers, with very different value in owning them:

| Layer | Value in owning | Verdict |
|---|---|---|
| MCP server (stdio ↔ TCP bridge) | Low — it is a pipe | Use official |
| Blender-side addon (receive / exec / return) | Medium — main-thread guarantee, queue, batch integration | Use official, fork only on M0.9 failure |
| `comonteur` library | All of it | Ours already |

Rationale for not shipping a custom typed-tool MCP: the library **is** the typed surface,
expressed in Python rather than JSON schema. Adding a function is a library edit;
adding an MCP tool is a server release plus a client reinstall. The exec+library
combination iterates faster and has no wall at the edge of an anticipated tool set.

Non-trivial things the official server provides, which a rewrite must replace:

- Blender API reference (RST) and manual excerpts shipped to the model at connection
  time. Measurably reduces hallucinated `bpy` calls; real work to replicate.
- Maintenance by the Blender Foundation across API releases.

Gaps that are **not** MCP problems and must not be used to justify a rewrite:

- Lifecycle (launch Blender, open project, health check, reconnect) → belongs in the
  `comonteur` CLI.
- Three-step install friction → a packaging problem; solve with an installer.
- Guardrails → need full context; belong in the library.

**Hard trigger for forking the addon: M0.9.** If `execute_python` does not run on
Blender's main thread, the official addon cannot be used for mutation. Fork the addon,
keep the official MCP server — the wire protocol is fine.

**Soft triggers, reassess after M5:** latency unacceptable in practice; the docs bundle
proves not to help; distribution friction becomes the top user complaint.

### 7.5 Reversibility constraint (binding)

**Depend on `execute_python` and nothing else, behind a single adapter module**
(`addon/comonteur/transport.py` or equivalent). No other MCP tool from the official server
may be called from `comonteur` code.

Blender Lab is at v1.0.0 and explicitly experimental. This isolation makes swapping the
transport roughly a day's work rather than a refactor, and is worth having regardless of
the eventual decision.

If a custom MCP server + CLI is ever built, the language policy is: **Rust for
everything outside the Blender process; Python for everything inside it** (bpy is
Python-only).

---

## 8. Tooling and language policy

- **v1 is pure Python.** `mise` for tool versions, `uv` for dependency and venv
  management, `ruff` for lint + format. Simpler to develop; the MCP ecosystem already
  requires Python and `uv`/`uvx` on the user's machine.
- Blender **5.2 LTS, pinned** (released 2026-07-14, supported to July 2028). Every line
  the agent emits is only reproducible against a pinned `bpy`. Do not track 5.3+.
- Type hints throughout; `bpy` stubs (`fake-bpy-module`) for editor support.
- Tests: pure-logic modules (journal, easing map, spec parsing, manifest) unit-tested
  outside Blender. Blender-dependent modules tested via `blender -b -P tests/run.py`.

### 8.1 Third-party Blender add-ons — explicit allowlist

Add-ons are permitted but each requires an entry in `docs/ADDONS.md` with: name,
version, why, and what breaks without it. No implicit dependencies.

Selection principle: **prefer asset libraries (data) over add-ons (operators).** The
agent works through the data API; add-on operators need valid context and are awkward to
drive from a timer callback. Add-ons that ship reusable **node groups, assets or
components** are high value. Add-ons that only add UI operators are low value here.

Start with zero and add only on demonstrated need.

---

## 9. Components and the asset system

Blender's asset system is the component registry — do not build one.

Mark a Scene, node group, or Action as an asset; give it a catalog, description, tags and
a preview render. That is a self-describing, human-authored, thumbnailed component
library. The agent lists catalogs, reads descriptions, looks at previews, and picks.

5.2's **remote asset library hosting** means a brand kit can be a URL rather than a
vendored folder — worth designing for even if v1 ships local.

Parameter interface, once a component is chosen: custom properties on the Scene or a
`PARAMS` empty, with subtypes and UI limits. Notes:

- Numeric params propagate cleanly via **drivers**.
- **Strings are not drivable.** A handler must sync `scene["headline"]` into the text
  object's `data.body`.
- Geometry Nodes modifier inputs are the other good interface — typed, with UI. The
  **String to Curves** node gives per-character instances, which is how GSAP-style
  `SplitText` staggers are done natively.
  **⚠ The GN modifier property Python API changed in 5.2 — verify before building on it (M0.3).**

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
  Prefer `blender --command extension install-file` (available since 4.2 — **verify in
  M0.11**); fall back to copying into the platform extensions directory.
- Register the MCP server: `claude mcp add`, or write a project-local `.mcp.json`.
- Install the Claude Code skill into `.claude/skills/`.
- Scaffold a new project (`comonteur new`).

Out of scope — **detect and report, never install**: Blender itself, `ffmpeg`, git-lfs.
Platform package managers own these; silently installing them is user-hostile.

Ends by running `doctor` and printing the result.

### M6 — Launch video
A product-launch video **about comonteur, made with comonteur**. Published to YouTube,
embedded in the README. Dogfooding as acceptance test.

---

## 11. Constraints checklist

Cross-cutting; violating any of these produces bugs that are hard to attribute.

- `bpy` is **not thread-safe**. Socket thread queues; `bpy.app.timers` drains on the main
  thread.
- Prefer the data API over `bpy.ops`. Operators need context overrides and fail
  confusingly from timers.
- One labelled `undo_push` per batch. Defer while a modal operator runs.
- **Agent never saves the file.**
- Strings are not drivable → handler sync.
- No layout engine. Text fitting = measure `obj.dimensions` after a depsgraph update,
  iterate.
- Colour management: `view_transform = 'Standard'` for imported sRGB and 2D graphics.
- Alpha: PNG sequence or ProRes 4444. VP9-with-alpha WebM is unreliable in the VSE.
- Gitignore: `renders/`, `renders/BL_proxy/`, `*.blend1`, HyperFrames `renders/work-*/`.
- Fonts: Blender loads TTF/OTF only. Web assets ship `.woff2` and must be converted at
  ingest (`fonttools`).
- Time: fps lives in the spec and is resolved **once**. Never let two layers round
  independently.
- Coordinates: CSS is top-left/y-down/layout-px; VSE transform offsets are
  center-origin/y-up/project-px.
- Render budget: Workbench/OpenGL previews in the agent loop; full renders at the end,
  local, not CI.
- MCP socket is an RCE surface: localhost-only, and see §7.2.

---

## 12. Open risks

| Risk | Impact | Mitigation |
|---|---|---|
| Linked scenes unusable as VSE scene strips (M0.7) | Repo layout collapses; agent and human write the same file | Verify in M0. Fallback: single `master.blend` + LFS, rely on journal + provenance alone |
| Automatic provenance flip too noisy or too coarse | Core UX broken | M1 gates on this. Manual take-ownership operators exist regardless |
| Token cost of introspection on real scenes | Agent becomes unusable on non-trivial projects | Hard budgets in `introspect`; visual review preferred over structural |
| Blender 5.2 API drift in helper library | Silent breakage | Pinned version; `docs/M0-FINDINGS.md` as the record of what was verified |
| Journal grows unbounded | Slow, unreviewable | Rotate per session; snapshot compaction |
| Loss of rebuild-from-source | Unexplainable scenes | Journal + provenance are the deliberate substitute. Accepted trade — see §4.2 |
