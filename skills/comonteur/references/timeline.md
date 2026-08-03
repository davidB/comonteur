# Assembly — `timeline.toml` → VSE strips

`timeline.toml` is the only file you treat as desired state. It governs assembly — what
plays, when, for how long — and says nothing about what's inside a shot.

## Schema

```toml
fps = 30
resolution = [1920, 1080]

[encode]
video_codec = "H265"        # optional, default "H265" — any scene.render.ffmpeg.codec identifier
video_container = "MPEG4"   # optional — auto-picked per codec when omitted
audio_codec = "AAC"          # optional — only set on the scene when given

[[shots]]
id = "shot-01"
source = {kind = "scene", blend = "compositions/frames/shot-01.blend", scene = "GEN_hook"}
start = 0                          # absolute frames
duration = 90                      # frames

[[shots]]
id = "shot-02"
source = {kind = "movie", path = "assets/broll_terminal.mp4"}
anchor = {word = "observability", occurrence = 1, offset = -0.2}
duration = 120
in = 45
transition = {type = "cross", duration = 0.4}

[[shots]]
id = "talking-head-03"
source = {kind = "movie", path = "raw/take3.mp4", with_audio = true}
start = 210
duration = 300

[[shots]]
id = "caption-card"
source = {kind = "scene", blend = "compositions/frames/caption-card.blend", scene = "GEN_caption"}
overlay_of = "talking-head-03"     # same start/duration as talking-head-03, channel picked for you

[[audio]]
id = "vo"
path = "audio/narration.wav"
start = 0
```

- `start` xor `anchor` — one or the other, per shot and per audio track. Not required on a
  shot that sets `overlay_of` — see below.
- `duration` and `in` are frames; `anchor.offset` and `transition.duration` are seconds (timed
  against the recording, not the edit grid).
- `overlay_of = "<shot-id>"` places a shot as an overlay above another shot's channel —
  e.g. a transparent caption card composited over a movie shot. It inherits `start`/`duration`
  from the target shot when omitted (either can still be set explicitly to override). No
  `channel` field exists to set directly: the addon picks the actual VSE channel for you (see
  "Channel layout" below) — a spec author expresses *which shot this overlays*, not *which
  channel number*.
- `transition` sits on a shot and crossfades it with the shot immediately before it. `cross` is
  the only type as of M4.
- `source.with_audio` (movie shots only, default `false`) keeps the file's own embedded audio
  synced to the video — for a take where lip-sync matters (dialogue/webcam captured in one
  file) and cutting the video (removing an "um", trimming silence) must move its audio along
  with it. Leave it `false` for plain B-roll: lighter to decode, and there's nothing to sync.
- Paths are relative to the project root.
- `[encode]` is optional; its values pass straight through to Blender's FFmpeg codec/format
  enums unvalidated — an invalid identifier fails at apply time, not at resolve time.

Known gap: `in` resolves to `in_frame` but `reconcile.apply()` doesn't yet write it to the
strip (`reconcile.py:250` reconciles `frame_start`, `frame_final_duration` and `channel`
only). If a shot needs a media in-point today, say so rather than assuming it took effect.

## The two-step: the task resolves, the addon applies

The addon never parses `timeline.toml` and never reads a transcript. Always both steps, in
order.

**1. Outside Blender** — validate, and resolve every anchor to an absolute frame:

```bash
mise run comonteur:reconcile
```

It defaults to the right paths — `timeline.toml`, `audio/transcript.json` when that file
exists, `.comonteur/timeline.resolved.json` for output — so the bare task is usually all you
need. `--help` lists the overrides:

```bash
mise run comonteur:reconcile --timeline timeline.toml \
  --transcript audio/transcript.json -o .comonteur/timeline.resolved.json
```

A transcript is required if any shot or audio entry uses `anchor`.

The resolved JSON is plain: `{fps, resolution, shots: [{id, source, start_frame,
duration_frames, in_frame, transition: {type, duration_frames}}], audio: [{id, path,
start_frame}]}`. No TOML, no anchors, no seconds. Note `transition.type` — `kind` is the key
inside `source`; mixing them up gets a silent fallback to a cross dissolve.

**A transitioned shot's `start_frame`/`duration_frames` are not its authored values.** A
`CROSS` effect only blends across the frame range where its two shots actually overlap, and
two strips can't share a channel (Blender neither rejects nor blends an overlap on the same
channel — see the channel table below). So the resolver shifts a transitioned shot's
`start_frame` earlier by `transition.duration_frames` and extends `duration_frames` by the
same amount: the authored `start` becomes the frame where the *previous* shot's untouched
footage ends, and the shot still settles into its authored length once the transition
finishes. Only the shot carrying the transition moves — this composes for free with
back-to-back-authored shots (next `start` == previous `start + duration`, the pattern used
above) without touching the previous shot at all.

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

`apply()` opens its own `journal.batch("reconcile timeline")` — don't wrap it in another;
`batch()` doesn't nest (see `../SKILL.md` Hard rules). Run it against `timeline.blend`'s scene;
it creates the sequence editor if there isn't one.

Then preview and tell the human to save.

## What `apply()` does

Four passes, all through `journal.set()`:

| Pass | Channel | Strip type |
|---|---|---|
| shots | 5 or 6, alternating by position | `SCENE` (via `library.link_scene()`) or `MOVIE` |
| audio (`[[audio]]`) | 1 | `SOUND` |
| shot audio (`source.with_audio`) | 1 | `SOUND`, id `<shot-id>:audio` |
| transitions | 7 | `CROSS` effect, `input1` = previous shot, `input2` = this shot |

Chapter/navigation markers were considered (one `TimelineMarker` per shot, for quick
navigation) but Blender 5.2's `TimelineMarker` does not support custom properties at all
(`marker.id_properties_ensure()` raises `TypeError: This type doesn't support IDProperties`,
verified directly — despite older API docs suggesting otherwise). Without a `cmt_id` tag,
markers can't get the create/update/delete provenance safety every other agent write here
relies on, so this isn't implemented; don't add untagged, unmanaged markers as a workaround.

### Channel layout

Bottom-up, matching pro post-production convention (dialogue/music/SFX kept together,
separate from video; overlay/titles on top) rather than interleaving audio between two video
passes:

```
1     CHANNEL_AUDIO        SOUND — voiceover/dialogue, and any with_audio shot's own audio
2-4   reserved              human audio (music/SFX/ambience) — no timeline.toml schema yet
5     CHANNEL_SHOTS_A       shots, alternating with channel 6
6     CHANNEL_SHOTS_B
7     CHANNEL_TRANSITIONS   CROSS effect, above both shot channels
8+    overlay                `overlay_of` shots, human video overlay (PiP, B-roll insert),
                             titles/subtitles/karaoke — addon-allocated, see below
```

Shots alternate channel by position (even index → 5, odd → 6) rather than sitting on one
fixed channel: a transitioned shot's frame range overlaps the previous shot's (see above), and
two strips can't usefully occupy the same channel at once — Blender neither rejects nor
blends that overlap, it just silently renders garbage. `channel` is therefore a synced field
for shots (alongside `frame_start`/`frame_final_duration`), so inserting or removing a shot —
which shifts every later shot's parity — moves the existing strips to their new channel on
the next reconcile, unless a human has since claimed that strip's `channel` by moving it
manually, in which case reconcile leaves it alone like any other claimed field. `overlay_of`
shots sit outside this alternation entirely and never shift it.

An `overlay_of` shot's channel is picked, not authored: the addon scans upward from above
its target's channel (and above 7, so it never lands on the shot/transition rows) for the
lowest channel with nothing occupying its time range — skipping both other agent strips and
any human content already sitting there. It's re-derived on every reconcile rather than
stored as a synced field, so it stays out of the way of whatever else is on those channels.

Strips are matched by `cmt_id`, which is the shot's `id` (transitions use
`<shot-id>:transition`, a `with_audio` shot's companion sound strip uses `<shot-id>:audio`).
So:

- id in the plan, not in the VSE → **create**
- in both → **update only the fields that changed and aren't claimed**
- in the VSE, not in the plan → **delete only if agent-owned and unclaimed**

Renaming a shot's `id` is therefore a delete + create, losing every human tweak on that
strip. Don't rename ids to tidy them up.

Strip names are set to `item["id"]` directly — deliberately, not something to "clean up" to a
prettier name. A stable, human-readable name (not an auto-incremented `Strip.004`) is the
same convention pro editors use, and it's what makes `<shot-id>:transition`/`<shot-id>:audio`
readable in the VSE strip list.

## Reconcile is not exempt from provenance

"Authoritative for assembly" means authoritative for what you propose, not a licence to
clobber. If the human dragged a strip's duration in the timeline, that field is claimed and
reconcile skips it — it doesn't reset it to the `timeline.toml` value. Report the skip; if
the spec and the human disagree, that's a question for them, not a conflict for you to
resolve.

One subtlety: VSE strips aren't ID datablocks, so the automatic `agent → shared` origin flip
never fires for a strip edit. Delete-safety here rests on `claimed_paths()` — derived
straight from the journal — not on `cmt_origin` (`reconcile.py:50`).

Another: a `with_audio` shot's companion sound strip isn't natively linked to its video strip
in Blender's sense — Blender only creates a true video/audio link when both come from one
`movie_strip_add` operator call. Here, "linked" means comonteur re-syncs both strips'
`frame_start`/`frame_final_duration` to the same values on every reconcile. If a human retrims
only one of the pair, that field is claimed on that strip alone and reconcile stops syncing
it — a deliberate split is respected, not fought back into sync.

A third: `[[audio]]` tracks and `with_audio` companions are both `SOUND` strips, reconciled
by two separate passes. Each pass's existing-strip scan is filtered to only the ids it could
have created (`<shot-id>:audio` suffix vs. everything else) — without that, each pass's
delete-safety check would see the *other* pass's strips as strays not in its own desired
list and delete them, mid-batch, right after they were created in the same reconcile. Any
future pass sharing a strip `type` with an existing one needs the same id-scoped filter.

## Anchors

A shot may be positioned by an absolute `start`, or by a word in the voiceover:

```toml
anchor = {word = "observability", occurrence = 1, offset = -0.2}
```

This exists because audio processing invalidates every absolute `start` in the project —
silence removal, a re-record, a re-cut. Anchored shots survive: re-transcribe, re-resolve,
done.

Order of operations:

1. Capture anchors before any destructive audio edit.
2. Process audio.
3. Re-transcribe to word-level `audio/transcript.json`
   (`mise run comonteur:ingest_captions <input> --kind whisper` writes `captions/vo.json`;
   the reconcile step reads `audio/transcript.json`, so put it there).
4. `mise run comonteur:reconcile` → `cmt.reconcile.apply()`.

If an anchor word is missing, or its occurrence count changed, the task fails loudly. That
means the script has drifted from the recording. Stop and tell the human — don't switch the
shot to an absolute `start` to make the error go away.

Resolved anchor positions are journalled like any other agent write, so a human override of
`frame_start` is claimed normally and survives the next re-resolution.
