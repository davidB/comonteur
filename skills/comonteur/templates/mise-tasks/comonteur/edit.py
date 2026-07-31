#!/usr/bin/env -S uv run --script
#MISE description="Open master.blend in Blender — leave it open, the agent talks to this session"
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
#USAGE arg "[blender_args]…" help="Extra arguments forwarded verbatim to Blender"
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Open `master.blend` for the human. Extra args go straight to Blender."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from _common import TaskError, die, require_blender, run


def main(argv: list[str]) -> int:
    exe = require_blender()
    if not Path("master.blend").exists():
        raise TaskError(
            f"no master.blend in {Path.cwd()}",
            "create and save it in Blender first — the agent never saves for you",
        )
    cmd = [exe, "master.blend", *argv]
    # execvp hands the terminal to Blender outright; Windows has no equivalent (it would
    # spawn and return), so there we wait and pass the exit code back.
    if os.name == "posix":
        os.execvp(exe, cmd)  # noqa: S606 — never returns
    return run(cmd, check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
