# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`comonteur` lets an AI agent build video scenes/animations/timelines inside Blender while a
human keeps editing the same `.blend` normally — bidirectional editing without clobbering.
This is the tool's own repo (not a video project it generates — those have their own
generated `AGENTS.md`/`CLAUDE.md`, see `docs/data-contracts.md` §5.1b).

Read `SPEC.md` first if working on design/architecture — it's a short thesis/index, not the
full spec. It routes to:

- `docs/architecture.md` — provenance, journal, batch protocol (§4)
- `docs/data-contracts.md` — repo/project layout, `timeline.toml`, HyperFrames adapter (§5)
- `docs/library.md` — `addon/comonteur/` modules, asset/component system (§6, §9)
- `docs/mcp-and-tooling.md` — MCP transport, language/tooling policy (§7, §8)
- `docs/milestones.md` — M0–M6 plan (§10)
- `docs/constraints-and-risks.md` — cross-cutting rules and known risks (§11, §12)
- `docs/M0-FINDINGS.md` / `M1-FINDINGS.md` / `M3-FINDINGS.md` — verified Blender API behaviour

Code comments referencing `SPEC.md §N` resolve to whichever doc above now holds that section.

## Repo structure — a mise monorepo, Python on both sides of the Blender boundary

- `addon/` — the in-Blender library + Blender add-on (`addon/comonteur/`). Pure Python,
  `bpy`-locked. Own `pyproject.toml`/`mise.toml`/venv (ruff only, no pytest — nothing here
  is testable outside Blender).
- `skills/` — Claude Code skills, one directory per skill (`skills/comonteur/SKILL.md` +
  `references/` + `scripts/` + `templates/`), installable with
  `npx skills add <repo>/skills/<name>`. No build, no lint, not a mise config root. This is
  both what teaches an agent to call the library instead of writing raw `bpy` **and** the
  distribution unit users install — it carries the bootstrap scripts and the project
  scaffold, since no user clones this repo (§8.2). Keep it in sync when `addon/comonteur/`
  changes. Also holds **everything that runs outside the Blender process**: the ingest and
  reconcile logic lives in `templates/mise-tasks/comonteur/*.py`, one `uv run --script`
  Python file per task (there is no `comonteur` binary and nothing to install — see below).
- `tests/` — pure-logic Python unit tests (pytest) for modules with no `bpy` dependency
  (journal, paths, easing map, spec parsing) **and** for the task scripts, which it reaches
  through `tests/unit/_tasks.py`. Own `pyproject.toml`/`mise.toml`/venv; also owns the
  `ruff check` + `mypy` pass over the task scripts, since `skills/` is not a config root.
- Root `mise.toml` is orchestration only — `monorepo_root = true`, no Python project of its
  own. `lint`/`autofix`/`test`/`ci` fan out via `//...:<task>` across `addon/` and `tests/`
  automatically.

**Language policy**: Python everywhere. It used to be "Rust outside Blender, Python inside",
but `cli/` was 1151 lines of TOML/JSON-in, JSON-out with no performance requirement, and
shipping it meant maintaining a per-OS release matrix for a validator. It is now four mise
task scripts. Do not reintroduce a compiled tool for spec parsing.

**The wall the compiler used to enforce, now a rule**: `addon/comonteur/` never imports a
task script and never parses a spec file. Parsing, validation and anchor resolution belong to
the outside-Blender step — the add-on's input is the resolved plan, not the source document.
(`tomllib` is stdlib, so the add-on *could* read `timeline.toml`; that it can is not a reason
to. Importing a task script remains impossible either way: Blender's bundled interpreter
cannot see a uv environment.) The task scripts emit plain JSON; the add-on reads that with the
stdlib `json` module. Nothing crosses that line.

## Commands

Run from repo root (mise monorepo — these fan out to every config root):

```bash
mise run lint       # ruff (addon/, tests/) + ruff check & mypy over the task scripts
mise run autofix    # ruff --fix + format
mise run test       # pytest (tests/) — addon/ has no tests of its own
mise run ci         # lint + test
```

Or scope to one workspace: `mise run addon:lint`, `mise run tests:test`, etc.

`ruff format` deliberately does **not** run over the task scripts: the formatter rewrites
`#MISE`/`#USAGE` into `# MISE`/`# USAGE` and mise only recognizes the unspaced form, so
formatting them would silently strip every task's description, `dir`, `sources`/`outputs` and
arguments. `ruff check` and `mypy` are safe there (`E265` is not in the selected rule set).

Extension packaging (needs Blender 5.2 on `PATH`, so deliberately outside `lint`/`ci`):

```bash
mise run addon:validate   # manifest structure + copyright format (not the SPDX id)
mise run addon:build      # publishable zip into addon/build/, asserts LICENSE shipped
```

User-facing bootstrap (see `docs/mcp-and-tooling.md` §8.2):

```bash
mise run comonteur:setup            # one-time install: addon, MCP server, then doctor
mise run comonteur:init [dir] [--git] [--lfs]   # initialize a video project — add-only
mise run comonteur:doctor           # blender 5.2 / ffmpeg / uv / task scripts / addon / MCP
```

`setup` no longer installs anything for the outside-Blender side — the four task scripts ship
with the skill and run in place via `uv run --script`, so there is no release asset, no
toolchain to bootstrap, and updating the skill updates them.

**Every task has exactly one copy, in `skills/comonteur/templates/mise-tasks/comonteur/`** —
which is also what `init` installs into a project, so a project gets all nine tasks including
`setup`/`init`/`doctor` and can repair itself. `skills/comonteur/scripts` symlinks that
directory (short bootstrap path); `mise-tasks/comonteur/{setup,init,doctor}` symlink the three
files a checkout needs. Edit the template copy, never a symlink. Users are never expected to
clone this repo — they install the skill (`npx skills add`), so keep the scripts runnable *both*
as mise tasks (`usage_*` from `#USAGE`, `MISE_PROJECT_ROOT` set) and directly by path with
`$@`. Prefer mise headers (`dir`, `sources`/`outputs`, `env`, `tools`, `#USAGE`) over
hand-written equivalents — see §8.2 for which and why.

Anything written into a *user's* project is namespaced `comonteur:` (their project may have its
own `build`/`test`); project tasks ship as files under `mise-tasks/comonteur/` so an existing
`mise.toml` is never rewritten. `skills/` is Markdown + bash + TOML — no lint/test root, not in
`[monorepo] config_roots`.

The task scripts are `*.py` with underscored names (`ingest_narrative.py`) because mise strips
the `.py` from a file task's name and Python cannot import a hyphenated module — the tests
import them directly. Keep `#!/usr/bin/env -S uv run --script` plus a PEP 723 header on each;
all four are stdlib-only (`dependencies = []`) — keep it that way, `tomllib` and `json` cover
the whole surface.

Single test: `cd tests && uv run pytest unit/test_paths.py::test_name`

Dev-loop install (symlinks `addon/comonteur` into Blender's extensions dir so edits are
live without reinstalling):
```bash
mise run install-addon
```
It also enables the add-on, so run it with Blender closed — enabling happens in a background
Blender and a GUI session exiting afterwards overwrites those preferences.

`mise run install-mcp` fetches the official Blender MCP `.mcpb` server and registers it
with Claude Code (`claude mcp add blender ...`) — separate from the Blender-side add-on.

## Architecture

### Ownership: per-datablock provenance (docs/architecture.md §4.1)

Every datablock the agent creates carries `cmt_id` (stable logical id), `cmt_origin`
(`agent` | `human` | `shared`), `cmt_rev` (monotonic, bumped per agent batch). Rules:

- Untagged data is human data — never modified/deleted without an explicit instruction naming it.
- `agent`-owned: agent may mutate or delete freely.
- `shared`-owned (human has touched agent-created data): agent may mutate only paths it
  hasn't lost to a human edit, and may never delete it.
- `human`-owned: agent may mutate only when explicitly instructed in the current turn.

**The agent never regenerates** — its only operation on existing data is mutation. The
scene is the source of truth; the spec (`timeline.toml`) is an intent log, authoritative
only for timeline assembly, not for scene contents. A `depsgraph_update_post` handler
detects human edits to agent-owned data and flips `cmt_origin` to `shared`; fine-grained
"which paths did I lose" is derived on demand in `provenance.claimed_paths()`, not
observed in the handler (the handler must stay cheap — it runs on every depsgraph eval).

### The mutation journal (docs/architecture.md §4.4-4.5)

`.comonteur/journal.jsonl`, append-only, is the entire audit/diff/revert surface (there is
no rebuild-from-spec recovery path). Every agent write goes through `journal.set()` —
`exec_python` bypassing it produces untracked drift, surfaced by `introspect.drift()`.
Agent writes are grouped into a `journal.batch(...)` context manager: exactly one labelled
`bpy.ops.ed.undo_push()` per batch (never poison the human's undo stack), gated by
`batch_active()`. **The agent never saves the `.blend`** — save is always a human action.

### `addon/comonteur/` module map (docs/library.md §6)

| Module | Responsibility |
|---|---|
| `provenance.py` | tag / flip handler / `claimed_paths` / ownership queries / take-ownership operators |
| `journal.py` | `batch()` context manager, `set()`, JSONL, snapshot, revert |
| `scene.py` | `new_scene()` — deterministic baseline, never inherits `bpy.context.scene` state |
| `anim.py` | `tween`, `stagger`, easing map (GSAP-equivalent), F-curve helpers — real keyframes only, no baked/driver animation |
| `text.py` | text objects, styling, fit-to-box, per-character split |
| `library.py` | link `lib/*.blend` components and `compositions/frames/*.blend` scenes; asset catalog discovery |
| `introspect.py` | `outline`, `describe`, `animated_paths`, `find`, `drift` — progressive disclosure, token-budgeted, never dumps a full tree |
| `preview.py` | render frames for agent visual review (`.comonteur/review/`) |
| `ui.py` | sidebar panel (ownership override operators) |
| `doctor.py` | environment/setup checks |
| `paths.py`, `const.py` | shared path resolution / constants |

Reusable animation should become Actions instanced via NLA strips with a time offset, not
re-emitted keyframes. Components are Blender's own asset system (mark Scene/node
group/Action as an asset) — do not build a separate component registry.

### MCP transport (docs/mcp-and-tooling.md §7)

Uses the **official Blender Foundation MCP server** exclusively, via `execute_python` —
no provenance/batching/journaling exists in it, all of that lives in `addon/comonteur/`.
Raw `bpy` from the agent is not forbidden but is quarantined: effects show up in
`introspect.drift()` and must be promoted into the journal or discarded. Do not add calls
to other MCP tools from the official server, and do not fork it unless `execute_python`
turns out not to run on Blender's main thread (the documented hard trigger).

### Video project layout this tool operates on (docs/data-contracts.md §5.1b)

Distinct from this repo's own layout. A generated project has `lib/` (human-authored
components, git-lfs), `compositions/frames/*.blend` (one agent-generated scene per shot,
**linked** — not appended — into `master.blend` so it stays read-only there),
`timeline.toml` (assembly source of truth), and `.comonteur/journal.jsonl` +
`snapshot.json`. Don't confuse this with `addon/`, `skills/`, `tests/` which belong to the
tool itself.

## Python conventions

- All Python (`addon/`, `tests/`) must be type-hinted: function args, return types, and non-obvious variables.
- `bpy` has no type stubs in this project — use `typing.Any` for Blender RNA objects (Object, Scene, Context, etc.) rather than leaving them untyped.
- Enforced by ruff's `ANN` rule set (`addon/pyproject.toml`, `tests/pyproject.toml`); `ANN401` (disallow `Any`) is ignored since `bpy` forces `Any` for its dynamic types.

## Requirements pinned for reproducibility

Blender **5.2 LTS only** (do not track 5.3+) — generated code is only reproducible
against a fixed API. Third-party Blender add-ons need an explicit allowlist entry in
`docs/ADDONS.md` (name, version, why, what breaks without it); prefer asset libraries
(data) over add-on operators.

License is **GPL-3.0-or-later repo-wide** — required by the extensions platform for add-ons, so
do not "restore" Apache-2.0 when editing `blender_manifest.toml`. The GPL text exists twice on
purpose (root `LICENSE` and `addon/comonteur/LICENSE`): the extension builder skips symlinks, so a
symlinked copy would not ship in the zip. Verify with `mise run addon:build`, which asserts
`LICENSE` is inside the archive.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **comonteur** (697 symbols, 1048 relationships, 45 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/comonteur/context` | Codebase overview, check index freshness |
| `gitnexus://repo/comonteur/clusters` | All functional areas |
| `gitnexus://repo/comonteur/processes` | All execution flows |
| `gitnexus://repo/comonteur/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
