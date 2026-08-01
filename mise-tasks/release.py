#!/usr/bin/env -S uv run --script
#MISE description="Bump version, changelog, tag, push, build all 3 zips, publish the GitHub release"
#MISE tools={"git-cliff" = "latest", gh = "latest"}
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Release policy for comonteur.

Version scheme: {major}.{yyyymmdd}.{patch}
- major: repo-root VERSION file, single line, manually bumped for a deliberate break (e.g. a
  Blender-compatibility jump). Not automated on purpose — a one-line file needs no task; just
  edit VERSION.
- yyyymmdd: today's date (UTC, so a laptop and a CI runner agree regardless of local time zone).
- patch: count of existing git tags matching "{major}.{yyyymmdd}.*" — same-day re-releases
  increment instead of colliding.

A future Blender-compatibility marker can be appended later as build metadata (e.g. "+bl5.2")
without changing this scheme — that kind of suffix doesn't affect version/tag ordering.

This is one task, not tag-then-package-then-publish: `gh release create` needs a pushed tag to
attach zips to, and there is nothing to package "for" until this run creates that tag. Steps 1-6
below are local-only and safe to abort (nothing pushed yet); steps 7-8 push and publish — the
point of no return. Run identically on a laptop (`mise run release`) or via the `release`
GitHub Actions workflow — that workflow is workflow_dispatch only, never a tag-push trigger,
since there is no tag before this script runs; this run is what creates it.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
MANIFEST = ROOT / "addon" / "comonteur" / "blender_manifest.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
DIST = ROOT / "dist"
NOTES_FILE = DIST / "RELEASE_NOTES.md"


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, cwd=ROOT, text=True, capture_output=capture)


def next_version() -> str:
    major = VERSION_FILE.read_text().strip()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"{major}.{today}."
    existing = run(["git", "tag", "-l", f"{prefix}*"], capture=True).stdout.split()
    return f"{prefix}{len(existing)}"


def bump_manifest(version: str) -> None:
    text = MANIFEST.read_text()
    new_text, n = re.subn(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1)
    if n == 0:
        sys.exit(f"could not find a version line in {MANIFEST}")
    MANIFEST.write_text(new_text)


def build_zip(output: Path, source: Path, arcname_root: str) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, str(Path(arcname_root) / path.relative_to(source)))


def main() -> None:
    version = next_version()
    print(f"==> releasing {version}")

    DIST.mkdir(exist_ok=True)
    for old in DIST.glob("*"):
        old.unlink()

    bump_manifest(version)
    run(["git-cliff", "--tag", version, "-o", str(CHANGELOG)])
    NOTES_FILE.write_text(run(["git-cliff", "--tag", version, "--latest"], capture=True).stdout)

    run(["git", "add", str(MANIFEST), str(CHANGELOG)])
    run(["git", "commit", "-m", f"chore(release): {version}"])
    run(["git", "tag", "-a", version, "-m", version])

    run(["mise", "run", "addon:build"])
    addon_zip = sorted((ROOT / "addon" / "build").glob("comonteur-*.zip"))[-1]
    (DIST / f"comonteur-addon-{version}.zip").write_bytes(addon_zip.read_bytes())
    build_zip(DIST / f"comonteur-skill-{version}.zip", ROOT / "skills" / "comonteur", "comonteur")
    build_zip(
        DIST / f"comonteur-mise-tasks-{version}.zip",
        ROOT / "skills" / "comonteur" / "templates",
        "comonteur",
    )

    run(["git", "push"])
    run(["git", "push", "origin", version])
    run(
        [
            "gh",
            "release",
            "create",
            version,
            *sorted(str(p) for p in DIST.glob("*.zip")),
            "--title",
            version,
            "--notes-file",
            str(NOTES_FILE),
        ]
    )
    print(f"==> published {version}")


if __name__ == "__main__":
    main()
