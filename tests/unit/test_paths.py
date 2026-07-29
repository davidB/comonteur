"""Pure-logic test for addon/comonteur/paths.py — no bpy needed (SPEC.md §8)."""

import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "addon", "comonteur"))
import paths  # noqa: E402


class Vec:
    def __init__(self, *v: float) -> None:
        self._v = list(v)

    def __getitem__(self, i: int) -> float:
        return self._v[i]

    def __setitem__(self, i: int, val: float) -> None:
        self._v[i] = val


class Obj:
    def __init__(self) -> None:
        self.location = Vec(0.0, 0.0, 0.0)
        self.child: Any = None


def test_resolve_plain_attr() -> None:
    o = Obj()
    assert paths.resolve(o, "location") is o.location


def test_resolve_indexed() -> None:
    o = Obj()
    o.location[1] = 0.5
    assert paths.resolve(o, "location[1]") == 0.5


def test_set_indexed() -> None:
    o = Obj()
    paths.set_(o, "location[1]", 0.42)
    assert o.location[1] == 0.42


def test_set_plain_attr() -> None:
    o = Obj()
    o.child = Obj()
    paths.set_(o, "child.location[2]", 9.0)
    assert o.child.location[2] == 9.0


def test_bad_segment_raises() -> None:
    o = Obj()
    with pytest.raises(ValueError):
        paths.resolve(o, "loc[[1]")
