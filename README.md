# comonteur

**Make videos with an AI agent — in Blender, where you can still edit them.**

`comonteur` lets an AI agent build video scenes, animations and timelines inside Blender,
while you keep working in Blender normally. You open the dope sheet and move a keyframe.
The agent reviews the shot, changes something else, and *doesn't overwrite your edit*.

It's the way a coding agent works with your code — you edit in your editor, the agent edits
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

- **Bidirectional editing.** The agent creates scenes you can edit. You create scenes it
  can review and edit. Neither destroys the other's work.
- **Real Blender output.** Animations are real F-curves on real data paths. Your dope
  sheet, graph editor and NLA work normally. Nothing is baked or locked.
- **Everything is attributable.** Every change the agent makes is journalled — what changed,
  when, from what to what. Reviewable and revertible, without reading a binary file.
- **Clean undo.** The agent's changes land as single labelled undo steps. `Ctrl+Z` does what
  you expect.
- **Your components, its assembly.** Build your brand's title cards and lower-thirds in
  Blender, mark them as assets, and the agent uses them as components with parameters.
- **Word-accurate captions and beat sync**, taken from TTS timing marks rather than
  speech recognition — so text reveals and cuts land exactly on the voiceover.

## Requirements

Install these yourself — everything else comes from `comonteur:install` (see
[Installation](#installation)):

| | |
|---|---|
| **Blender** | 5.2 LTS, [download](https://www.blender.org/download/lts/) — pinned, do not use 5.3+ |
| **[`mise`](https://mise.jdx.dev/getting-started.html)** | pins the rest of the tooling and runs every command |
| **An agent** | any MCP-capable coding agent that can read a skill/instructions directory; developed and tested with [Claude Code](https://claude.com/claude-code) |
| **`npx`** | Node 20+, to install the skill (`npx skills add …`) |

Pulled in for you: `uv`, the Blender add-on, Blender's MCP server, `ffmpeg` / `ffprobe`. Optional: Git + Git LFS if you want the project version-controlled (off by
default), `sox` if you record a voiceover locally.

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

You don't clone this repo. Get the four [requirements](#requirements) above, then install the
skill — the skill installs everything else, pinned, so commands behave the same on another
machine.

### 1. Prerequisites

```bash
curl https://mise.run | sh          # mise, if you don't have it
blender --version                   # expect 5.2.x — install from blender.org/download/lts
npx --version                       # Node 20+
claude --version                    # or whichever MCP-capable agent you use
```

### 2. The skill, then the project

```bash
mkdir my-video-project && cd my-video-project
npx skills add https://github.com/davidB/comonteur/skills/comonteur
uv run .claude/skills/comonteur/scripts/init.py .   # the only command you run by path
mise trust                                          # these task files are new to mise
mise run comonteur:install                          # both add-ons, the MCP server, then doctor
```

`init` scaffolds the project and its `comonteur:*` mise tasks; from then on everything —
installing and repairing the toolchain included — is `mise run comonteur:<task>` from inside
the project. `install` chains `install_addon` and `install_mcp` and finishes with a `doctor`
report of what's still missing. Nothing gets compiled or put on your `PATH`: every task is a
Python script that ships with the skill and runs in place via `uv`.

Want the add-on from a pinned tag rather than `main`?
`mise run comonteur:install_addon --ref v0.1.0` — no clone needed.

`mise trust` is a deliberate stop: mise refuses to run task files until you say they are yours
to run, and `init` will not clear that gate for you.

The skill itself is what teaches the agent the workflow and the helper library. It matters
more than it sounds: without it the agent writes raw `bpy` — verbose, inconsistent, and
outside the ownership system.

`npx skills add` writes to `.claude/skills/comonteur/` — Claude Code's convention, and just a
directory of Markdown. On another harness, point it at that directory (or symlink it where
your agent looks for instructions); nothing in the skill is Claude-specific.

### 3. Nothing, if Blender was installed first

`install` installs and enables both add-ons — comonteur and Blender's official
[MCP add-on](https://www.blender.org/lab/mcp-server/) — through
`blender --command extension`. Run it **with Blender closed**: add-ons are enabled from a
background Blender, and a GUI session exiting afterwards writes its own preferences over that.

Installed Blender only after running `install`? Re-run it. Prefer the GUI? Drag the MCP
extension into Blender **twice** (first drop adds the Blender Lab repository, second installs
the add-on) and tick comonteur in `Edit ▸ Preferences ▸ Add-ons`.

Re-run the doctor at any point — `mise run comonteur:doctor` — it's the single answer to
"is my setup right?".

---

## Workflows

You work in two places: **Blender**, and the **chat with your agent**. You don't run the
commands yourself — the agent runs the tooling for you (there's a table of what it runs at the
end of this section).

### The loop, whichever workflow you're in

1. Open `master.blend` in Blender and **leave it open**. The agent talks to that live session.
2. Ask for one shot at a time:

   ```
   Read narrative.toml and build the opening shot: a title card reading
   "Ship faster", fading up with a back-ease, over the first 3 seconds
   of the voiceover.
   ```

3. The agent builds `compositions/frames/<shot>.blend`, renders review frames into
   `.comonteur/review/`, looks at them, and reports what it did — including anything it
   routed around because you'd claimed it.
4. Switch to Blender. It's there, live, fully editable. Nudge the keyframe, change the
   font, drag the strip. That data flips to **shared** and the agent works around your edit.
5. Ask for the next shot, or for a change to this one. Your edits survive.
6. When the shots exist: *"assemble the timeline"* — the agent resolves `timeline.toml` and
   reconciles it into `master.blend`'s sequencer. Then *"render shots 1–3"*.
7. **You save the `.blend`.** The agent never does — saving under you could destroy unsaved
   work it can't see. It'll remind you.

What differs between workflows is only how the project *starts*.

### A. A video from scratch

Nothing upstream — a brief, your own components, maybe some footage and a voiceover.

1. Initialize the folder (the skill is already there from installation above):

   ```bash
   uv run .claude/skills/comonteur/scripts/init.py .
   ```

   That creates the [project layout](#project-layout) and the project's own `comonteur:*`
   mise tasks — from then on everything, `install` and `doctor` included, is
   `mise run comonteur:<task>` from inside the project. It's **add-only**: point it at a
   folder that already has your footage or another mise project and nothing there is touched;
   re-running it tops up what's missing.

   Git and Git LFS are **off** by default (`--git`, `--lfs`) — the agent asks before enabling
   them rather than deciding for you.

2. Tell the agent what the video is — *"a 90-second launch video for X, here's the script"* —
   and it fills in `narrative.toml`, validates it, and ingests your assets and voiceover.
3. Open `master.blend` (`mise run comonteur:edit`), and follow the loop above.

Details for the agent: [`skills/comonteur/references/workflows.md`](./skills/comonteur/references/workflows.md),
[`SKILL.md`](./skills/comonteur/SKILL.md).

### B. A video from an existing HyperFrames project folder

You shipped it in HTML and want an editable Blender project out of it.

Say *"import this HyperFrames project"*. The agent copies the tree (most of it maps 1:1),
translates the metadata (`STORYBOARD.md` → `narrative.toml`, `hyperframes.json` +
`index.html` → `timeline.toml`), converts the `.woff2` fonts Blender can't load, then
rebuilds each shot as a Blender scene and previews it.

**One thing it will stop and ask you.** HyperFrames has no timeline file — durations live
inside the HTML/JS. The agent recovers the cut list from three sources and shows it to you as
a table before building anything. Confirm it; everything downstream depends on it.

HTML → timeline is **not** lossless. The import ends with a list of what didn't survive:
timings it had to ask about, effects it approximated. That's honest, not a failure.

Details: [`references/hyperframes-import.md`](./skills/comonteur/references/hyperframes-import.md).
Status: M5, in progress.

### C. From scratch, with the HyperFrames harness

HyperFrames is two things: a production **harness** (script → shot list → asset prep → TTS
→ word-level captions) and an HTML **renderer**. Keep the harness, skip the renderer.

1. Run the harness for production prep only — its output already matches comonteur's
   production contract.
2. **No HTML compositions are written.** Shots are authored in Blender from the first
   frame, so there's no conversion step and nothing gets lost — unlike workflow B, which
   exists only because the HTML already happened.
3. Then the loop above. If there's a voiceover, the agent anchors shots to transcript words
   rather than absolute frames, so re-recording the VO doesn't invalidate the edit.

Details: [`docs/data-contracts.md`](./docs/data-contracts.md) §5.3–§5.4, and
[Relation to HyperFrames](#relation-to-hyperframes) below.

### Under the hood

Everything repeatable is a mise task, so the agent runs the same command you would — and you
can re-run any of it yourself. `mise tasks` is the menu.

`init` installs **one** set of tasks into the project, so every command — including the ones
that set the machine up — is re-runnable from the project afterwards:

| Task | What it does |
|---|---|
| `comonteur:install` | Install/repair everything, then doctor — chains the two below |
| `comonteur:init [dir] [--git] [--lfs]` | Initialize or top up a project — add-only, never overwrites |
| `comonteur:doctor` | Toolchain **and** project checks, one ✓/✗ list |
| `comonteur:ingest_narrative` | Validates `narrative.toml` |
| `comonteur:ingest_manifest` | `assets/` → `assets/manifest.json` (sha256 + `ffprobe`) |
| `comonteur:ingest_captions <in.json> [--kind whisper\|tts]` | Normalizes word-level timing |
| `comonteur:reconcile` | `timeline.toml` → resolved plan the add-on applies |
| `comonteur:edit` / `comonteur:render` | Open `master.blend` / render the timeline |
| `comonteur:install_addon [--ref <tag>]` | The comonteur add-on into Blender (symlinked from a checkout, fetched otherwise) |
| `comonteur:install_mcp` | Blender's MCP add-on **and** the MCP server it talks to |

Shipped as files in `mise-tasks/comonteur/` — every one of them is a self-contained,
stdlib-only Python script (`uv run --script`, no install step, Linux/macOS/Windows alike) —
a project that already has its own `mise.toml` and tasks keeps them, and the `comonteur:`
prefix stays out of the way of a `build` or `test` of your own. `--help` works on each one,
and the expensive ones (`ingest_manifest`, `reconcile`) skip themselves when their inputs
haven't changed.

Before a project exists, the same files are runnable straight from the installed skill —
`uv run .claude/skills/comonteur/scripts/{setup,init,doctor}.py` — which is the only
chicken-and-egg step. Contributors who clone the repo get `mise run comonteur:{setup,init,doctor}`
via symlinks to those same files: one copy, no drift.

## How collaboration works

Every piece of data carries an owner:

| Owner | Meaning |
|---|---|
| **agent** | the agent made it and can change it freely |
| **shared** | You've touched it — the agent works around what you changed |
| **human** | Yours. The agent only touches it when you explicitly ask |

When you edit something the agent made, it flips to **shared** automatically, and the
specific properties you changed are recorded as yours. The agent sees this and routes
around them.

Anything you made from scratch is never modified or deleted without you asking by name.

You can override ownership either way from the comonteur sidebar panel in Blender:
**Take ownership** or **Return to agent**.

### Reviewing what the agent did

Every change is in `.comonteur/journal.jsonl` — append-only JSONL, one line per property
written, with the before and after. Readable with any text tool; no binary diffing.

Changes are grouped into labelled batches, each landing as exactly one Blender undo step —
so `Ctrl+Z` undoes a whole batch, cleanly, and the label tells you which. Reverting an
older batch from the journal is designed but not yet built (M5.5); today, undo and the
journal's before/after values are what you have.

## Project layout

A video project — distinct from this repo:

```
mise.toml                pinned tools; mise-tasks/comonteur/ holds the comonteur:* tasks
narrative.toml           script/shot intent (STORYBOARD.md kept alongside)
assets/  audio/  captions/   media + word-level timing, manifest.json generated
lib/                     your Blender components (brand, titles) — human-authored, git-lfs
compositions/frames/     one .blend per shot, agent-generated, yours to edit too
timeline.toml            the assembly — authoritative for the edit, not for scene contents
master.blend             links the above into a VSE timeline
.comonteur/              journal, snapshot, review frames
renders/  thumbnail/  meta.json    deliverables
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
Blender's isn't, so structure and pacing are cheaper to iterate in HTML. If you want that,
lock the structure there and then import (workflow B) — but expect the round trip to cost
you: shot order and durations survive, per-shot timing largely doesn't. Workflow C skips
it deliberately, authoring in Blender from the first frame.

You don't need HyperFrames at all. A folder of footage, a voiceover and a `.blend` full
of your own components is an equally valid starting point.

## Status

Early. Working through the milestones in [`SPEC.md`](./SPEC.md):

- [x] **M0** — Blender 5.2 API verification spike
- [x] **M1** — Walking skeleton: bidirectional edit without clobbering
- [x] **M2** — Production contract (assets, TTS, captions)
- [x] **M3** — Scene authoring (text, animation, components)
- [x] **M4** — VSE assembly
- [ ] **M5** — Validation against a real HyperFrames project
- [ ] **M6** — Launch video, made with comonteur

M1 is the load-bearing one. If bidirectional editing doesn't hold up there, the design
needs rethinking — and that will be said out loud rather than papered over.

## Contributing

Not yet — the architecture is still moving. Issues and design discussion welcome.

## License

[GPL-3.0-or-later](LICENSE), for the whole repo — `addon/`, `skills/` and `tests/` alike.

Not a preference: the Blender extensions platform
[requires GPL-3.0-or-later for add-ons](https://docs.blender.org/manual/en/5.2/advanced/extensions/licenses.html),
and `addon/comonteur/` links `bpy`. The skill and its task scripts are technically separate
programs that could have stayed permissive, but one license across the repo beats explaining a
split.
