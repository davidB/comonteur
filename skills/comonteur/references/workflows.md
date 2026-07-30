# Project-level workflows

`../SKILL.md`'s loop is **per shot**. This file is the order of work **around** it: how a
project starts, what gets ingested, and what shipping means. Read it when the human asks for
a video rather than for a shot.

## Which workflow is this?

Decide before touching anything, by looking at the directory:

| What you see | Workflow |
|---|---|
| Nothing, or only raw material (a brief, footage, a `.wav`) | **A — from scratch** |
| `index.html` + `hyperframes.json` + `compositions/frames/*.html` | **B — import** → `hyperframes-import.md`, stop reading here |
| Harness output (script, shot list, `assets/`, TTS audio, captions) but **no** HTML compositions | **C — harness upstream, Blender rendering** |
| `master.blend` + `timeline.yaml` + `.comonteur/` | An existing comonteur project — go straight to the per-shot loop |

If it's ambiguous, ask. Scaffolding over an existing project is destructive in a way the
journal cannot undo.

## A — from scratch

1. **Create the tree** (`docs/data-contracts.md` §5.1b). There is no `comonteur new` yet
   (M5.5); make the directories and files yourself:

   ```
   assets/  audio/  captions/  compositions/frames/  lib/  renders/  thumbnail/
   narrative.yaml  timeline.yaml  meta.json
   ```

2. **Git + LFS**, before the first `.blend` exists — retrofitting LFS on committed binaries
   is a rewrite:

   ```bash
   git init
   git lfs track "*.blend" "assets/**" "audio/**" "renders/**"
   ```

   `.gitignore`: `renders/`, `.comonteur/review/`, `renders/BL_proxy/`.

3. **Write `narrative.yaml`** from what the human described — `shots: [{id, intent,
   target_duration, vo, broll}]` — then validate it, don't eyeball it:

   ```bash
   comonteur ingest narrative narrative.yaml
   ```

   Keep any prose brief (`STORYBOARD.md`, `design.md`) verbatim alongside it. The YAML is
   the machine-readable projection, not a replacement for the human's own words.

4. **Ingest what exists.** Assets and captions only — skip either if there is none:

   ```bash
   comonteur ingest manifest assets/ -o assets/manifest.json
   comonteur ingest captions <input.json> --kind whisper -o captions/vo.json
   ```

   `--kind tts` when the audio was synthesized (timing marks beat ASR on proper nouns);
   `--kind whisper` for human-recorded VO. No voiceover is a first-class case, not a
   degraded one (§5.5) — on-screen text and music drive the pacing instead.

5. **Create `master.blend` and `lib/brand.blend`** — brand colours, fonts and node groups
   first, marked as assets, so shots link them instead of redefining them eight times.

6. **Generate the project's `AGENTS.md` / `CLAUDE.md`** (HyperFrames convention, §5.1b): what
   this video is, its fps/resolution, where the brand lives, and that comonteur rules apply.

7. **Hand back.** Tell the human to open `master.blend` and leave it open — you talk to that
   live session. Then the per-shot loop in `../SKILL.md`, one shot at a time.

8. **Assemble** with `timeline.md` once the shots exist.

## C — HyperFrames harness upstream, Blender rendering

The harness (script → shot list → asset prep → TTS → word-level captions) is worth keeping.
The renderer is not — that is the whole point of comonteur.

**Do not create `index.html`, any HTML composition, or run the HyperFrames renderer.** Shots
are authored in Blender from the first frame. There is no HTML to parse afterwards, so none
of workflow B's lossiness applies — do not import your own output.

1. Run the harness for production prep only. Its output already matches the production
   contract (§5.3): shot list, `assets/`, `audio/`, word-level captions.
2. Map its files onto §5.1b names using the metadata table in `hyperframes-import.md` §2
   (`STORYBOARD.md` → `narrative.yaml`, `audio_meta.json` → `audio/meta.json`, tokens →
   `lib/brand.blend`). **Metadata only** — that document's §3 timing recovery and §5 shot
   rebuilding are for imports and have no equivalent here.
3. Then A's steps 2–8, skipping what the harness already produced.
4. **Prefer `anchor` over absolute `start`** in `timeline.yaml` (`timeline.md`). TTS gets
   re-synthesized; anchors survive it, absolute frames don't.

## Rendering and delivery — all three workflows

The deliverable is **video + title + description + thumbnail**, not video alone.

- Render from `master.blend` into `renders/`. Never overwrite a render the human is holding
  onto without asking.
- `thumbnail/thumbnail.png` renders from a dedicated `compositions/frames/thumbnail.blend`
  reusing the components already in `lib/` — a real frame from the real project, not a
  screenshot.
- `meta.json` (§5.6): title, description, tags, chapters.

**The rendered-frame gate applies here too.** Never report an assembly or a delivery as done
without having read a frame out of it — a shot can be perfect and still land on the wrong
strip, at the wrong length, over the wrong audio.

## Always the human's, never yours

- **Saving the `.blend`.** Always. Say so at the end of every batch of work.
- **Confirming a recovered cut list** (workflow B's gate).
- **Ownership overrides** — the sidebar's *Take ownership* / *Return to agent*.
- **Deleting or overwriting anything they made.** Untagged is human; ask by name.
