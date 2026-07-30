# comonteur — Technical Specification

> **Name: `comonteur`.** From the French *monteur* (video editor) plus *co-*, as in
> co-pilot / coworker. Verified unclaimed on PyPI, crates.io and npm, with no GitHub
> repositories of that name (checked 2026-07-29).
>
> Derive everything from a **single constant** — package name, custom-property prefix
> (`cmt_`), addon id, journal filename, CLI name. A rename must remain a one-line change,
> not a find-replace across the tree.

Status: **draft for implementation**. Target reader: Claude Code, working locally.
Author context: distilled from a design discussion; see `docs/DESIGN-RATIONALE.md`
(to be written from this spec's "Why" notes).

This document is split across files so a session only needs to load the part relevant to
its task — see the index below. Section numbers are preserved across files (e.g. §4 lives
in `docs/architecture.md`), so existing `SPEC.md §N` references in code comments still
resolve.

---

## 1. Thesis

Build a video production system in which an **AI agent and a human edit the same
Blender project, in both directions, without either destroying the other's work.**

This is the Claude Code collaboration property — human edits files in their editor,
agent edits the same files, git mediates — transposed from text files to a `.blend`,
which is binary, unmergeable, and unreadable to an agent without a Python round-trip.

Everything else in this document exists to manufacture that property.

---

## 2. Goals

- **G1** Agent creates scenes (2D text, motion graphics, 3D) that the human can open in
  Blender and edit with the full normal toolset — dope sheet, graph editor, viewport.
- **G2** Agent can review and edit scenes the human authored, without needing to
  comprehend them in full.
- **G3** Neither party silently clobbers the other. Every agent mutation is attributable,
  reviewable and revertible.
- **G4** Human-in-the-loop is the normal mode: a running Blender session with a human
  attached. Headless is for CI and batch render only.
- **G5** Production upstream (script, storyboard, TTS, captions, assets) is pluggable —
  HyperFrames, a bespoke harness, or a human with a folder of footage all satisfy the
  same contract.

## 3. Non-goals

Explicitly rejected during design. Do not reintroduce without a decision record.

- **NG1** HTML/CSS/JS/GSAP anywhere in the final render path.
- **NG2** Transpiling HTML/GSAP into Blender.
- **NG3** A two-backend intermediate representation (dropped once HTML ceased to be a
  renderer — an intersection format would cap expressiveness at the browser's).
- **NG4** A third-party "video orchestrator". Claude Code + a skill + the Blender MCP
  server *is* the orchestrator.
- **NG5** Real-time concurrent multi-writer. Turn-taking is sufficient and much simpler.
- **NG6** A general-purpose Blender agent. This is video production, scoped.
- **NG7** A custom MCP server (for now — see `docs/mcp-and-tooling.md` §7).

---

## Document index

| File | Sections | Read when... |
|---|---|---|
| [`docs/architecture.md`](docs/architecture.md) | §4 | Working on provenance, the journal, or the batch protocol |
| [`docs/data-contracts.md`](docs/data-contracts.md) | §5 | Working on repo/project layout, `timeline.yaml`, the HyperFrames adapter, or reference projects |
| [`docs/library.md`](docs/library.md) | §6, §9 | Working inside `addon/comonteur/` (any module) or the asset/component system |
| [`docs/mcp-and-tooling.md`](docs/mcp-and-tooling.md) | §7, §8 | Working on the MCP transport, the user-facing entry point (mise tasks, §8.2), or language/tooling/dependency choices |
| [`docs/milestones.md`](docs/milestones.md) | §10 | Planning or checking progress against M0–M6 |
| [`docs/constraints-and-risks.md`](docs/constraints-and-risks.md) | §11, §12 | Sanity-checking a change against cross-cutting rules, or reviewing known risks |
| [`docs/M0-FINDINGS.md`](docs/M0-FINDINGS.md) | — | Results of the M0 API verification spike |
| [`docs/M1-FINDINGS.md`](docs/M1-FINDINGS.md) | — | Results of the M1 walking skeleton |
| [`AGENTS.md`](AGENTS.md) | — | Start here in a fresh session on this repo |
