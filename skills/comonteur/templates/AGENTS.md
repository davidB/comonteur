# __PROJECT_NAME__

A comonteur video project: an AI agent builds scenes, animations and the timeline inside
Blender while a human edits the same `.blend` live. Nothing here gets regenerated — the
scene is the source of truth and the agent only mutates it.

## Read this first

The `comonteur` skill is the contract. Read `SKILL.md` before writing any `bpy` code
against this project, and `references/workflows.md` for the project-level order of work.
Not installed? `npx skills add https://github.com/davidB/comonteur/skills/comonteur`.

Raw `bpy` bypasses the ownership and journal system that makes the live human editing safe.

## This project

| | |
|---|---|
| **Video** | _one line: what this video is and who it's for_ |
| **fps / resolution** | see `timeline.toml` |
| **Voiceover** | _none / human-recorded / TTS_ |
| **Brand** | `lib/brand.blend` — colours, fonts, node groups, marked as assets |

`narrative.toml` is the intent, `timeline.toml` is the assembly, `compositions/frames/*.blend`
are the shots (one Blender scene each, linked read-only into `master.blend`).

## Commands

Everything repeatable is a mise task — `mise tasks` to list, and prefer them over raw
shell so the human can re-run exactly what you ran:

```
mise run comonteur:doctor              # toolchain + project checks
mise run comonteur:setup               # install/repair the toolchain
mise run comonteur:init                # top up this project's scaffold (add-only)
mise run comonteur:ingest_narrative    # validate narrative.toml
mise run comonteur:ingest_manifest     # assets/ -> assets/manifest.json
mise run comonteur:ingest_captions <in.json> [--kind whisper|tts]
mise run comonteur:reconcile           # timeline.toml -> .comonteur/timeline.resolved.json
mise run comonteur:edit                # open master.blend
mise run comonteur:render              # render the timeline to renders/
```

## Non-negotiable

- **Never save the `.blend`.** Saving is the human's action, always. Tell them to save.
- **Never regenerate.** Mutate; `scene.new_scene()` returning an existing scene is deliberate.
- **Untagged data is human data** — don't touch it unless the instruction names it.
- **Never claim a shot is done without reading a rendered frame of it.**
