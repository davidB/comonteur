"""Pure-logic test for addon/comonteur/color.py — no bpy needed (SPEC.md §8)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "addon", "comonteur"))
import color  # noqa: E402

pytestmark = pytest.mark.pure


def test_srgb_to_linear_endpoints() -> None:
    assert color.srgb_to_linear(0.0) == 0.0
    assert color.srgb_to_linear(1.0) == pytest.approx(1.0)


def test_srgb_to_linear_below_threshold_is_linear_segment() -> None:
    # 0.04045 is the sRGB piecewise breakpoint; below it the transform is c / 12.92.
    assert color.srgb_to_linear(0.02) == pytest.approx(0.02 / 12.92)


def test_hex_to_rgba_black_and_white() -> None:
    assert color.hex_to_rgba("#000000") == (0.0, 0.0, 0.0, 1.0)
    r, g, b, a = color.hex_to_rgba("ffffff", a=0.5)
    assert (r, g, b, a) == pytest.approx((1.0, 1.0, 1.0, 0.5))


def test_hex_to_rgba_mid_gray_is_darker_than_naive_divide() -> None:
    # 0x80/255 = 0.502 sRGB; the whole point of the decode is that this is NOT ~0.5
    # linear -- a naive hex/255 pass-through would double-gamma-wash it lighter.
    r, _g, _b, _a = color.hex_to_rgba("#808080")
    assert r < 0.5
    assert r == pytest.approx(color.srgb_to_linear(0x80 / 255.0))
