#!/usr/bin/env -S uv run --script
#MISE description="Install the comonteur add-on into Blender (symlinked from a checkout, packaged otherwise)"
#USAGE flag "--source <source>" help="add-on source dir (default: this checkout's addon/comonteur)"
#USAGE flag "--ref <ref>" help="git tag/branch/sha to fetch the add-on from when not in a checkout"
#USAGE flag "--copy" help="copy/package instead of symlinking, even from a checkout"
#MISE tools={uv = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Install and enable `addon/comonteur` in Blender's `user_default` extension repository.

Self-sufficient — this is the only task that knows how the add-on reaches a machine:

- **checkout** — symlink, so edits are live without reinstalling. The dev loop.
- **no checkout** — fetch `--ref`'s source tarball, then `extension build` +
  `extension install-file`, the packaged path end users get. The add-on is the one artifact
  still needing delivery; every other task ships inside the skill (docs/mcp-and-tooling.md §8.2).
- **`--source <dir>`/`--copy`** — package a tree you already have, skipping the download.

The extensions directory is asked *of Blender* rather than hardcoded: the bash version had
`~/.config/blender/5.2/extensions/user_default`, which is Linux-only — macOS and Windows put
it somewhere else entirely, and a user may have moved the repo anywhere.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from _common import (
    TaskError,
    die,
    enable_addon,
    require_blender,
    run,
    step,
    tasks_dir,
)

MODULE = "bl_ext.user_default.comonteur"
REPO = "https://github.com/davidB/comonteur"


def fetch_source(ref: str, into: Path) -> Path:
    """Extract `<repo>@<ref>` into `into`, returning `addon/comonteur` inside it."""
    url = f"{REPO}/archive/{ref}.tar.gz"
    step(f"Fetching add-on source for {ref}")
    archive = into / "source.tar.gz"
    try:
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
            archive.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError) as e:
        raise TaskError(f"could not download {url}: {e}", f"check that {ref} exists") from e
    root = into / "src"
    with tarfile.open(archive) as tar:
        # filter="data" refuses absolute paths and links escaping the destination.
        tar.extractall(root, filter="data")
    extracted = sorted(p for p in root.iterdir() if p.is_dir())
    if not extracted:
        raise TaskError(f"{url} extracted to nothing", "the ref may not exist")
    return extracted[0] / "addon" / "comonteur"


def checkout_addon() -> Path | None:
    """`<repo>/addon/comonteur` when this script is running from a checkout, else None.

    The templates dir sits five levels below the repo root
    (`skills/comonteur/templates/mise-tasks/comonteur/`); in an installed project that path
    resolves to somewhere without an `addon/`, which is exactly the signal we want.
    """
    candidate = tasks_dir().parents[4] / "addon" / "comonteur"
    return candidate if (candidate / "blender_manifest.toml").is_file() else None


def extensions_dir(repo: str = "user_default") -> Path:
    """Blender's `<repo>` extension directory, from `--command extension repo-list`.

    Verified on 5.2 — repo-list prints one `<id>:` block per repository, each with an absolute
    `directory:`, which is the documented way to ask (and the reason no `~/.config/blender/...`
    is assembled here: macOS and Windows put it elsewhere, and a user may have moved it).
    """
    out = run(
        [require_blender(), "--command", "extension", "repo-list"], capture=True
    ).stdout
    current = ""
    for line in out.splitlines():
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            current = line.rstrip()[:-1]
        elif current == repo and line.strip().startswith("directory:"):
            return Path(line.split(":", 1)[1].strip().strip('"'))
    raise TaskError(
        f"Blender reported no `{repo}` extension repository",
        "check `blender --command extension repo-list` — the repo may have been removed",
    )


def check_source(source: Path) -> Path:
    """Resolve `source` and refuse anything that is not a Blender add-on."""
    source = source.resolve()
    if not (source / "blender_manifest.toml").is_file():
        raise TaskError(
            f"{source} is not a Blender add-on (no blender_manifest.toml)",
            "point --source at the addon/comonteur directory",
        )
    return source


def link(source: Path, dest: Path) -> str:
    """Symlink source -> dest, replacing whatever is there. Copies if symlinks are refused."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)
    try:
        dest.symlink_to(source, target_is_directory=True)
    except OSError:
        # Windows without Developer Mode (or a filesystem that has no symlinks): a copy is
        # correct, it just is not the live dev loop.
        shutil.copytree(source, dest)
        return f"copied (no symlink support) {source} -> {dest}"
    return f"linked {dest} -> {source}"


def install_packaged(source: Path) -> str:
    """`extension build` + `install-file` — what an end user gets."""
    blender = require_blender()
    with tempfile.TemporaryDirectory() as tmp:
        build = ["--command", "extension", "build"]
        build += ["--source-dir", str(source), "--output-dir", tmp]
        run(
            [blender, *build],
            capture=True,
            fix="check the add-on source is intact (blender_manifest.toml + LICENSE)",
        )
        zips = sorted(Path(tmp).glob("comonteur-*.zip"))
        if not zips:
            raise TaskError(
                "extension build produced no zip",
                f"run it by hand: blender --command extension build --source-dir {source}",
            )
        # -e enables it as part of the install, so the packaged path needs no separate
        # enable() launch — that is the only reason install-file is preferred over unzipping.
        install = ["--command", "extension", "install-file"]
        install += ["-r", "user_default", "-e", str(zips[0])]
        run([blender, *install], capture=True)
    return "installed and enabled in Blender's user_default repository"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install the comonteur Blender add-on")
    parser.add_argument("--source", type=Path, help="add-on source directory")
    parser.add_argument("--ref", default="main", help="git tag/branch/sha to fetch")
    parser.add_argument("--copy", action="store_true", help="package/copy instead of symlink")
    args = parser.parse_args(argv)

    step("Installing the comonteur Blender add-on")
    # Symlinking needs no Blender, but finding *where* to symlink does; without Blender we
    # cannot do either honestly, so require it rather than guess a path per platform.
    require_blender()

    checkout = checkout_addon()
    local: Path | None = args.source or checkout
    if local is None:
        # No checkout and no --source: the delivery case. Fetch, install, drop the tree.
        with tempfile.TemporaryDirectory() as tmp:
            source = check_source(fetch_source(args.ref, Path(tmp)))
            print(f"    {install_packaged(source)} ({args.ref})")
    elif args.copy or args.source is not None:
        print(f"    {install_packaged(check_source(local))}")
    else:
        # The checkout's own add-on: symlink, so edits stay live without reinstalling.
        print(f"    {link(check_source(local), extensions_dir() / 'comonteur')}")
        enable_addon(MODULE)
        print(f"    enabled {MODULE}")
    print("    (run this with Blender closed — a GUI session overwrites those preferences)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TaskError as e:
        sys.exit(die(e))
