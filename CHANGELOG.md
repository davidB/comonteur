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
