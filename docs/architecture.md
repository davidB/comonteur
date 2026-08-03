# comonteur — Core architecture

Part of the [comonteur spec](../SPEC.md). Section numbers match the original SPEC.md for
continuity with existing code comments (`SPEC.md §4...`).

---

## 4. Core architecture

### 4.1 Ownership is per-datablock provenance

Field-level locking was considered and rejected: it works for VSE strips, whose
properties are enumerable, but does not scale to objects, node trees, actions, grease
pencil layers, or arbitrary RNA. Strict scene-level partition (agent scenes vs human
scenes, neither looking inside the other) was also rejected — it contradicts G1 and G2.

Every datablock the agent creates carries:

| Property      | Type  | Meaning |
|---------------|-------|---------|
| `cmt_id`      | str   | Stable logical id, e.g. `shot-03.lower-third`. Survives renames. |
| `cmt_origin`  | str   | `agent` \| `human` \| `shared` |
| `cmt_rev`     | int   | Monotonic, bumped on each agent batch that touches this id |

Rules:

- **Untagged data is human data.** Never modified, never deleted, without an explicit
  instruction naming it.
- `origin == "agent"` — agent may mutate or delete freely.
- `origin == "shared"` — human has touched it. Agent may mutate only paths **not** in
  the claimed set (§4.3), and may **never** delete it.
- `origin == "human"` — agent may read and may mutate only when explicitly instructed
  in the current turn. Never on its own initiative.

Applies to: Scene, Object, Collection, Action, NodeTree, Material, GreasePencil, Text,
and VSE strips (**verify strips accept custom properties — M0.1**).

### 4.2 The agent never regenerates

Direct consequence of G1. If the human can edit `GEN_lower_third_03`, then regenerating
it destroys their work. The agent's only operation on existing data is **mutation**.

Reconcile therefore means: update agent-owned data still present in spec, remove
agent-owned data dropped from spec, leave everything else untouched.

**The scene is the source of truth. The spec is an intent log** — authoritative for
timeline assembly only (§5.2). This is the central trade of the design: reviewability is
bought back by the journal (§4.4), not by the ability to rebuild.

### 4.3 Automatic provenance flip

A `depsgraph_update_post` handler detects human edits to agent-owned data.

```python
@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph):
    if journal.batch_active():
        return                      # agent's own writes — not a human edit
    for upd in depsgraph.updates:
        id_ = getattr(upd.id, "original", upd.id)
        if id_.get("cmt_origin") == "agent":
            id_["cmt_origin"] = "shared"
            journal.record_flip(id_)
```

**Known limitation, do not paper over it:** `DepsgraphUpdate` exposes `is_updated_geometry`,
`is_updated_transform`, `is_updated_shading` — it does **not** report which RNA path
changed. So the handler can only flip coarsely.

Fine-grained claimed paths are **derived, not observed**:

```
claimed_paths(id) = { p : p ∈ journal.paths_written_by_agent(id)
                          ∧ resolve(p) != journal.last_agent_value(id, p) }
```

This works because the agent only needs to know which of *its own* paths it has lost.
Compute on demand in `provenance.claimed_paths()`, not in the handler — the handler must
stay cheap; it runs on every depsgraph evaluation.

Risks to validate in M0: handler noise (does it fire on selection-only changes?),
performance with many datablocks, correctness of `upd.id.original` for linked data.
A manual `Take ownership` / `Return to agent` operator pair in the sidebar is required
regardless, as an override.

### 4.4 The mutation journal

Mandatory. Since rebuild is no longer the recovery mechanism, the journal is the entire
audit / diff / revert surface.

`.comonteur/journal.jsonl`, append-only:

```json
{"ts":"2026-07-29T10:31:02Z","batch":"b_0f3a","actor":"agent","op":"set",
 "target":"bpy.data.scenes['GEN_lower_third_03'].objects['Title']","path":"location[1]",
 "old":0.0,"new":0.34}
{"ts":"2026-07-29T10:33:41Z","batch":null,"actor":"human","op":"flip",
 "target":"bpy.data.scenes['GEN_lower_third_03'].objects['Title']",
 "from":"agent","to":"shared"}
```

Every agent write goes through `journal.set()` — there is no other sanctioned path.
`exec_python` bypassing it produces **untracked drift**, surfaced by
`introspect.drift()` as the equivalent of `git status`, to be promoted into the journal
or discarded.

### 4.5 Batch protocol

```python
with journal.batch("retime shot-03"):
    anim.tween(...)
    cmt.set(obj, "location", ...)
# on exit: flush JSONL, bump cmt_rev, bpy.ops.ed.undo_push(message="comonteur: retime shot-03")
```

- Exactly **one** `undo_push` per batch, labelled. Without this the agent poisons the
  human's undo stack and the tool becomes unusable.
- `batch_active()` gates the provenance handler.
- Defer if a modal operator is running (transform/grab). Queue and retry.
- **The agent never saves the `.blend`.** Save is a human action, always. The one
  exception: `comonteur:edit` creates and saves a brand-new `timeline.blend` when none
  exists yet — nothing to clobber. Every later `edit`/`render` run still refuses to
  re-save an existing file.
