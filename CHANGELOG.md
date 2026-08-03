## [0.20260803.0] - 2026-08-03

### 🚀 Features

- *(timeline)* Add overlay_of for intent-based overlay-channel shots
- *(addon)* Add text.split_spans() for word/span-granularity multi-color text

### 🐛 Bug Fixes

- *(addon)* Reconcile set audio render when audio track
- *(addon)* Render preview frames via scene camera, not ambient viewport
- *(ci)* Install comonteur addon before running tests
- *(addon)* Stack card image plane above border/shadow, not below
- *(ci)* Install libegl1 for headless Blender EEVEE renders
- *(addon)* Round fractional keyframe frames in anim._keyframe
- *(addon)* Preserve color/position in split_chars, add alpha fades and reusable helpers
- *(addon)* Resolve library/VSE asset links portably, not against process cwd
- [**breaking**] Rename: master.blend -> timeline.blend
- [**breaking**] Rename `compositions/frames/` → `shots/`

### 🚜 Refactor

- Format

### ⚡ Performance

- *(scene)* Tune EEVEE samples/shadows for flat 2D scenes
## [0.20260802.0] - 2026-08-02

### 🚀 Features

- *(skill)* Prefer keyframes over drivers/baked anim, don't force it
- *(addon)* Add anim.idle_jitter(), text.measure(), and cmt.card.create()
- *(addon)* Multi-color inline text spans, karaoke/pulse/vignette effects
- *(timeline)* Add [encode] table for video/audio codec + container
- *(edit)* Auto-create master.blend on first mise run comonteur:edit
- *(skill)* Agent runs mise trust/install/edit itself instead of telling the human
- *(skill)* Remove active git/git-lfs management from init — dropped --git/--lfs subprocess calls from comonteur:init
- *(reconcile)* Pro VSE channel layout, auto-overlapping transitions, and with_audio movie sync
- *(reconcile)* Force VSE render output and set ffmpeg quality defaults
- *(skill)* Tighten preview cadence and add per-shot subagent delegation

### 🐛 Bug Fixes

- *(addon)* Sync scene fps/resolution/frame_end in reconcile.apply()
- *(ingest_manifest)* Fall back to sha256+path when ffprobe can't probe an asset (fonts, etc.) instead of aborting the whole manifest build
- *(addon)* Flat/unlit shading for kind="2d" scenes
- *(addon,skill)* Wire font-loading recipe + check_fonts(), document brand.blend read-back

### ⚙️ Miscellaneous Tasks

- *(release)* 0.20260802.0
## [0.20260801.1] - 2026-08-01

### 🐛 Bug Fixes

- *(release)* Fail cleanly and roll back local commit/tag on step failure
- *(addon)* Stop journal.set() from shadowing builtin set in annotations
- Build addon failed to check LICENSE when multiple zip (version) files

### 🚜 Refactor

- *(release)* Build everything before any git/gh call

### ⚙️ Miscellaneous Tasks

- Add a basic ci github workflow
- Add weekly renovate workflow for mise, uv, and github actions
- Declare uv & blender as top level tool to be cached by ci...
- *(release)* 0.20260801.1
## [0.20260801.0] - 2026-08-01

### 🚀 Features

- M0 API verification spike, MCP server install task
- M1 walking skeleton — journal, provenance, batch protocol
- M2 production-contract ingest — comonteur CLI (Rust)
- M3 Basic Scene authoring (inspired by HTML+GSAP on hyperframes)
- VSE assembly — reconcile.py, timeline.yaml resolution, transitions
- Mise-driven setup and additive project init, shipped in the skill
- *(setup)* Install and enable both Blender add-ons headlessly
- *(tasks)* Add comonteur:convert_fonts to unwrap woff/woff2 into ttf/otf
- *(release)* Add version scheme and one-shot release task for addon/skill/mise-tasks zips

### 🐛 Bug Fixes

- *(skills)* Move the project AGENTS.md/CLAUDE.md contract into the skill
- *(addon)* Repair eight bugs the skill documented as working
- *(skills)* Correct the agent contract and make its claims testable
- In skill doesn't considere that the user as `uv` preinstalled, but `mise` (if not skill request user to install it)

### 💼 Other

- From discussion with Claude/Opus 5

### 🚜 Refactor

- Move to a monorepo to prepare introduction of cli
- *(deps)* Allow patch update of version in cli
- Format
- Add type annotation into python code
- [**breaking**] Dissolve the Rust CLI into uv+Python mise tasks
- [**breaking**] Switch narrative/timeline spec files from YAML to TOML
- [**breaking**] Rewrite the remaining bash tasks in Python, replace setup with comonteur:install

### 📚 Documentation

- Split SPEC.md into focused files, add AGENTS.md entry point
- *(skill)* Add skills/comonteur — the Claude Code skill
- *(readme,skill)* Document the three video workflows, add references/workflows.md
- Update README to be more agent-neutral
- Drop the last `comonteur` CLI references from skills and instructions
- *(skills)* Trim comonteur skill for token cost, add skill-content conventions
- *(skills)* Replace bare A/B/C workflow labels with descriptive slugs in workflows.md

### 🧪 Testing

- Group tests by marker and widen tests/ past pure logic

### ⚙️ Miscellaneous Tasks

- Prepare tool for python development
- Enable gitnexus
- Update CLAUDE.md
- [**breaking**] Relicense to GPL-3.0-or-later, add extension validate/build tasks
- Untrack gitnexus-generated skills so skill installers don't propose them
- Gitnexus analyze
- *(release)* 0.20260801.0
