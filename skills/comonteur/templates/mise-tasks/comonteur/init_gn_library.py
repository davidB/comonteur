#!/usr/bin/env -S uv run --script
# fmt: off
#MISE description="Materialize the project's GN VFX asset library at lib/gn-vfx.blend (add-only)"
#USAGE arg "[dir]" help="project folder (default: the enclosing project)"
#MISE tools={uv = "latest"}
# fmt: on
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build every `cmt.gn.*` effect once and save it as `lib/gn-vfx.blend` (docs/library.md §9).

`gn.char_reveal()` et al. are idempotent-by-name in whichever `.blend` calls them, but that
means each new project rebuilds them from scratch in `timeline.blend` — there is no
persistent, project-independent catalog to browse in Blender's Asset Browser or link from a
*different* future project. This task is that missing "start a library" step: add-only, like
`init.py` — if `lib/gn-vfx.blend` already exists, it's left untouched.

Reuse from any project (this one or a later one) via `cmt.library.discover()`/`link()`,
same as `lib/design.blend` (references/vfx-recipes.md).
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from _common import TaskError, blender_headless, die, ok, project_root, skip

EFFECTS = ["char_reveal", "typewriter", "fracture"]

_BUILD_SCRIPT = f"""
import addon_utils
import bpy

cmt_module_name = next(
    (m.__name__ for m in addon_utils.modules() if m.__name__.split(".")[-1] == "comonteur"),
    None,
)
if cmt_module_name is None:
    raise SystemExit("comonteur add-on not installed - run `mise run comonteur:install` first")
import importlib
cmt = importlib.import_module(cmt_module_name)

built = []
for name in {EFFECTS!r}:
    ng = getattr(cmt.gn, name)()
    built.append((ng.name, ng.asset_data.description if ng.asset_data else ""))

bpy.ops.wm.save_as_mainfile(filepath={{lib_path!r}})
print("CMT_GN_LIBRARY_BUILT " + repr(built))
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="comonteur:init_gn_library", description="Materialize lib/gn-vfx.blend (add-only)"
    )
    parser.add_argument("dir", nargs="?", default=None, help="project folder")
    args = parser.parse_args(argv)

    root = Path(args.dir) if args.dir else project_root()
    lib_path = root / "lib" / "gn-vfx.blend"
    if lib_path.exists():
        skip(f"{lib_path} already exists, kept")
        return 0

    lib_path.parent.mkdir(parents=True, exist_ok=True)
    script = _BUILD_SCRIPT.format(lib_path=str(lib_path))
    out = blender_headless(script)
    line = next(
        (line_ for line_ in out.splitlines() if line_.startswith("CMT_GN_LIBRARY_BUILT ")), ""
    )
    # literal_eval, not eval: this is a repr() of plain str/tuple/list data, no need for eval's
    # arbitrary-code-execution risk even though the source (Blender's own stdout) is trusted.
    built = ast.literal_eval(line[len("CMT_GN_LIBRARY_BUILT ") :]) if line else []

    ok(f"created {lib_path}")
    for gn_name, description in built:
        print(f"    {gn_name} — {description}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
