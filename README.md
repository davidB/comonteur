# comonteur

**Make videos with an AI agent — in Blender, where you can still edit them.**

`comonteur` lets Claude build video scenes, animations and timelines inside Blender, while
you keep working in Blender normally. You open the dope sheet and move a keyframe. Claude
reviews the shot, changes something else, and *doesn't overwrite your edit*.

It's the way Claude Code works with your code — you edit in your editor, the agent edits
the same files, nothing gets clobbered — applied to video.

> 🎬 **Watch the launch video** — made entirely with `comonteur`
> *(link pending — see milestone M6)*

> **co · monteur** — *monteur* is French for video editor. The *co* is you.

---

## Why

Agentic video tools generate videos from a prompt. That works until you want to change
one thing. Then you're prompting for a nudge you could have made by hand in two seconds,
or dropping into a code editor to hand-tune easing curves.

The fix isn't a better prompt. It's putting the agent and the human in the **same
editable project**, with clear rules about who owns what.

`comonteur` uses Blender because Blender gives you a real timeline, a real graph editor,
2D and 3D animation, Geometry Nodes, Grease Pencil and a video sequencer — all in one
file, all directly manipulable. What Blender doesn't give you is a mergeable project
file. That's the problem this project solves.

## What you get

- **Bidirectional editing.** Claude creates scenes you can edit. You create scenes Claude
  can review and edit. Neither destroys the other's work.
- **Real Blender output.** Animations are real F-curves on real data paths. Your dope
  sheet, graph editor and NLA work normally. Nothing is baked or locked.
- **Everything is attributable.** Every change Claude makes is journalled — what changed,
  when, from what to what. Reviewable and revertible, without reading a binary file.
- **Clean undo.** Claude's changes land as single labelled undo steps. `Ctrl+Z` does what
  you expect.
- **Your components, its assembly.** Build your brand's title cards and lower-thirds in
  Blender, mark them as assets, and Claude uses them as components with parameters.
- **Word-accurate captions and beat sync**, taken from TTS timing marks rather than
  speech recognition — so text reveals and cuts land exactly on the voiceover.

## Requirements

| | |
|---|---|
| **Blender** | 5.2 LTS (pinned — do not use 5.3+) |
| **Python** | 3.11+, via `uv` |
| **Tooling** | [`mise`](https://mise.jdx.dev/), [`uv`](https://docs.astral.sh/uv/) |
| **LLM client** | Claude Code (or any MCP-capable client) |
| **Media** | `ffmpeg` / `ffprobe` on `PATH` |
| **Git** | Git LFS (mandatory — `.blend` files and media) |

---

## ⚠️ Security

`comonteur` builds on Blender's official MCP server, which **executes AI-generated Python
inside Blender with no sandboxing**. Blender's own documentation is explicit about this:
code can delete your data or send it elsewhere.

Blender recommends running it on a virtual machine, or on a system without access to
sensitive information. Take that seriously. At minimum, work in a dedicated project
directory, keep the MCP socket bound to localhost, and don't run it on a machine holding
client data you can't afford to lose.

---

## Installation

### 1. Blender 5.2 LTS

Download from [blender.org](https://www.blender.org/download/lts/). Pinned deliberately —
LTS is supported until July 2028, and generated code is only reproducible against a fixed
API.

### 2. Blender's official MCP add-on

From [blender.org/lab/mcp-server](https://www.blender.org/lab/mcp-server/).

Drag the extension into Blender **twice** — the first drop adds the Blender Lab
repository, the second installs the add-on. (This also gets you update notifications.)
Alternatively, download the `.zip` and use *Install from Disk*.

### 3. The MCP server

For Claude Code and other clients supporting `.mcpb` bundles, grab the latest package
from the [releases page](https://projects.blender.org/lab/blender_mcp/releases).
Otherwise follow the [setup instructions](https://projects.blender.org/lab/blender_mcp/wiki/Setup).

### 4. comonteur

```bash
git clone <this-repo> && cd comonteur
mise install          # tool versions
uv sync               # dependencies
mise run install-addon # installs addon/comonteur into your Blender extensions dir
```

Enable **comonteur** in Blender: `Edit ▸ Preferences ▸ Add-ons`.

### 5. The Claude Code skill

```bash
cd your-video-project
npx skills add <this-repo>/skill
```

The skill teaches Claude the workflow and the helper library. It matters more than it
sounds: without it, Claude writes raw `bpy` — verbose, inconsistent, and outside the
ownership system.

---

## Quick start

```bash
mise run new-project my-launch-video
cd my-launch-video
blender master.blend     # leave this open
```

Then, in Claude Code:

```
Read production/narrative.yaml and build the opening shot:
a title card reading "Ship faster", fading up with a back-ease,
over the first 3 seconds of the voiceover.
```

Claude creates the scene, animates it, and renders a preview to check its own work.
Switch to Blender — it's there, live, fully editable.

Nudge the keyframe. Change the font. Then ask Claude to adjust the next shot. Your edit
survives.

## How collaboration works

Every piece of data carries an owner:

| Owner | Meaning |
|---|---|
| **agent** | Claude made it and can change it freely |
| **shared** | You've touched it — Claude works around what you changed |
| **human** | Yours. Claude only touches it when you explicitly ask |

When you edit something Claude made, it flips to **shared** automatically, and the
specific properties you changed are recorded as yours. Claude sees this and routes
around them.

Anything you made from scratch is never modified or deleted without you asking by name.

You can override ownership either way from the comonteur sidebar panel in Blender:
**Take ownership** or **Return to agent**.

### Reviewing what Claude did

```bash
mise run log            # human-readable journal
mise run log --batch b_0f3a
mise run revert b_0f3a  # undo one labelled batch
```

## Project layout

```
production/     script, assets, voiceover, captions — the "what"
lib/            your Blender components (brand, titles) — human-authored
lib/gen/        Claude-generated scenes — yours to edit too
spec/           timeline assembly
master.blend    the edit: links everything above
render/         outputs
.comonteur/       change journal
```

---

## Relation to HyperFrames

[HyperFrames](https://hyperframes.heygen.com/) (HeyGen, Apache 2.0) lets AI agents
compose videos by writing HTML, CSS and JS. It's two things in one: a **production
harness** (script → shot list → asset prep → TTS → captions → derush) and a **renderer**
(HTML/GSAP → frames).

`comonteur` **replaces the renderer** and can **keep the harness**.

The reason is editability. HTML/GSAP is agent-friendly because it's text, but it gives a
human no timeline — tuning means editing code or round-tripping through a web editor.
Blender gives you a genuine editing surface, at the cost of a binary project file, which
is what the ownership system here exists to solve.

If you already use HyperFrames, its upstream output fits `comonteur`'s production contract
with a thin adapter: shots, durations, assets, voiceover and word-level captions. Nothing
about rendering crosses that line.

HTML still has one honest advantage: **previz**. Browser rendering is instant and
Blender's isn't, so structure and pacing are cheaper to iterate in HTML. Lock the
structure there, then commit to Blender for the finish. Shot order and durations survive
the jump; per-shot timing largely doesn't.

You don't need HyperFrames at all. A folder of footage, a voiceover and a `.blend` full
of your own components is an equally valid starting point.

## Status

Early. Working through the milestones in [`SPEC.md`](./SPEC.md):

- [x] **M0** — Blender 5.2 API verification spike
- [x] **M1** — Walking skeleton: bidirectional edit without clobbering
- [x] **M2** — Production contract (assets, TTS, captions)
- [x] **M3** — Scene authoring (text, animation, components)
- [ ] **M4** — VSE assembly
- [ ] **M5** — Validation against a real HyperFrames project
- [ ] **M6** — Launch video, made with comonteur

M1 is the load-bearing one. If bidirectional editing doesn't hold up there, the design
needs rethinking — and that will be said out loud rather than papered over.

## Contributing

Not yet — the architecture is still moving. Issues and design discussion welcome.

## License

TBD. Apache 2.0 is the likely choice, matching HyperFrames.
