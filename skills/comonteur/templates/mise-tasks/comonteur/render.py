#!/usr/bin/env -S uv run --script
#MISE description="Render master.blend's timeline to renders/ (background Blender)"
#MISE dir="{{config_root}}"
#MISE tools={uv = "latest"}
#USAGE arg "[blender_args]…" help="Extra arguments forwarded verbatim to Blender"
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render `master.blend`'s timeline.

ponytail: uses master.blend's own output settings and full frame range; pass
`-- -s 100 -e 200` for a subrange rather than teaching this script about ranges.
No sources/outputs: a render's inputs live inside a .blend, which mise cannot hash usefully.
"""

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
            "run `mise run comonteur:edit` first — it creates master.blend",
        )
    Path("renders").mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-b", "master.blend", "-a", *argv]
    if os.name == "posix":
        os.execvp(exe, cmd)  # noqa: S606 — never returns
    return run(cmd, check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
