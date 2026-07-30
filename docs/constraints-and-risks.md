# comonteur — Constraints and open risks

Part of the [comonteur spec](../SPEC.md). Section numbers match the original SPEC.md for
continuity with existing code comments (`SPEC.md §11...`, `§12...`).

---

## 11. Constraints checklist

Cross-cutting; violating any of these produces bugs that are hard to attribute.

- `bpy` is **not thread-safe**. Socket thread queues; `bpy.app.timers` drains on the main
  thread.
- Prefer the data API over `bpy.ops`. Operators need context overrides and fail
  confusingly from timers.
- One labelled `undo_push` per batch. Defer while a modal operator runs.
- **Agent never saves the file.**
- Strings are not drivable → handler sync.
- No layout engine. Text fitting = measure `obj.dimensions` after a depsgraph update,
  iterate.
- Colour management: `view_transform = 'Standard'` for imported sRGB and 2D graphics.
- Alpha: PNG sequence or ProRes 4444. VP9-with-alpha WebM is unreliable in the VSE.
- Gitignore: `renders/`, `renders/BL_proxy/`, `*.blend1`, HyperFrames `renders/work-*/`.
- Fonts: Blender loads TTF/OTF only. Web assets ship `.woff2` and must be converted at
  ingest (`fonttools`).
- Time: fps lives in the spec and is resolved **once**. Never let two layers round
  independently.
- Coordinates: CSS is top-left/y-down/layout-px; VSE transform offsets are
  center-origin/y-up/project-px.
- Render budget: Workbench/OpenGL previews in the agent loop; full renders at the end,
  local, not CI.
- MCP socket is an RCE surface: localhost-only, and see §7.2.
- License: **GPL-3.0-or-later**, repo-wide. Forced by the extensions platform for add-ons; not a
  preference to revisit per-directory. `extension validate` does *not* check the SPDX id, so a
  wrong license passes CI silently — verify the manifest by eye.

---

## 12. Open risks

| Risk | Impact | Mitigation |
|---|---|---|
| Linked scenes unusable as VSE scene strips (M0.7) | Repo layout collapses; agent and human write the same file | Verify in M0. Fallback: single `master.blend` + LFS, rely on journal + provenance alone |
| Automatic provenance flip too noisy or too coarse | Core UX broken | M1 gates on this. Manual take-ownership operators exist regardless |
| Token cost of introspection on real scenes | Agent becomes unusable on non-trivial projects | Hard budgets in `introspect`; visual review preferred over structural |
| Blender 5.2 API drift in helper library | Silent breakage | Pinned version; `docs/M0-FINDINGS.md` as the record of what was verified |
| Journal grows unbounded | Slow, unreviewable | Rotate per session; snapshot compaction |
| Loss of rebuild-from-source | Unexplainable scenes | Journal + provenance are the deliberate substitute. Accepted trade — see §4.2 |
