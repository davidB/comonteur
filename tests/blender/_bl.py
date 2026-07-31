"""Prelude for the in-Blender regression scripts (see unit/test_addon_blender.py).

These files are *not* pytest tests. Each runs inside a headless Blender under
`blender -b --python-exit-code 1 --python <file>`, which exits 1 when the script raises — so a
plain `assert` is the whole reporting mechanism, and no pytest has to exist inside Blender.

`addon/` goes on `sys.path` directly rather than being installed as an extension: it is the
dev-checkout import path SKILL.md already documents, it tests the working tree instead of
whatever `comonteur:install_addon` last symlinked, and it needs no Blender preferences write.
"""

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "addon"))

import comonteur as cmt  # noqa: E402


def setup() -> Any:
    """Register the add-on and return the `cmt` module."""
    cmt.register()
    return cmt


def raises(exc: type[BaseException], fn: Any) -> BaseException | None:
    """Return the exception `fn` raised if it is an `exc`, else None. Re-raises anything else,
    so a test that expects a TypeError is not silently satisfied by an unrelated crash.
    """
    try:
        fn()
    except exc as e:
        return e
    return None
