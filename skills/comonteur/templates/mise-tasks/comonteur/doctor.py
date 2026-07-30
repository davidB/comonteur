#!/usr/bin/env -S uv run --script
#MISE description="Check the toolchain, and this project too when run inside one"
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""One doctor for both roles: the machine's toolchain, plus the project's own files when
there is a project.

Every check runs even after one fails — a doctor that stops at the first problem makes the
user fix things one round-trip at a time.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from _common import (
    BLENDER_DOWNLOAD,
    BLENDER_PIN,
    TaskError,
    bad,
    blender_py,
    die,
    ok,
    project_root,
    skip,
    tasks_dir,
    warn,
)

FIX = "mise run comonteur:install"
TASK_SCRIPTS = [
    "_common",
    "convert_fonts",
    "doctor",
    "edit",
    "ingest_captions",
    "ingest_manifest",
    "ingest_narrative",
    "init",
    "install",
    "install_addon",
    "install_mcp",
    "reconcile",
    "render",
]
ADDONS = {
    "bl_ext.user_default.comonteur": "comonteur add-on",
    "bl_ext.lab_blender_org.mcp": "mcp add-on",
}


def classify_blender_version(output: str, pin: str = BLENDER_PIN) -> tuple[str, str]:
    """Parse `blender --version` output into (status, message).

    Pure, so the version policy is testable without Blender. A *newer* Blender warns rather
    than fails: it will probably work, it just is not what generated code is reproducible
    against (docs/constraints-and-risks.md §11).
    """
    first = output.strip().splitlines()[0] if output.strip() else ""
    parts = first.split()
    version = parts[1] if len(parts) > 1 and parts[0].lower() == "blender" else ""
    if not version:
        return "bad", "blender found but --version unreadable"
    if version.split(".")[:2] == pin.split("."):
        return "ok", f"blender {version}"
    return "warn", f"blender {version} (pinned: {pin} LTS)"


def check_blender() -> bool:
    if shutil.which("blender") is None:
        bad("blender not on PATH", f"install Blender {BLENDER_PIN} LTS — {BLENDER_DOWNLOAD}")
        return False
    try:
        out = subprocess.run(
            ["blender", "--version"], capture_output=True, text=True, timeout=60
        ).stdout
    except (OSError, subprocess.SubprocessError) as e:
        bad(f"blender --version failed: {e}", "check your Blender install")
        return False
    status, message = classify_blender_version(out)
    if status == "ok":
        ok(message)
        return True
    if status == "warn":
        warn(message, f"only {BLENDER_PIN} is reproducible — {BLENDER_DOWNLOAD}")
        return True
    bad(message, "check your Blender install")
    return False


def check_tool(tool: str, fix: str) -> bool:
    found = shutil.which(tool)
    if found:
        ok(tool)
        return True
    bad(f"{tool} not on PATH", fix)
    return False


def check_task_scripts() -> bool:
    """The task scripts ship next to this one — nothing is installed, so "are they there" is
    the whole check. No executable-bit test: it means nothing on Windows.
    """
    here = tasks_dir()
    missing = [name for name in TASK_SCRIPTS if not (here / f"{name}.py").is_file()]
    if missing:
        bad(f"task scripts missing: {' '.join(missing)}", FIX)
        return False
    ok(f"comonteur task scripts ({len(TASK_SCRIPTS)})")
    return True


def check_addons() -> bool:
    """Ask Blender itself: a present extensions directory says nothing about an add-on being
    registered or enabled. One launch reports both add-ons.
    """
    if shutil.which("blender") is None:
        skip("add-ons unchecked — no blender on PATH")
        return True
    expr = (
        "import bpy, addon_utils\n"
        "avail = {m.__name__ for m in addon_utils.modules()}\n"
        "on = set(bpy.context.preferences.addons.keys())\n"
        f"for m in {tuple(ADDONS)!r}:\n"
        "    print('CMT', m, 'installed' if m in avail else 'missing',"
        " 'enabled' if m in on else 'disabled')\n"
    )
    try:
        lines = blender_py(expr, check=False).splitlines()
    except TaskError as e:
        warn(f"add-ons unchecked: {e}", FIX)
        return True
    reported = {
        parts[1]: parts[2:]
        for parts in (line.split() for line in lines)
        if len(parts) == 4 and parts[0] == "CMT"
    }
    healthy = True
    for module, label in ADDONS.items():
        state = reported.get(module)
        if state == ["installed", "enabled"]:
            ok(label)
        elif state == ["installed", "disabled"]:
            warn(
                f"{label} installed but not enabled",
                f"{FIX}  (or tick it in Edit > Preferences > Add-ons)",
            )
        else:
            bad(f"{label} not installed in Blender", FIX)
            healthy = False
    return healthy


def check_mcp() -> None:
    claude = shutil.which("claude")
    if claude is None:
        warn(
            "claude CLI not found — MCP registration unchecked",
            "any MCP-capable client works; see README",
        )
        return
    out = subprocess.run(
        [claude, "mcp", "list"], capture_output=True, text=True, timeout=120
    ).stdout
    if "blender" in out:
        ok("Blender MCP server registered with Claude Code")
    else:
        warn("Blender MCP server not registered with Claude Code", FIX)


def check_project(root: Path) -> None:
    """Project checks run only inside a project — nothing here is fatal to the toolchain."""
    if not ((root / "narrative.toml").is_file() or (root / "timeline.toml").is_file()):
        return
    print(f"\nproject ({root})")
    checks = [
        ("narrative.toml", "shot intents live here"),
        ("timeline.toml", "the assembly lives here"),
        (
            "master.blend",
            "create and save it in Blender — the agent never saves for you",
        ),
    ]
    for name, hint in checks:
        if (root / name).is_file():
            ok(name)
        else:
            warn(f"no {name}", hint)
    if (root / ".comonteur").is_dir():
        ok(".comonteur/ (journal, review frames)")
    else:
        skip(".comonteur/ fills in on the agent's first batch")


def main(argv: list[str]) -> int:
    print("comonteur doctor")
    print("toolchain")

    healthy = check_blender()
    for tool in ("ffmpeg", "ffprobe"):
        healthy &= check_tool(tool, "mise install  (pinned in the project's mise.toml)")
    healthy &= check_tool(
        "uv", "mise use -g uv  (every comonteur task is a `uv run --script`)"
    )
    healthy &= check_task_scripts()
    healthy &= check_addons()
    check_mcp()

    for tool, why in (
        ("rec", "only needed to record a voiceover locally"),
        ("git-lfs", "only needed if you version .blend/media with git"),
    ):
        if shutil.which(tool):
            ok(tool)
        else:
            skip(f"{tool} absent — {why}")

    check_project(Path(argv[0]) if argv else project_root())

    print()
    if not healthy:
        print("Something required is missing (see ✗ above).")
        return 1
    print("Ready.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
