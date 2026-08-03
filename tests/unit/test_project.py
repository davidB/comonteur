"""Pure-logic test for addon/comonteur/project.py's _walk_up/_to_link_path — no bpy
needed (SPEC.md §8). find_root()/to_link_path() stay thin bpy-dependent wrappers
around these, mirroring reconcile.py's diff()/apply() split.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "addon", "comonteur"))
import project  # noqa: E402

pytestmark = pytest.mark.pure


def test_walk_up_finds_marker(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / ".comonteur").mkdir(parents=True)
    nested = root / "shots"
    nested.mkdir(parents=True)

    assert project._walk_up(str(nested), ".comonteur") == str(root)


def test_walk_up_falls_back_to_start_when_marker_absent(tmp_path: Path) -> None:
    start = tmp_path / "nowhere"
    start.mkdir()

    assert project._walk_up(str(start), ".comonteur") == str(start)


def test_to_link_path_relative_to_current_blend() -> None:
    target = "/proj/lib/design.blend"
    current = "/proj/shots/shot-03.blend"

    assert project._to_link_path(target, current) == "//../lib/design.blend"


def test_to_link_path_same_dir_as_current_blend() -> None:
    target = "/proj/lib/design.blend"
    current = "/proj/timeline.blend"

    assert project._to_link_path(target, current) == "//lib/design.blend"


def test_to_link_path_unsaved_blend_returns_target_unchanged() -> None:
    target = "/proj/lib/design.blend"

    assert project._to_link_path(target, "") == target
