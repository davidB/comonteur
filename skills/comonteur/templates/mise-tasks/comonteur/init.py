#!/usr/bin/env -S uv run --script
#MISE description="Initialize a video project folder (additive, never overwrites)"
#USAGE arg "<dir>" help="project folder — created if missing, never overwritten" default="."
#USAGE flag "--git" help="git init (refused if already inside a work tree)"
#USAGE flag "--lfs" help="track .blend and media with Git LFS (needs --git)"
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Initialize a video project folder (docs/data-contracts.md §5.1b).

Add-only and idempotent: the folder may already hold footage, a `.blend`, or another mise
project. Existing files are kept, never overwritten and never deleted — the same rule the
provenance model applies inside Blender (docs/architecture.md §4.1).

These task files ARE the template: this script lives in the very directory it installs
(`skills/comonteur/templates/mise-tasks/comonteur/`), so a project ends up with every task
including this one — re-runnable by the human or the agent to fix or top up a project.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from _common import TaskError, die, tasks_dir

# Copied verbatim if absent. `mise.toml` is deliberately not here — see plan().
# No `AGENTS.md`/`CLAUDE.md`: the agent contract lives in the skill (`SKILL.md` and
# `references/`), which is what an agent actually loads. A project's own agent-instruction
# files are the human's, and comonteur never writes or edits them.
ROOT_FILES = [
    "narrative.toml",
    "timeline.toml",
    "meta.json",
    ".gitignore",
]

DIRS = [
    "assets",
    "audio",
    "captions",
    "compositions/frames",
    "lib",
    "renders",
    "thumbnail",
    ".comonteur",
]

MISE_TOML_HINT = """
Your mise.toml was left untouched. Add this to it if you want the pinned tools:

  [tools]
  ffmpeg = "latest"
  uv = "latest"
"""


def template_root() -> Path:
    """`skills/comonteur/templates/` — the directory this script's own parent lives in."""
    return tasks_dir().parents[1]


def sources(template: Path) -> list[str]:
    """Relative paths this task installs, in copy order.

    Tasks ship as files under `mise-tasks/comonteur/` so a `mise.toml` the user already owns
    is never rewritten. Files only: a `__pycache__/` next to the Python tasks (pytest imports
    them) is not a task, and copying a directory as a file would blow up mid-loop.
    """
    task_dir = template / "mise-tasks" / "comonteur"
    tasks = sorted(p.name for p in task_dir.iterdir() if p.is_file())
    return [f"mise-tasks/comonteur/{name}" for name in tasks] + ROOT_FILES + ["mise.toml"]


def plan(target: Path, template: Path) -> tuple[list[str], list[str]]:
    """Split the template's files into (to create, already there). Pure — no writes.

    This is the add-only rule in one place: anything already in `target` lands in `kept` and
    is never touched again.
    """
    created: list[str] = []
    kept: list[str] = []
    for rel in sources(template):
        (kept if (target / rel).exists() else created).append(rel)
    return created, kept


def apply(target: Path, template: Path, created: list[str]) -> None:
    for d in DIRS:
        (target / d).mkdir(parents=True, exist_ok=True)
    for rel in created:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # copy2 keeps the executable bit, which is what makes the copies runnable as tasks.
        shutil.copy2(template / rel, dest)


def setup_git(target: Path, lfs: bool) -> list[str]:
    inside = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if inside.returncode == 0:
        raise TaskError(
            f"refusing --git: {target} is already inside a git work tree",
            "nothing else was skipped; drop --git and commit however that repo does it",
        )
    subprocess.run(["git", "-C", str(target), "init", "-q"], check=True)
    added = [".git/"]
    if lfs:
        subprocess.run(["git", "-C", str(target), "lfs", "install", "--local"], check=True)
        subprocess.run(
            ["git", "-C", str(target), "lfs", "track", "*.blend", "assets/**", "audio/**"],
            check=True,
        )
        added.append(".gitattributes")
    return added


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="comonteur:init", description="Initialize a video project folder (add-only)"
    )
    parser.add_argument("dir", nargs="?", default=".", help="project folder")
    parser.add_argument("--git", action="store_true", help="git init")
    parser.add_argument("--lfs", action="store_true", help="track media with Git LFS")
    args = parser.parse_args(argv)
    if args.lfs and not args.git:
        parser.error("--lfs needs --git (LFS is a git feature). Re-run with both, or neither.")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    template = template_root()

    target = Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)
    target = target.resolve()
    print(f"Initializing {target}")

    created, kept = plan(target, template)
    apply(target, template, created)
    if "mise.toml" in kept:
        print(MISE_TOML_HINT)
    if args.git:
        created += setup_git(target, args.lfs)

    print()
    if created:
        print(f"created: {' '.join(created)}")
    if kept:
        print(f"kept:    {' '.join(kept)}")

    print(f"""
Next:
  cd {target}
  mise trust                    # these task files are new to mise, and it will not run
                                #   them until you say they are yours to run
  mise run comonteur:install    # both Blender add-ons + the MCP server, then a doctor report
  mise tasks                    # the whole comonteur:* menu, once you are set up

This is the last command you run by path: after `mise trust` every comonteur task —
installing and repairing the toolchain included — is `mise run comonteur:<task>` from
inside this project.

Then create master.blend, open it in Blender, and leave it open — the agent works
against that live session.""")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
