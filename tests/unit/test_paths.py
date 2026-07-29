"""Pure-logic test for addon/comonteur/paths.py — no bpy needed (SPEC.md §8)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "addon", "comonteur"))
import paths  # noqa: E402


class Vec:
    def __init__(self, *v):
        self._v = list(v)

    def __getitem__(self, i):
        return self._v[i]

    def __setitem__(self, i, val):
        self._v[i] = val


class Obj:
    def __init__(self):
        self.location = Vec(0.0, 0.0, 0.0)
        self.child = None


def test_resolve_plain_attr():
    o = Obj()
    assert paths.resolve(o, "location") is o.location


def test_resolve_indexed():
    o = Obj()
    o.location[1] = 0.5
    assert paths.resolve(o, "location[1]") == 0.5


def test_set_indexed():
    o = Obj()
    paths.set_(o, "location[1]", 0.42)
    assert o.location[1] == 0.42


def test_set_plain_attr():
    o = Obj()
    o.child = Obj()
    paths.set_(o, "child.location[2]", 9.0)
    assert o.child.location[2] == 9.0


def test_bad_segment_raises():
    o = Obj()
    with pytest.raises(ValueError):
        paths.resolve(o, "loc[[1]")
