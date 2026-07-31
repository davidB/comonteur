# comonteur — MCP layer and tooling policy

Part of the [comonteur spec](../SPEC.md). Section numbers match the original SPEC.md for
continuity with existing code comments (`SPEC.md §7...`, `§8...`).

---

## 7. MCP layer

**Use the official Blender Foundation MCP server.** Do not fork
`anan0110692/blender-mcp-vse` or any other unless a concrete need appears that cannot be
met from the helper library — record the reason if so.

- Add-on: Blender Lab extension, requires Blender 5.1+. `comonteur:install_mcp` installs it
  headlessly — `extension repo-add lab_blender_org --url https://lab.blender.org/` then
  `extension install mcp --sync --enable`, which is the same repository id and package the
  GUI produces. The GUI fallback is dragging the extension in **twice** (first drop adds the
  repository, second installs), or Install from Disk.
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
  `comonteur:*` mise tasks (`edit`, `render`, `doctor`).
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

**Language policy — Python on both sides (revised; superseded the Rust split).** M2 shipped
the production-contract ingest (`narrative.toml`, `assets/manifest.json`, captions — §5.3)
plus M4's `timeline.toml` resolution as `cli/`, a Rust crate, on the reasoning that
outside-Blender code should need no Python at install time. That reasoning did not survive
contact with distribution: the crate was 1151 lines of TOML/JSON-in, JSON-out with no
performance requirement, and shipping it meant a per-OS/arch release-asset matrix plus a
`cargo install` fallback that demanded a Rust toolchain the user had no other reason to have.

It is now **four `uv run --script` Python files**, one per subcommand, in
`skills/comonteur/templates/mise-tasks/comonteur/`:
`ingest_narrative.py`, `ingest_manifest.py`, `ingest_captions.py`, `reconcile.py`. The
orchestration tasks (`install`, `init`, `doctor`, `edit`, `render`, `convert_fonts`,
`install_addon`, `install_mcp`) followed later, from bash for the same reason a compiled CLI had to go: bash
hardcoded `~/.config/blender/...`, `readlink -f`, `curl | tar` and `sed -i`, none of which
exist on Windows, and it had no error reporting worth the name. There is no
`comonteur` binary, no release asset, and no install step — the scripts ship inside the skill
and run in place, so `npx skills add` updates the logic and the docs together. `uv` was already
required by `addon/` and `tests/`; Rust was the only toolchain in the repo with no second use.

What made this a collapse rather than a port: the CLI's argument surface had no users. Every
wrapper passed the same hardcoded paths (`narrative.toml`, `--timeline timeline.toml -o
.comonteur/timeline.resolved.json`), so `main.rs` was 140 lines of `clap` dispatch translating
project convention into flags mise was already supplying via `#USAGE`, `dir`, and
`sources`/`outputs`. Dissolving the CLI into tasks deleted that layer outright. The four
modules were independent — the single cross-module edge was a data shape (`captions::Word`),
which is `json.load(f)["words"]` on the Python side.

**The wall Rust was enforcing for free, now a written rule:** `addon/comonteur/` never imports
a task script and never parses a spec file. Spec parsing, validation and anchor resolution are
the outside step's job, so the add-on's input is the resolved plan, never the source document.
Blender's bundled interpreter *can* parse TOML (`tomllib` is stdlib) — that is not a licence to,
it just means the rule is now design rather than mechanism. Importing a task script remains
mechanically impossible: Blender's interpreter cannot see a uv environment. The scripts emit
plain JSON; the add-on reads it with the stdlib `json` module.

What was given up, honestly: the compiler over ~450 lines of anchor→frame arithmetic in
`reconcile.py`. Compensated with `mypy` over the scripts and the Rust `#[cfg(test)]` suite
ported to `tests/unit/` — the timeline cases carry the most coverage there for this reason.
`setup`, `new`, and a CLI-side `doctor` are no longer M5.5 CLI subcommands; `install` and
`doctor` already exist as tasks.

---

## 8. Tooling and language policy

- **Inside Blender (`addon/`) is pure Python** — `bpy` leaves no other option. `uv` for
  dependency and venv management, `ruff` for lint + format. Simpler to develop; the MCP
  ecosystem already requires Python and `uv`/`uvx` on the user's machine.
- **Outside Blender is Python too**, per §7.5 — `uv run --script` task files with PEP 723
  inline dependency headers, so each is self-contained and `uv` provisions its own
  interpreter on first run. All four are stdlib-only — `dependencies = []` on every one,
  since `tomllib` and `json` cover the whole surface. Of the tasks added since, only
  `convert_fonts` declares a dependency (`fonttools[woff]`): WOFF2 is Brotli-compressed and
  the stdlib has no decoder for it.
- The repo is a **mise monorepo**: root `mise.toml` is orchestration only
  (`monorepo_root = true`, `[monorepo] config_roots = ["addon", "tests"]`, no tasks of its
  own beyond aggregation) and has **no Python project file**. `addon/` and `tests/` each own
  a `pyproject.toml` + `mise.toml` + venv: `addon/` only needs `ruff` (it has no pytest suite
  of its own — see below); `tests/` needs `pytest` + `ruff` + `mypy`, and owns the lint and
  typecheck pass over the task scripts via `$TASKS_DIR`, since `skills/` is deliberately not
  a config root. Root `lint`/`autofix`/`test` are pure aggregators using the recursive glob
  `//...:<task>`, which picks up every config root automatically. Run `mise run addon:lint` /
  `tests:test` from anywhere in the repo; root `ci` depends on `lint` + `test`.
- **`ruff format` must never run over the task scripts.** The formatter rewrites `#MISE` and
  `#USAGE` into `# MISE`/`# USAGE`, and mise only recognizes the unspaced form — formatting
  them silently strips every task's description, `dir`, `sources`/`outputs` and arguments.
  `ruff check` and `mypy` are safe (`E265`, which wants that space, is not selected).
- Blender **5.2 LTS, pinned** (released 2026-07-14, supported to July 2028). Every line
  the agent emits is only reproducible against a pinned `bpy`. Do not track 5.3+.
- **mise is also the user-facing entry point**, not just the repo's dev tooling: setup,
  project initialization and every repeatable command are `comonteur:*` mise tasks the agent
  and the human run identically — see §8.2.
- Type hints throughout; `bpy` stubs (`fake-bpy-module`) for editor support.
- Tests: pure-logic Python modules (journal, easing map, spec parsing) unit-tested
  outside Blender via `tests/unit/`. The ingest and reconcile task scripts are tested there
  too — `tests/unit/_tasks.py` imports each one under a prefixed module name (`reconcile.py`
  exists on both sides of the Blender boundary, so a plain `import reconcile` would return
  whichever landed in `sys.modules` first). Blender-dependent modules tested via
  `blender -b -P tests/run.py`.

### 8.1 Third-party Blender add-ons — explicit allowlist

Add-ons are permitted but each requires an entry in `docs/ADDONS.md` with: name,
version, why, and what breaks without it. No implicit dependencies.

Selection principle: **prefer asset libraries (data) over add-ons (operators).** The
agent works through the data API; add-on operators need valid context and are awkward to
drive from a timer callback. Add-ons that ship reusable **node groups, assets or
components** are high value. Add-ons that only add UI operators are low value here.

Start with zero and add only on demonstrated need.

### 8.2 mise as the user-facing entry point — decision record

**No user is expected to clone this repository.** What a user installs is the skill
(`npx skills add <repo>/skills/comonteur`), so the skill is the distribution unit: it carries
the scaffold, `skills/comonteur/templates/`, whose `mise-tasks/comonteur/` **is** the task set.

**`init` is the only command ever run by path**, and it is the first thing a user runs after
`npx skills add`. Everything else — installing the toolchain included — is
`mise run comonteur:<task>` from inside the project it just created. That ordering is why
there is no bootstrap installer: a fresh project is *untrusted* (verified: `mise tasks` and
`mise run` both refuse until `mise trust`), so `init` scaffolds, prints `mise trust` and
`mise run comonteur:install`, and stops. It does not run the installation itself and does not
trust the files on the user's behalf — clearing that gate silently would be `init`'s to
answer for, and `init` is also the *top-up* command, re-run on live projects.

There is exactly **one copy of every task**, and `init` installs all of them — `install` and
`doctor` included, not just the day-to-day ones. Consequences, all wanted: a project can
repair its own toolchain (`mise run comonteur:install`) without the human remembering where the
skill lives; `doctor` covers toolchain and project in one command instead of two half-doctors
with the same name; and `init` re-run on a live project tops up whatever a newer skill version
added. `skills/comonteur/scripts` is a symlink to that directory, giving the pre-project
bootstrap a short path (`uv run <skill>/scripts/init.py`), and the repo's `mise-tasks/comonteur`
is a symlink to the same directory so contributors get the whole `comonteur:*` menu for free.
Two directory symlinks, one source of truth, and adding a task needs neither touched.

Each script therefore has to work in two contexts: as a mise task (`MISE_PROJECT_ROOT` set)
and invoked directly by path before any tasks exist (`$PWD`). mise forwards argv to a file
task *and* sets `usage_*` from `#USAGE`, so `argparse` over `sys.argv[1:]` serves both and
`#USAGE` is kept purely for what `mise tasks` shows. They also detect a checkout
(`addon/comonteur/blender_manifest.toml`, five levels up from the task dir) and prefer it — no
download, and the add-on is symlinked so edits stay live.

`_common.py` sits in the same directory and is deliberately **not** a task: no shebang, mode
644, which is what keeps mise from listing it (mise only picks up executable files). Siblings
import it as a plain module — `uv run --script` and a by-path run both put the script's own
directory first on `sys.path`. It carries `TaskError`/`die`, the ✓/✗/!/· printers, a
`subprocess` wrapper that reports the failing command and its stderr, `shutil.which` lookups,
`blender_py()` and `enable_addon()` (shared the moment `install_addon` and `install_mcp` both
needed it). `install` holds no logic at all — it is `#MISE depends`/`depends_post`/`wait_for`
headers over `install_addon`, `install_mcp` and `doctor`, which is what removed the duplicated
install logic bash had in two places. `install_addon` owns the whole delivery question
(checkout → symlink; `--source`/`--copy` → package; otherwise fetch `--ref` → package), so no
task above it needs to know how the add-on reaches a machine.

**Only one artifact still needs delivering: the add-on.** The ingest and reconcile tasks are
Python that ships inside the skill and runs in place, so there is nothing to download, compile,
or put on `PATH` for them — `npx skills add` is the whole update mechanism, and the scripts can
never skew from the docs and templates they ship beside. `install_addon --ref <tag>` fetches that tag's
source tarball (`urllib` + `tarfile`, `filter="data"`) only to obtain `addon/comonteur`,
packaged with `extension build` and installed with `extension install-file -r user_default -e`
(a checkout symlinks instead, to keep edits live; `install_addon.py` falls back to a copy where
symlinks are refused, as on Windows without Developer Mode). Where those files go is asked of
Blender — `--command extension repo-list` prints an absolute `directory:` per repository —
never assembled from a hardcoded `~/.config` path.

**Add-on management is `blender --command extension …` wherever that command reaches**: `build`,
`install-file -r user_default -e`, `repo-add`, `repo-list`, `install --sync --enable`. The one
gap, re-verified against 5.2's `--command extension --help`, is that its subcommand list
(server-generate/build/validate/list/sync/update/install/install-file/remove/repo-{list,add,remove})
has **no enable/disable**: `install-file -e` enables only what it just installed, and `--addons`
enables for a single launch without persisting. So the symlinked dev install — a directory that
appears in the repository without ever being "installed" — is the only place left using
`bpy.ops.preferences.addon_enable` + `wm.save_userpref()`, and the packaged path no longer
launches Blender a second time to enable what `-e` already did. `extension list` marks packages
`[installed]` but does not report enabled state, which is why `doctor` probes both through
`addon_utils.modules()` and `preferences.addons` in one `bpy` launch rather than parsing it. Nothing is fetched unpinned, and the scaffold never touches the network — templates ship
inside the skill.

**Decision: mise is the only tool a user installs by hand**, plus Blender itself (a ~300MB
GUI installer, out of reach of a package manager here). Everything else — `uv`, both
Blender add-ons via `blender --command extension`, the MCP server, `ffmpeg` — is installed by
`mise run comonteur:install` and verified by `mise run comonteur:doctor`.

Blender is deliberately **not** pinned per-project even though mise's registry carries it
(`aqua:blender/blender`, 5.2.0 available): a ~300MB download per video project buys nothing
over the single user-wide install the MCP add-on already requires. `comonteur:doctor` checks
the version on PATH against the 5.2 pin instead, warning rather than failing on 5.3+.

**Every repeatable command is a task, and the agent calls the task, not the shell underneath.**
The orchestration tasks are thin Python wrappers over `blender …` (`os.execvp` on POSIX so
Blender takes the terminal outright, `subprocess` + exit code on Windows); the ingest/reconcile
tasks are the implementation itself, not a wrapper over anything. The point is not
abstraction, it is symmetry: the human can re-run exactly what the agent ran, `mise tasks`
lists the whole surface without reading a chat transcript, and the pinned tools make the
result the same tomorrow and on another machine. An ad-hoc `blender -b … -a` buried in a
conversation is not a re-runnable artifact. This is the journal's argument (§4.4) applied to
the shell: the agent's actions must be inspectable and repeatable by the human, not merely
effective.

**Let mise's headers do the work, don't hand-roll it.** The tasks are
[file tasks](https://mise.jdx.dev/tasks/file-tasks.html) and use:

| Header | Where, and why |
|---|---|
| `#USAGE arg`/`flag` | `init`, `install_addon`, `ingest_captions` — defaults, value validation (`choices`) and a generated `--help` per task, so the agent discovers a task's interface instead of guessing, and a bad argument fails at the boundary rather than inside a `blender -b` run |
| `#MISE dir="{{config_root}}"` | every project task — replaces a `cd "$MISE_PROJECT_ROOT"` line and makes a task correct when run from a subdirectory |
| `#MISE sources`/`outputs` | `ingest_manifest` (sha256 + `ffprobe` per asset) and `reconcile` — mise skips them when inputs are unchanged. `ingest_manifest` needs `"!assets/manifest.json"` in sources: the output lives in the directory it describes and would otherwise invalidate itself every run |
| `#MISE env` | `BLENDER_MCP_VERSION` in `install_mcp` — a pinned version appears once per script instead of in each path and comparison |
| `#MISE depends`/`depends_post`/`wait_for` | `install` is nothing but these three: it depends on `install_addon` + `install_mcp`, `depends_post`s `doctor`, and `install_mcp` `wait_for`s `install_addon` so two background Blenders never race on `wm.save_userpref()`. Verified on file tasks. The catch, also verified: runtime args never reach a dependency — only statically written ones — which is why `--ref` lives on `install_addon` |
| `#MISE tools` | `ffmpeg` for `ingest_manifest`, `uv` for the four Python tasks — the tool arrives with the task rather than being a prerequisite the user discovers by failing |
| PEP 723 `# /// script` | the four Python tasks — the header travels with the file, so `uv run --script` provisions the interpreter on first run with no venv to manage and no lockfile to install. All four declare `dependencies = []`; keep it that way |

Deliberately not used: `alias` and `depends`. `alias` does not work in file tasks at all
(verified on mise 2026.7.10: the alias is parsed but never registered, and `mise run` on it
fails) — which is why the Python task files use underscores rather than keeping the old
`ingest-narrative` spelling, since Python cannot import a hyphenated module name and the tests
import these files directly. `depends` is unused because nothing here is a build graph:
`reconcile` resolves the timeline, and applying it is a separate step inside Blender.

**Task file naming.** mise strips a `.py` extension from a file task's name (verified:
`reconcile.py` → `comonteur:reconcile`), so the scripts keep clean task names while remaining
importable `.py` modules — which is also why every task carries the extension and an
underscored name. Do not rename them to extensionless files for looks: it would break the
tests' imports for no gain. `_common.py` is the exception that proves the rule — mode 644 and
no shebang, so mise skips it and it stays importable.

**The `comonteur:` namespace is binding.** A video project may be someone else's mise project
with its own `build`/`test`/`deploy`. Anything the comonteur stack writes into a user's
project is prefixed `comonteur:`; a bare task name is never claimed.

**Tasks ship as files, never by rewriting a user's config.**
`skills/comonteur/templates/mise-tasks/comonteur/*` is copied in; `mise.toml` is written only
when absent, and otherwise the `[tools]` snippet is printed for the human to add. That is what
makes initialization additive. The bootstrap scripts work both as mise tasks (`usage_*` from
`#USAGE` headers) and invoked directly with plain `$@`, since before `init` runs there are no
tasks yet.

**`comonteur:init`, not `new`.** Initializing a folder is add-only and idempotent: existing
files are kept and reported, never overwritten, never deleted; a folder holding footage, a
`.blend`, or another project is a normal input. Same rule as the provenance model in §4.1 —
the tool does not destroy what it did not create — and it is what makes workflow C (HyperFrames
harness output, no HTML) a one-command setup rather than a merge.

**git and Git LFS are opt-in** (`--git`, `--lfs`; LFS requires git), and the skill must ask
before passing either. `.blend` and media want LFS, but wanting is not deciding: the ask
happens at init because retrofitting LFS onto binaries already in history costs a rewrite.
`init --git` refuses inside an existing work tree rather than silently skipping.

**Reversibility (§7.5).** These scripts are the final form, not a placeholder for CLI
subcommands — see the language-policy note in §7.5. The task names are the stable interface;
an implementation may change language underneath without a user noticing.
