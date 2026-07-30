# Project-level workflows

`../SKILL.md`'s loop is **per shot**. This file is the order of work **around** it: how a
project starts, what gets ingested, and what shipping means. Read it when the human asks for
a video rather than for a shot.

## Run tasks, not shell

If the project has `mise-tasks/comonteur/` (or `mise tasks` lists `comonteur:*`), **use
`mise run comonteur:<task>`** — never the raw command it wraps. Reasons, in order: the human
can re-run exactly what you ran, the tools are pinned so it behaves the same tomorrow, and
`mise tasks` is a menu they can read without a chat transcript.

If a repeatable command has no task, **add one** under `mise-tasks/comonteur/` (a
`#!/usr/bin/env -S uv run --script` shebang, a `#MISE description=` line, `#USAGE arg`/`flag`
headers for any arguments —
[docs](https://mise.jdx.dev/tasks/task-arguments.html#file-task-headers) — and
`#MISE dir="{{config_root}}"` instead of a `cd`) rather than running it ad-hoc. Every existing
task is stdlib-only Python; keep it that way, and reuse `_common.py` next to them. Anything
the comonteur stack adds to a user's project is namespaced `comonteur:` — the project may be
someone else's mise project, so never claim a bare name like `render` or `build`.

**Before a project has tasks**, the same files are runnable straight from this skill:
`uv run <skill>/scripts/{init,setup,doctor}.py` (`../scripts/` from here — it is the task directory
itself). After `init` there is only one way to say it: `mise run comonteur:<task>`. The human
does not need a checkout of the comonteur repo, so never tell them to clone one.

Don't install system tooling silently. If doctor reports a ✗, relay those lines and let the
human run `mise run comonteur:install` — or ask before running it for them.

Check `--help` on a task rather than guessing its arguments; each one declares them in its own
`#USAGE` header.

## Which workflow is this?

Decide before touching anything, by looking at the directory:

| What you see | Workflow |
|---|---|
| Nothing, or only raw material (a brief, footage, a `.wav`) | **A — from scratch** |
| `index.html` + `hyperframes.json` + `compositions/frames/*.html` | **B — import** → `hyperframes-import.md`, stop reading here |
| Harness output (script, shot list, `assets/`, TTS audio, captions) but **no** HTML compositions | **C — harness upstream, Blender rendering** |
| `master.blend` + `timeline.toml` + `.comonteur/` | An existing comonteur project — go straight to the per-shot loop |

If it's ambiguous, ask.

## A — from scratch

1. **Initialize the folder** — this skill's own script, no checkout involved:

   ```bash
   uv run <skill>/scripts/init.py <dir>   # dir defaults to .
   ```

   It creates the §5.1b tree, all eleven `comonteur:*` tasks (`mise-tasks/comonteur/`, from
   `<skill>/templates/`), and stub `narrative.toml` / `timeline.toml` / `meta.json` /
   `AGENTS.md`. It is **add-only**: an existing folder with footage, a `.blend`, or its own
   `mise.toml` is a normal input — nothing already there is overwritten, and re-running it
   tops up what's missing and prints what it kept. Everything after this step, `install` and
   `doctor` included, is `mise run comonteur:*` from inside the project. Tell the human to
   `mise trust` once — the task files are new to mise.

2. **Ask about git and Git LFS — do not decide for them.** `init` takes `--git` and `--lfs`
   (LFS needs git), both off by default. Ask once, plainly:

   > *Version-control this project with git? And `.blend`/media files are large — track them
   > with Git LFS?*

   Mention the one fact that makes the timing matter: LFS retrofitted onto binaries already
   committed to history means a history rewrite, so it is much cheaper to decide now. If they
   decline, initialize without and don't raise it again. Never run `git init` inside a folder
   that is already in a git work tree — `init --git` refuses, deliberately.

3. **Write `narrative.toml`** from what the human described — `shots: [{id, intent,
   target_duration, vo, broll}]` — then validate it, don't eyeball it:

   ```bash
   mise run comonteur:ingest_narrative
   ```

   Keep any prose brief (`STORYBOARD.md`, `design.md`) verbatim alongside it. The TOML is
   the machine-readable projection, not a replacement for the human's own words.

4. **Ingest what exists.** Assets and captions only — skip either if there is none:

   ```bash
   mise run comonteur:ingest_manifest
   mise run comonteur:ingest_captions <input.json> --kind whisper
   ```

   `--kind tts` when the audio was synthesized (timing marks beat ASR on proper nouns),
   `whisper` (the default) for human-recorded VO. Every task carries `--help`, generated from
   its own header — check that rather than guessing at arguments. No voiceover is a
   first-class case, not a
   degraded one (§5.5) — on-screen text and music drive the pacing instead.

5. **Create `master.blend` and `lib/brand.blend`** — brand colours, fonts and node groups
   first, marked as assets, so shots link them instead of redefining them eight times.

6. **Fill in the project's `AGENTS.md`** (`init` writes the skeleton, with `CLAUDE.md`
   pointing at it): what this video is, its fps/resolution, where the brand lives.

7. **Hand back.** Tell the human to open `master.blend` — `mise run comonteur:edit` — and
   leave it open; you talk to that live session. Then the per-shot loop in `../SKILL.md`, one
   shot at a time.

8. **Assemble** with `timeline.md` once the shots exist.

## C — HyperFrames harness upstream, Blender rendering

The harness (script → shot list → asset prep → TTS → word-level captions) is worth keeping.
The renderer is not — that is the whole point of comonteur.

**Do not create `index.html`, any HTML composition, or run the HyperFrames renderer.** Shots
are authored in Blender from the first frame. There is no HTML to parse afterwards, so none
of workflow B's lossiness applies — do not import your own output.

1. Run the harness for production prep only. Its output already matches the production
   contract (§5.3): shot list, `assets/`, `audio/`, word-level captions. `init` on
   that folder is safe — it adds what's missing and keeps what the harness produced.
2. Map its files onto §5.1b names using the metadata table in `hyperframes-import.md` §2
   (`STORYBOARD.md` → `narrative.toml`, `audio_meta.json` → `audio/meta.json`, tokens →
   `lib/brand.blend`). **Metadata only** — that document's §3 timing recovery and §5 shot
   rebuilding are for imports and have no equivalent here.
3. Then A's steps 2–8, skipping what the harness already produced.
4. **Prefer `anchor` over absolute `start`** in `timeline.toml` (`timeline.md`). TTS gets
   re-synthesized; anchors survive it, absolute frames don't.

## Rendering and delivery — all three workflows

The deliverable is **video + title + description + thumbnail**, not video alone.

- `mise run comonteur:render` — renders `master.blend`'s timeline into `renders/` using the
  file's own output settings. Never overwrite a render the human is holding onto without
  asking.
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
