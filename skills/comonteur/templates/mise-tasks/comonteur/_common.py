"""Shared helpers for the `comonteur:*` task scripts (docs/mcp-and-tooling.md §8.2).

Not a task itself: no shebang and mode 644, which is what keeps mise from listing it — mise
only picks up executable files in `mise-tasks/`. `comonteur:init` still copies it into a
project (without the executable bit) because its siblings import it.

Siblings reach it with a plain `import _common`: `uv run --script foo.py` puts the script's
own directory first on `sys.path`, and running one by path does the same.

Everything here is stdlib and cross-platform. Rules of thumb for what belongs: `shutil.which`
over `command -v`, `subprocess` lists over shell strings, and no helper only one script uses.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BLENDER_PIN = "5.2"
"""Blender LTS this project is reproducible against (docs/constraints-and-risks.md §11)."""

BLENDER_DOWNLOAD = "https://www.blender.org/download/lts/"


class TaskError(Exception):
    """Fatal but expected. `main()` prints it and exits 1 — a traceback would tell the user
    nothing they can act on. `fix` is the actionable half: what to run or install.
    """

    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.fix = fix


def die(err: TaskError) -> int:
    """Print a TaskError like doctor prints its ✗ lines. Returns the process exit code."""
    print(f"{RED}✗{RESET} {err}", file=sys.stderr)
    if err.fix:
        print(f"   → {err.fix}", file=sys.stderr)
    return 1


# --- output -----------------------------------------------------------------------------

# Windows terminals have handled ANSI since Win10, but a redirected stream or NO_COLOR must not.
_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
GREEN = "\033[32m" if _COLOR else ""
RED = "\033[31m" if _COLOR else ""
YELLOW = "\033[33m" if _COLOR else ""
DIM = "\033[2m" if _COLOR else ""
RESET = "\033[0m" if _COLOR else ""


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def bad(msg: str, fix: str) -> None:
    print(f"  {RED}✗{RESET} {msg}\n     → {fix}")


def warn(msg: str, fix: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}\n     → {fix}")


def skip(msg: str) -> None:
    print(f"  {DIM}·{RESET} {msg}")


def step(msg: str) -> None:
    print(f"==> {msg}")


# --- processes --------------------------------------------------------------------------


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    fix: str = "",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """`subprocess.run` that fails as a TaskError naming the command and its last stderr line.

    A bare CalledProcessError says "returned non-zero exit status 1" and nothing else; the
    bash originals said even less, since most of them sent stderr to /dev/null.
    """
    try:
        proc = subprocess.run(cmd, check=False, capture_output=capture, text=True, cwd=cwd)
    except FileNotFoundError as e:
        raise TaskError(f"{cmd[0]} not found on PATH", fix) from e
    if check and proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        tail = f": {detail[-1]}" if detail else ""
        raise TaskError(f"`{' '.join(cmd)}` failed (exit {proc.returncode}){tail}", fix)
    return proc


def require(tool: str, fix: str) -> str:
    """Absolute path to `tool`, or a TaskError. `shutil.which` handles PATHEXT on Windows."""
    found = shutil.which(tool)
    if found is None:
        raise TaskError(f"{tool} not on PATH", fix)
    return found


def require_blender() -> str:
    return require("blender", f"install Blender {BLENDER_PIN} LTS — {BLENDER_DOWNLOAD}")


def blender_py(expr: str, *, check: bool = True) -> str:
    """Run `expr` in a background Blender, return its stdout.

    Blender writes its banner and quit message to stdout as well, so callers tag their own
    output (doctor emits `CMT ...` lines) and filter, rather than parsing the lot.
    """
    return run(
        [require_blender(), "-b", "--python-expr", expr], check=check, capture=True
    ).stdout


def enable_addon(module: str) -> None:
    """Persistently enable an installed add-on.

    `blender --command extension` has no enable/disable subcommand (verified on 5.2): its
    `install`/`install-file -e` enable only what that call just installed, and `--addons`
    lasts one launch. So anything already on disk — a symlinked dev install, or a package
    installed before its repository was registered — can only be enabled through `bpy.ops`.

    Run with the GUI closed: a GUI session exiting afterwards writes its own preferences
    over ours (docs/M0-FINDINGS.md M0.11).
    """
    blender_py(
        f"import bpy\n"
        f"bpy.ops.preferences.addon_enable(module={module!r})\n"
        f"bpy.ops.wm.save_userpref()\n"
    )


def project_root() -> Path:
    """The project being operated on: mise's config root, else the working directory."""
    return Path(os.environ.get("MISE_PROJECT_ROOT") or Path.cwd())


def tasks_dir() -> Path:
    """Directory holding the task scripts, resolved through symlinks to the real copy."""
    return Path(__file__).resolve().parent
