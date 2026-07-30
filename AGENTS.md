# comonteur — agent entry point

This is the comonteur tool's own repo (not a video project it generates — see
`docs/data-contracts.md` §5.1 for that distinction).

Read [`SPEC.md`](SPEC.md) first — it's now a short thesis/goals/non-goals overview plus
an index. Don't load the whole spec; follow the index to the one file that covers your
task:

- `docs/architecture.md` — provenance, journal, batch protocol (§4)
- `docs/data-contracts.md` — repo/project layout, `timeline.toml`, HyperFrames adapter (§5)
- `docs/library.md` — `addon/comonteur/` modules, asset/component system (§6, §9)
- `docs/mcp-and-tooling.md` — MCP transport, language/tooling policy (§7, §8)
- `docs/milestones.md` — M0–M6 plan (§10)
- `docs/constraints-and-risks.md` — cross-cutting rules and known risks (§11, §12)
- `docs/M0-FINDINGS.md` / `docs/M1-FINDINGS.md` — verified API behaviour so far

Code comments referencing `SPEC.md §N` still resolve — section numbers are unchanged,
only the file they live in moved.

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
