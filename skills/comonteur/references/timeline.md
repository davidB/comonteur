# Assembly — `timeline.yaml` → VSE strips

`timeline.yaml` is the **only** file you treat as desired state. It governs assembly
(what plays, when, for how long) and says nothing about what is inside a shot.

## Schema

```yaml
fps: 30
resolution: [1920, 1080]
shots:
  - id: shot-01
    source: {kind: scene, blend: compositions/frames/shot-01.blend, scene: GEN_hook}
    start: 0                       # absolute frames
    duration: 90                   # frames
  - id: shot-02
    source: {kind: movie, path: assets/broll_terminal.mp4}
    anchor: {word: "observability", occurrence: 1, offset: -0.2}
    duration: 120
    in: 45
    transition: {type: cross, duration: 0.4}
audio:
  - id: vo
    path: audio/narration.wav
    start: 0
```

- `start` **xor** `anchor` — one or the other, per shot and per audio track.
- `duration` and `in` are **frames**; `anchor.offset` and `transition.duration` are
  **seconds** (they are timed against the recording, not the edit grid).
- `transition` sits on a shot and crossfades it with the shot immediately before it.
  `cross` is the only type as of M4.
- Paths are relative to the project root.

Known gap: `in` is resolved into `in_frame` but `reconcile.apply()` does not
yet write it to the strip (`reconcile.py:141` reconciles `frame_start` and
`frame_final_duration` only). If a shot needs a media in-point today, say so rather than
assuming it took effect.

## The two-step: the task resolves, the addon applies

The addon never parses YAML and never reads a transcript. Always both steps, in order.

**1. Outside Blender** — validate, and resolve every anchor to an absolute frame:

```bash
mise run comonteur:reconcile
```

The task is a Python script (`mise-tasks/comonteur/reconcile.py`) and defaults to the right
paths: `timeline.yaml`, `audio/transcript.json` when that file exists, and
`.comonteur/timeline.resolved.json` for output. Running it directly by path works the same way,
and the flags are there if you need to override:

```bash
./mise-tasks/comonteur/reconcile.py --timeline timeline.yaml \
  --transcript audio/transcript.json -o .comonteur/timeline.resolved.json
```

A transcript is required if any shot or audio entry uses `anchor`.

The resolved JSON is plain: `{fps, resolution, shots: [{id, source, start_frame,
duration_frames, in_frame, transition: {kind, duration_frames}}], audio: [{id, path,
start_frame}]}`. No YAML, no anchors, no seconds.

**2. Inside Blender**, through `execute_python`:

```python
import json, os
try:
    from bl_ext.user_default import comonteur as cmt
except ImportError:
    import comonteur as cmt

root = os.path.dirname(bpy.data.filepath)
with open(os.path.join(root, ".comonteur", "timeline.resolved.json")) as f:
    resolved = json.load(f)

cmt.reconcile.apply(bpy.context.scene, resolved, root)
```

`apply()` opens its own `journal.batch("reconcile timeline")` — **do not wrap it in one**,
batches do not nest. Run it against `master.blend`'s scene; it creates the sequence editor
if there isn't one.

Then preview and tell the human to save.

## What `apply()` does

Three passes, all through `journal.set()`:

| Pass | Channel | Strip type |
|---|---|---|
| shots | 1 | `SCENE` (via `library.link_scene()`) or `MOVIE` |
| audio | 2 | `SOUND` |
| transitions | 3 | `CROSS` effect, `input1` = previous shot, `input2` = this shot |

Strips are matched by `cmt_id`, which is the shot's `id` (transitions use
`<shot-id>:transition`). So:

- id in the plan, not in the VSE → **create**
- in both → **update only the fields that changed and are not claimed**
- in the VSE, not in the plan → **delete only if agent-owned and unclaimed**

Renaming a shot's `id` is therefore a delete + create, losing every human tweak on that
strip. Don't rename ids to tidy them up.

## Reconcile is not exempt from provenance

"Authoritative for assembly" means authoritative for what you *propose*, not a licence to
clobber. If the human dragged a strip's duration in the timeline, that field is claimed and
reconcile **skips it** — it does not reset it to the YAML value. Report the skip; if the
YAML and the human disagree, that is a question for them, not a conflict for you to resolve.

One subtlety worth knowing: VSE strips are not ID datablocks, so the automatic
`agent → shared` origin flip never fires for a strip edit. Delete-safety here rests on
`claimed_paths()` — derived straight from the journal — not on `cmt_origin`
(`reconcile.py:50`).

## Anchors

A shot may be positioned by an absolute `start`, or by a word in the voiceover:

```yaml
anchor: {word: "observability", occurrence: 1, offset: -0.2}
```

This exists because **audio processing invalidates every absolute `start` in the
project** — silence removal, a re-record, a re-cut. Anchored shots survive: re-transcribe,
re-resolve, done.

Order of operations:

1. Capture anchors **before** any destructive audio edit.
2. Process audio.
3. Re-transcribe to word-level `audio/transcript.json`
   (`mise run comonteur:ingest_captions <input> --kind whisper` writes `captions/vo.json`;
   the reconcile step reads `audio/transcript.json`, so put it there).
4. `mise run comonteur:reconcile` → `cmt.reconcile.apply()`.

If an anchor word is missing, or its occurrence count changed, the task **fails loudly**.
That means the script has drifted from the recording. Stop and tell the human — do not
switch the shot to an absolute `start` to make the error go away.

Resolved anchor positions are journalled like any other agent write, so a human override of
`frame_start` is claimed normally and survives the next re-resolution.
