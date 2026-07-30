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
mise run comonteur:init [dir] [--git] [--lfs]   # initialize a video project — add-only
mise run comonteur:install          # both Blender add-ons + MCP server, then doctor
mise run comonteur:doctor           # blender 5.2 / ffmpeg / uv / task scripts / addon / MCP
```

`init` is the **only** command ever run by path (`uv run <skill>/scripts/init.py`), and it is
the first thing a user runs after `npx skills add`. It scaffolds, then stops and prints
`mise trust` + `mise run comonteur:install`: a fresh project is untrusted, mise refuses to run
its task files until told to, and `init` does not clear that gate for the user — it is also
the *top-up* command, re-run on live projects. Everything after it is `mise run comonteur:*`.

Nothing outside Blender is installed by any of this — every task script ships with the skill
and runs in place via `uv run --script`, so there is no release asset and no toolchain to
bootstrap. The add-on is the one artifact still delivered, and `install_addon` owns that
whole question (checkout → symlink; `--source`/`--copy` → package; otherwise fetch `--ref`).

**Every task has exactly one copy, in `skills/comonteur/templates/mise-tasks/comonteur/`** —
which is also what `init` installs into a project, so a project gets all twelve tasks including
`install`/`init`/`doctor`/`install_*` and can repair itself. Two directory symlinks point at that
one copy: `skills/comonteur/scripts` (short bootstrap path) and `mise-tasks/comonteur` (so a
checkout gets the whole `comonteur:*` menu). Edit the template copy, never a symlink; adding a
task needs no new symlink. Users are never expected to clone this repo — they install the skill
(`npx skills add`), so keep the scripts runnable *both* as mise tasks (`MISE_PROJECT_ROOT` set)
and directly by path. mise forwards argv to a file task *and* sets `usage_*` from `#USAGE`, so
`argparse` over `sys.argv[1:]` covers both — `#USAGE` stays for `mise tasks`' help. Prefer mise
headers (`dir`, `sources`/`outputs`, `env`, `tools`, `#USAGE`) over hand-written equivalents —
see §8.2 for which and why.

`_common.py` is the one file in that directory that is *not* a task: no shebang and mode 644,
which is exactly what keeps mise from listing it. Siblings reach it with `import _common`
(the script's own directory is first on `sys.path` under `uv run --script` and by-path runs).
It holds `TaskError`/`die`, the ✓/✗/!/· printers, `run()`, `require()`, `blender_py()`,
`enable_addon()` and path resolution — put a helper there only once a second script needs it.

Anything written into a *user's* project is namespaced `comonteur:` (their project may have its
own `build`/`test`); project tasks ship as files under `mise-tasks/comonteur/` so an existing
`mise.toml` is never rewritten. `skills/` is Markdown + Python + TOML — no lint/test root, not
in `[monorepo] config_roots`.

The task scripts are `*.py` with underscored names (`ingest_narrative.py`) because mise strips
the `.py` from a file task's name and Python cannot import a hyphenated module — the tests
import them directly. Keep `#!/usr/bin/env -S uv run --script` plus a PEP 723 header on each;
all of them are stdlib-only (`dependencies = []`) — keep it that way. There is no bash left
here: shelling out is `subprocess` with a list, tool lookup is `shutil.which` (PATHEXT on
Windows), archives are `tarfile`/`zipfile`, downloads are `urllib.request`, and no path under
`~/.config/blender/...` is ever hardcoded — `install_addon.py` asks Blender where its
extensions live, which is what makes macOS and Windows work.

Single test: `cd tests && uv run pytest unit/test_paths.py::test_name`

Dev-loop install (symlinks `addon/comonteur` into Blender's extensions dir so edits are
live without reinstalling):
```bash
mise run comonteur:install_addon
```
It also enables the add-on, so run it with Blender closed — enabling happens in a background
Blender and a GUI session exiting afterwards overwrites those preferences.

**Footgun:** Blender has one `user_default/comonteur`, so running `comonteur:install` (or
`install_addon`) from a *video project* rather than this checkout replaces that symlink with a
packaged build fetched from `--ref` (default `main`) — your working tree stops being what
Blender loads, silently. Re-run `mise run comonteur:install_addon` **from this repo** to get
the symlink back; `ls -l ~/.config/blender/5.2/extensions/user_default/` tells you which you
have.

`mise run comonteur:install_mcp` does both MCP halves, which are useless apart: the
Blender-side add-on from the Blender Lab repo (`--command extension repo-add` + `install
--sync --enable`, no hand-rolled download) and the `.mcpb` server registered with Claude Code
(`claude mcp add blender ...`).
`mise run comonteur:install` chains both and is **headers only** — `#MISE depends`,
`depends_post=["comonteur:doctor"]`, and `wait_for` on `install_mcp` so two background
Blenders never race on `wm.save_userpref()`. All three headers work on file tasks (verified).
The catch, also verified: runtime args never reach a dependency (only statically written ones
do), which is why `--ref` lives on `install_addon` and `install` takes no arguments. `depends`
also does nothing in a by-path run — fine, because `init`, not `install`, is the bootstrap.

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
