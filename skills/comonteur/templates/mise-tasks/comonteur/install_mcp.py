#!/usr/bin/env -S uv run --script
#MISE description="Install Blender's MCP add-on and its official MCP server, and register it"
#MISE env={BLENDER_MCP_VERSION = "1.0.0"}
#USAGE flag "--version <version>" help="Blender MCP server release to install"
# Both this and install_addon end in a background Blender writing user preferences;
# wait_for keeps them from overlapping when comonteur:install runs both.
#MISE wait_for=["comonteur:install_addon"]
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Install both halves of Blender MCP (docs/milestones.md M5.5) — they are useless apart:

1. **The Blender-side add-on**, from the Blender Lab extensions repository, entirely through
   `blender --command extension repo-add` + `extension install --sync --enable`. Nothing is
   downloaded or unzipped by hand; Blender's own package manager does it.
2. **The host-side MCP server**, which the add-on talks to. Claude Code has no native `.mcpb`
   installer (that format is Desktop-only), but a `.mcpb` is just a zip of `manifest.json`
   plus a uv-managed Python project — so unpack it and point `claude mcp add` at its
   `uv run` entry point.

Idempotent: an add-on already installed by hand is detected, not duplicated, and the server
registration is removed before it is re-added.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from _common import TaskError, die, enable_addon, require, run, step, tasks_dir, warn

DEFAULT_VERSION = "1.0.0"
RELEASES = "https://projects.blender.org/lab/blender_mcp/releases/download"
# Same repository id drag-and-drop creates, so an add-on installed through the GUI is found
# here rather than duplicated under a second repo.
ADDON_REPO = ("lab_blender_org", "Blender Lab", "https://lab.blender.org/")
ADDON_MODULE = "bl_ext.lab_blender_org.mcp"


def install_addon() -> None:
    """The Blender-side add-on, via Blender's own extension package manager.

    ponytail: `extension install` takes no version, so this tracks the Lab repo's latest while
    the server below is pinned to --version. Pin both via install-file if they ever skew.
    """
    blender = shutil.which("blender")
    if blender is None:
        warn("no blender on PATH — skipping the Blender-side MCP add-on", "install Blender, then re-run")
        return
    step("Installing Blender's MCP add-on")
    module, name, url = ADDON_REPO
    repos = run([blender, "--command", "extension", "repo-list"], check=False, capture=True)
    if not any(line.startswith(f"{module}:") for line in repos.stdout.splitlines()):
        add = ["--command", "extension", "repo-add", module, "--name", name, "--url", url]
        run([blender, *add], capture=True)
    listed = run([blender, "--command", "extension", "list"], check=False, capture=True)
    installed = any(
        line.strip().startswith("mcp [installed]") for line in listed.stdout.splitlines()
    )
    if not installed:
        try:
            install = ["--command", "extension", "install", "mcp", "--sync", "--enable"]
            run([blender, *install], capture=True)
        except TaskError as e:
            warn(str(e), "install it by hand: https://www.blender.org/lab/mcp-server/")
            return
        print("    installed")
    else:
        print("    already installed")
    # Always enable, never just when we installed: repo-add can reveal a package that was
    # already on disk (dropped in via the GUI) as [installed] but disabled, and `install -e`
    # never runs for it. Enabling an already-enabled add-on is a no-op.
    enable_addon(ADDON_MODULE)
    print("    enabled")


def base_dir() -> Path:
    """Where the unpacked server lives — permanently, since the registered `claude mcp` command
    points into it forever. It must outlive this script's working copy, which is why a
    throwaway extracted directory never qualifies.

    A checkout keeps it in `.vendor/`; anything else uses the platform's user data dir.
    """
    repo = tasks_dir().parents[4]
    if (repo / "addon" / "comonteur" / "blender_manifest.toml").is_file():
        return repo / ".vendor"
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        root = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(root) / "comonteur"


def fetch_and_unpack(version: str, vendor: Path) -> None:
    url = f"{RELEASES}/v{version}/blender-{version}.mcpb"
    step(f"Fetching Blender MCP server v{version}")
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "blender-mcp.mcpb"
        # The release host 403s an unadorned urllib User-Agent, as it did curl's.
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                bundle.write_bytes(response.read())
        except (urllib.error.URLError, TimeoutError) as e:
            raise TaskError(
                f"could not download {url}: {e}",
                "check the version exists and you are online — "
                "https://projects.blender.org/lab/blender_mcp/releases",
            ) from e
        if not zipfile.is_zipfile(bundle):
            raise TaskError(
                f"{url} is not a .mcpb bundle (got {bundle.stat().st_size} bytes of something else)",
                "the release may have moved; check the releases page",
            )
        if vendor.exists():
            shutil.rmtree(vendor)
        vendor.mkdir(parents=True)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(vendor)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install the Blender MCP server")
    parser.add_argument(
        "--version",
        default=os.environ.get("BLENDER_MCP_VERSION") or DEFAULT_VERSION,
    )
    args = parser.parse_args(argv)

    install_addon()

    uv = require("uv", "mise use -g uv — https://docs.astral.sh/uv/")
    claude = require(
        "claude",
        "install Claude Code, or register the server by hand with your MCP client: "
        "any client can run `uv run --project <dir> blender-mcp`",
    )

    vendor = base_dir() / "blender-mcp"
    fetch_and_unpack(args.version, vendor)

    step("Syncing dependencies")
    run([uv, "sync", "--project", str(vendor)], capture=True)

    step("Registering with Claude Code (scope: user)")
    run([claude, "mcp", "remove", "blender", "--scope", "user"], check=False, capture=True)
    run(
        [claude, "mcp", "add", "blender", "-s", "user", "--",
         uv, "run", "--project", str(vendor), "blender-mcp"],
        capture=True,
    )

    print(f"\nDone ({vendor}). Verify with: claude mcp list, and `comonteur:doctor` for the add-on.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
