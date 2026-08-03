#!/usr/bin/env -S uv run --script
# fmt: off
#MISE description="Bump version, changelog, tag, push, build all 3 zips, publish the GitHub release"
#MISE tools={"git-cliff" = "latest", gh = "latest"}
# fmt: on
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

Two phases, in order, so everything failable runs before anything git-visible:
1. Build — bump the manifest, generate the changelog, build all 3 zips. All local file edits,
   no commit yet. Any failure here just discards those edits; nothing to roll back in git.
2. Publish — commit, tag, push, `gh release create`. Only starts once the build has fully
   succeeded, so this phase is just git/gh plumbing and rarely fails on its own. A failure
   before the push still rolls back cleanly (delete tag, reset the commit); a failure after
   the push can't be safely auto-reverted (shared state) — it prints a ready-to-run retry
   command instead.

This is one task, not tag-then-package-then-publish, because `gh release create` needs a
pushed tag to attach zips to — there's nothing to publish "for" until this run creates that
tag. Run identically on a laptop (`mise run release`) or via the `release` GitHub Actions
workflow — that workflow is workflow_dispatch only, never a tag-push trigger, since there is
no tag before this script runs; this run is what creates it.
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


class ReleaseError(Exception):
    """A step failed. Caught once in __main__ so the user sees one clean message, not a
    traceback through subprocess/zipfile internals."""


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=capture)
    if proc.returncode != 0:
        tail = ""
        if capture and proc.stderr:
            tail = f": {proc.stderr.strip().splitlines()[-1]}"
        raise ReleaseError(f"`{' '.join(cmd)}` failed (exit {proc.returncode}){tail}")
    return proc


def discard_build_edits() -> None:
    """Undo the build phase's uncommitted file edits (manifest + changelog). No commit/tag
    exists yet at this point, so there's nothing in git history to roll back."""
    print("==> discarding uncommitted file edits")
    subprocess.run(["git", "checkout", "--", str(MANIFEST)], cwd=ROOT)
    tracked = (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(CHANGELOG)], cwd=ROOT, capture_output=True
        ).returncode
        == 0
    )
    if tracked:
        subprocess.run(["git", "checkout", "--", str(CHANGELOG)], cwd=ROOT)
    elif CHANGELOG.exists():
        CHANGELOG.unlink()


def rollback_publish(version: str, *, committed: bool, tagged: bool) -> None:
    """Best-effort undo for the publish phase's commit/tag. Never called once anything has
    been pushed — pushed state is shared and must not be force-reverted automatically."""
    print("==> rolling back local commit/tag")
    if tagged:
        subprocess.run(["git", "tag", "-d", version], cwd=ROOT)
    if committed:
        subject = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"], cwd=ROOT, text=True, capture_output=True
        ).stdout.strip()
        if subject == f"chore(release): {version}":
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=ROOT)
        else:
            print(
                f"   ! HEAD commit isn't 'chore(release): {version}', not resetting — check manually"
            )


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
        raise ReleaseError(f"could not find a version line in {MANIFEST}")
    MANIFEST.write_text(new_text)


def build_zip(output: Path, source: Path, arcname_root: str) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, str(Path(arcname_root) / path.relative_to(source)))


def build(version: str) -> None:
    bump_manifest(version)
    run(["git-cliff", "--tag", version, "-o", str(CHANGELOG)])
    NOTES_FILE.write_text(run(["git-cliff", "--tag", version, "--latest"], capture=True).stdout)

    run(["mise", "run", "addon:build"])
    addon_zip = sorted((ROOT / "addon" / "build").glob("comonteur-*.zip"))[-1]
    (DIST / f"comonteur-addon-{version}.zip").write_bytes(addon_zip.read_bytes())
    build_zip(DIST / f"comonteur-skill-{version}.zip", ROOT / "skills" / "comonteur", "comonteur")
    build_zip(
        DIST / f"comonteur-mise-tasks-{version}.zip",
        ROOT / "skills" / "comonteur" / "templates",
        "comonteur",
    )


def publish(version: str) -> None:
    committed = tagged = False
    try:
        run(["git", "add", str(MANIFEST), str(CHANGELOG)])
        run(["git", "commit", "-m", f"chore(release): {version}"])
        committed = True
        run(["git", "tag", "-a", version, "-m", version])
        tagged = True
        run(["git", "push"])
        run(["git", "push", "origin", version])
    except Exception as e:
        rollback_publish(version, committed=committed, tagged=tagged)
        raise ReleaseError(f"release {version} aborted before publishing, rolled back: {e}") from e

    # Point of no return: pushed. A gh failure from here on can't be safely auto-reverted.
    zips = sorted(str(p) for p in DIST.glob("*.zip"))
    gh_cmd = [
        "gh",
        "release",
        "create",
        version,
        *zips,
        "--title",
        version,
        "--notes-file",
        str(NOTES_FILE),
    ]
    try:
        run(gh_cmd)
    except ReleaseError as e:
        raise ReleaseError(
            f"{version} was pushed but the release wasn't published: {e}\n   retry: {' '.join(gh_cmd)}"
        ) from e


def main() -> None:
    if run(["git", "status", "--porcelain"], capture=True).stdout.strip():
        raise ReleaseError("working tree not clean — commit or stash before releasing")

    version = next_version()
    print(f"==> releasing {version}")

    DIST.mkdir(exist_ok=True)
    for old in DIST.glob("*"):
        old.unlink()

    try:
        build(version)
    except Exception as e:
        discard_build_edits()
        raise ReleaseError(f"release {version} aborted, no git changes made: {e}") from e

    publish(version)
    print(f"==> published {version}")


if __name__ == "__main__":
    try:
        main()
    except ReleaseError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
