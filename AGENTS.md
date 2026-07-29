# comonteur — agent entry point

This is the comonteur tool's own repo (not a video project it generates — see
`docs/data-contracts.md` §5.1 for that distinction).

Read [`SPEC.md`](SPEC.md) first — it's now a short thesis/goals/non-goals overview plus
an index. Don't load the whole spec; follow the index to the one file that covers your
task:

- `docs/architecture.md` — provenance, journal, batch protocol (§4)
- `docs/data-contracts.md` — repo/project layout, `timeline.yaml`, HyperFrames adapter (§5)
- `docs/library.md` — `addon/comonteur/` modules, asset/component system (§6, §9)
- `docs/mcp-and-tooling.md` — MCP transport, language/tooling policy (§7, §8)
- `docs/milestones.md` — M0–M6 plan (§10)
- `docs/constraints-and-risks.md` — cross-cutting rules and known risks (§11, §12)
- `docs/M0-FINDINGS.md` / `docs/M1-FINDINGS.md` — verified API behaviour so far

Code comments referencing `SPEC.md §N` still resolve — section numbers are unchanged,
only the file they live in moved.
