#!/usr/bin/env -S uv run --script
#MISE description="Install/repair the whole toolchain: both Blender add-ons, the MCP server, then doctor"
#MISE depends=["comonteur:install_addon", "comonteur:install_mcp"]
#MISE depends_post=["comonteur:doctor"]
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Orchestration only — every line of install logic lives in the tasks this depends on.

mise runs `install_addon` and `install_mcp` first, then `doctor` afterwards via
`depends_post`. `install_mcp` carries `wait_for=["comonteur:install_addon"]` so the two never
overlap: both end in a background Blender calling `wm.save_userpref()`, and concurrent writes
to user preferences would have one silently lose.

This task therefore has no body worth the name. Two consequences to know about:

- **Arguments do not reach dependencies** (verified: `mise run comonteur:install --ref X`
  leaves the dependency's `--ref` unset; only statically written `depends` args propagate).
  So pin a version with `mise run comonteur:install_addon --ref v0.1.0` directly — the flag
  lives on the task it affects.
- **`depends` only exists when mise is driving.** Running this file by path does nothing.
  That is fine because it is never the bootstrap: `init` is, and after `init` + `mise trust`
  a project has every `comonteur:*` task (docs/mcp-and-tooling.md §8.2).
"""

from __future__ import annotations

import sys

from _common import step


def main(argv: list[str]) -> int:
    step("Toolchain installed — see the doctor report below")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
