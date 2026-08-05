"""Tests for the `comonteur:convert_fonts` task script.

Font fixtures are built in-memory with `fontTools.fontBuilder.FontBuilder` rather than
shipping binary files — same approach fontTools's own test suite uses for throwaway fonts.
`.woff` (not `.woff2`) stands in for a web font here: fontTools's woff2 writer needs the
`brotli` extra, which this venv doesn't carry (only `convert_fonts.py`'s own PEP 723 header
does) — `.woff` uses zlib and needs nothing extra, and `convert_fonts.py` treats both
identically (`SUFFIXES = (".woff", ".woff2")`).
"""

from __future__ import annotations

import io
import string
from pathlib import Path

import pytest
from _tasks import load
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph

pytestmark = pytest.mark.task

convert_fonts = load("convert_fonts")

FULL_BASIC = string.ascii_letters + string.digits


def _build_font(chars: str, *, family: str = "Test Sans", weight: int = 400) -> TTFont:
    fb = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef", *(f"g{ord(c):04x}" for c in chars)]
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({ord(c): f"g{ord(c):04x}" for c in chars})
    fb.setupGlyf({name: Glyph() for name in glyph_order})
    fb.setupHorizontalMetrics({name: (600, 0) for name in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(usWeightClass=weight)
    fb.setupPost()
    fb.setupMaxp()
    return fb.font


def _write_ttf(path: Path, chars: str, **kw: object) -> None:
    _build_font(chars, **kw).save(str(path))  # type: ignore[arg-type]


def _write_woff(path: Path, chars: str, **kw: object) -> None:
    font = _build_font(chars, **kw)  # type: ignore[arg-type]
    font.flavor = "woff"
    font.save(str(path))


# --- missing_basic_glyphs: pure, no font fixture needed --------------------------------


def test_missing_basic_glyphs_reports_gaps() -> None:
    cmap = {ord(c): f"g{ord(c):x}" for c in string.ascii_lowercase}
    missing = convert_fonts.missing_basic_glyphs(cmap)
    assert missing == set(string.ascii_uppercase + string.digits)


def test_missing_basic_glyphs_empty_when_full() -> None:
    cmap = {ord(c): f"g{ord(c):x}" for c in FULL_BASIC}
    assert convert_fonts.missing_basic_glyphs(cmap) == set()


def test_missing_basic_glyphs_empty_cmap_is_everything() -> None:
    assert convert_fonts.missing_basic_glyphs({}) == set(FULL_BASIC)


# --- family_name / weight_class ---------------------------------------------------------


def test_family_name_and_weight_class() -> None:
    font = _build_font("abc", family="Acme Sans", weight=600)
    assert convert_fonts.family_name(font) == "Acme Sans"
    assert convert_fonts.weight_class(font) == 600


# --- fetch_full_ttf: network mocked, no live calls ---------------------------------------


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


def test_fetch_full_ttf_downloads_the_ttf_url(monkeypatch: pytest.MonkeyPatch) -> None:
    css = 'src: url(https://fonts.gstatic.com/s/acme/v1/abc.ttf) format("truetype");'
    calls: list[object] = []

    def fake_urlopen(req: object, timeout: float | None = None) -> _FakeResponse:
        calls.append(req)
        return _FakeResponse(css.encode() if len(calls) == 1 else b"FAKE-FONT-BYTES")

    monkeypatch.setattr(convert_fonts.urllib.request, "urlopen", fake_urlopen)
    assert convert_fonts.fetch_full_ttf("Acme Sans", 600) == b"FAKE-FONT-BYTES"
    assert len(calls) == 2


def test_fetch_full_ttf_none_when_css_has_no_ttf_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        convert_fonts.urllib.request, "urlopen", lambda req, timeout=None: _FakeResponse(b"nope")
    )
    assert convert_fonts.fetch_full_ttf("Nope", 400) is None


def test_fetch_full_ttf_none_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_err(req: object, timeout: float | None = None) -> _FakeResponse:
        raise convert_fonts.urllib.error.URLError("boom")

    monkeypatch.setattr(convert_fonts.urllib.request, "urlopen", raise_err)
    assert convert_fonts.fetch_full_ttf("Acme Sans", 400) is None


# --- regressions mapping to the two real bug reports -------------------------------------


def test_check_coverage_warns_on_subsetted_woff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.woff2`/`.woff` that's already missing basic glyphs converts cleanly and stays
    broken today, with no signal at all — this is the "silent" half of the bug.
    """
    assets = tmp_path / "assets"
    assets.mkdir()
    src = assets / "inter-400.woff"
    _write_woff(src, "inter", family="Inter", weight=400)

    convert_fonts.convert(src)
    capsys.readouterr()

    convert_fonts.check_coverage([assets], fetch_full=False)
    assert "missing basic glyphs" in capsys.readouterr().out


def test_check_coverage_flags_raw_ttf_shard_with_no_conversion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A CDN unicode-range shard captured directly as `.ttf` (no `.woff2` involved at all) —
    a check wired only into `convert()` would never see this file.
    """
    assets = tmp_path / "assets"
    assets.mkdir()
    _write_ttf(assets / "brand.ttf", "abc", family="Brand Sans", weight=400)

    convert_fonts.check_coverage([assets], fetch_full=False)
    assert "missing basic glyphs" in capsys.readouterr().out


def test_convert_does_not_clobber_better_existing_output(tmp_path: Path) -> None:
    """The transcript scenario: a hand-fixed full `.ttf` already sits next to the still-bad
    `.woff2`. A `--force` reconversion must not overwrite it with the worse coverage.
    """
    src = tmp_path / "inter-400.woff"
    _write_woff(src, "inter", family="Inter", weight=400)
    out = tmp_path / "inter-400.ttf"
    _write_ttf(out, FULL_BASIC, family="Inter", weight=400)
    original = out.read_bytes()

    result = convert_fonts.convert(src)

    assert result is None
    assert out.read_bytes() == original


def test_check_coverage_fetch_full_repairs_the_font(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    bad = assets / "brand.ttf"
    _write_ttf(bad, "abc", family="Brand Sans", weight=400)

    full_font = _build_font(FULL_BASIC, family="Brand Sans", weight=400)
    buf = io.BytesIO()
    full_font.save(buf)

    monkeypatch.setattr(convert_fonts, "fetch_full_ttf", lambda family, weight: buf.getvalue())
    convert_fonts.check_coverage([assets], fetch_full=True)

    refreshed = TTFont(str(bad))
    assert convert_fonts.missing_basic_glyphs(refreshed.getBestCmap() or {}) == set()
