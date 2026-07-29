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
