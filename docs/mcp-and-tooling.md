# comonteur — MCP layer and tooling policy

Part of the [comonteur spec](../SPEC.md). Section numbers match the original SPEC.md for
continuity with existing code comments (`SPEC.md §7...`, `§8...`).

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

**Language policy, in effect since M2 (no longer a future contingency):** Rust for
everything outside the Blender process; Python for everything inside it (`bpy` is
Python-only, so the addon never moves off Python). M2's production-contract ingest
(`narrative.yaml`, `assets/manifest.json`, captions — §5.3) has no Python-only
dependency and no need to run inside Blender, so it shipped as `cli/`, a Rust crate —
the start of the eventual M5.5 CLI rather than throwaway code it later replaces. Scope
as of M2 is **ingest-only**: `comonteur ingest {narrative,manifest,captions}`. `setup`,
`new`, and a CLI-side `doctor` are still M5.5 territory.

---

## 8. Tooling and language policy

- **Inside Blender (`addon/`) is pure Python** — `bpy` leaves no other option. `uv` for
  dependency and venv management, `ruff` for lint + format. Simpler to develop; the MCP
  ecosystem already requires Python and `uv`/`uvx` on the user's machine.
- **Outside Blender (`cli/`) is Rust**, per §7.5 — no `uv`/`uvx`/Python required to
  install or run it, which matters for the eventual M5.5 distribution story (single
  binary).
- The repo is a **mise monorepo**, and `pyproject.toml`/`uv.lock` moved with it: root
  `mise.toml` is orchestration only (`monorepo_root = true`, `[monorepo] config_roots =
  ["cli", "addon", "tests"]`, no tasks of its own beyond aggregation) and has **no
  Python project file anymore**. `addon/` and `tests/` each own a `pyproject.toml` +
  `mise.toml` + venv, exactly like `cli/` owns its `Cargo.toml` + `mise.toml`:
  `addon/` only needs `ruff` (it has no pytest suite of its own — see below); `tests/`
  needs `pytest` + `ruff`. Root `lint`/`autofix`/`test` are pure aggregators using the
  recursive glob `//...:<task>`, which picks up every config root automatically — adding
  a fourth workspace later needs no root `mise.toml` edit. Run `mise run cli:test` /
  `addon:lint` / `tests:test` from anywhere in the repo; root `ci` depends on `lint` +
  `test`, which fan out through the glob.
- Blender **5.2 LTS, pinned** (released 2026-07-14, supported to July 2028). Every line
  the agent emits is only reproducible against a pinned `bpy`. Do not track 5.3+.
- **mise is also the user-facing entry point**, not just the repo's dev tooling: setup,
  project initialization and every repeatable command are `comonteur:*` mise tasks the agent
  and the human run identically — see §8.2.
- Type hints throughout; `bpy` stubs (`fake-bpy-module`) for editor support.
- Tests: pure-logic Python modules (journal, easing map, spec parsing) unit-tested
  outside Blender via `tests/unit/`; narrative/manifest/captions ingest is Rust, tested
  via `cargo test` (`cli/src/*.rs`, inline `#[cfg(test)]`). Blender-dependent modules
  tested via `blender -b -P tests/run.py`.

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

There is exactly **one copy of every task**, and `init` installs all of them — `setup` and
`doctor` included, not just the day-to-day ones. Consequences, all wanted: a project can
repair its own toolchain (`mise run comonteur:setup`) without the human remembering where the
skill lives; `doctor` covers toolchain and project in one command instead of two half-doctors
with the same name; and `init` re-run on a live project tops up whatever a newer skill version
added. `skills/comonteur/scripts` is a symlink to that directory, giving the pre-project
bootstrap a short path (`bash <skill>/scripts/init`), and the repo's `mise-tasks/comonteur/*`
are symlinks to the same three files so contributors get `mise run comonteur:setup` for free.
One source of truth, no drift.

Each script therefore has to work in two contexts: as a mise task (`usage_*` from `#USAGE`
headers, `MISE_PROJECT_ROOT` set) and invoked directly by path before any tasks exist (plain
`$@`, `$PWD`). They also detect a checkout (`../../../../../cli/Cargo.toml` from the task dir)
and prefer it — no download, and the add-on is symlinked so edits stay live.

Delivery of the two binaries-ish artifacts is **release asset when present, pinned source
otherwise**: `scripts/setup --ref <tag>` tries the GitHub release binary (no Rust needed), and
falls back to `curl` of that tag's source tarball + `cargo install --path <tmp>/cli`, which
also yields `addon/comonteur` to copy into Blender's extensions dir. The fallback is what works
today, pre-1.0; the release path is what should work later, without changing the command
anyone types. Nothing is fetched unpinned, and the scaffold itself never touches the network —
templates ship inside the skill.

**Decision: mise is the only tool a user installs by hand**, plus Blender itself and Blender's
MCP add-on (both live inside Blender's own UI, out of reach of a package manager). Everything
else — the CLI, the comonteur add-on, the MCP server, `ffmpeg` — is installed by
`scripts/setup` and verified by `scripts/doctor` / `mise run comonteur:doctor`.

Blender is deliberately **not** pinned per-project even though mise's registry carries it
(`aqua:blender/blender`, 5.2.0 available): a ~300MB download per video project buys nothing
over the single user-wide install the MCP add-on already requires. `comonteur:doctor` checks
the version on PATH against the 5.2 pin instead, warning rather than failing on 5.3+.

**Every repeatable command is a task, and the agent calls the task, not the shell underneath.**
The tasks are ~10-line bash wrappers over `comonteur …` / `blender …`. The point is not
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
| `#USAGE arg`/`flag` | `init`, `setup`, `ingest-captions` — defaults, value validation (`choices`) and a generated `--help` per task, so the agent discovers a task's interface instead of guessing, and a bad argument fails at the boundary rather than inside a `blender -b` run |
| `#MISE dir="{{config_root}}"` | every project task — replaces a `cd "$MISE_PROJECT_ROOT"` line and makes a task correct when run from a subdirectory |
| `#MISE sources`/`outputs` | `ingest-manifest` (sha256 + `ffprobe` per asset) and `reconcile` — mise skips them when inputs are unchanged. `ingest-manifest` needs `"!assets/manifest.json"` in sources: the output lives in the directory it describes and would otherwise invalidate itself every run |
| `#MISE env` | `BLENDER_PIN = "5.2"` in `setup`/`doctor` — the pin appears once per script instead of in each path and comparison |
| `#MISE tools` | `ffmpeg` for `ingest-manifest`, `rust` for `setup`'s source-build fallback — the tool arrives with the task rather than being a prerequisite the user discovers by failing |

Deliberately not used: `alias` (a bare alias would break the `comonteur:` namespace rule
below) and `depends` (nothing here is a build graph — `reconcile` resolves YAML, applying it is
a separate step inside Blender). Interpreter stays bash: Python outside `addon/`/`tests/` would
break §8's language split, and these scripts are Rust's job at M5.5 anyway.

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

**Reversibility (§7.5).** M5.5's `comonteur init` / `comonteur doctor` subcommands supersede
these scripts by taking over the same task names; nothing else in the stack changes, and a
user's muscle memory doesn't either.
