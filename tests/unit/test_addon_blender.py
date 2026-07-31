"""Driver for the in-Blender regression scripts in tests/blender/.

`addon/comonteur/` is bpy-locked, so none of it can be imported into this venv. Rather than
mock bpy — which would test the mock — each script runs in a real headless Blender:

    blender -b --python-exit-code 1 --python <script>

That flag makes Blender exit 1 when the script raises and 0 when it does not, so the whole
pass/fail protocol is the return code and each script body is plain `assert`. Nothing is
parsed out of stdout.

Blender's own startup noise (a `ModuleNotFoundError: No module named 'cattrs'` from its bundled
bl_pkg add-on on some installs, and an unregister_class complaint at teardown) does not affect
the return code, so nothing here asserts on clean stderr.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

BLENDER_DIR = Path(__file__).resolve().parents[1] / "blender"
SCRIPTS = sorted(p for p in BLENDER_DIR.glob("*.py") if not p.name.startswith("_"))

pytestmark = [
    pytest.mark.blender,
    pytest.mark.skipif(shutil.which("blender") is None, reason="blender not on PATH"),
]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_in_blender(script: Path, tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            shutil.which("blender") or "blender",
            "-b",
            # Without this, a dev install of the add-on (comonteur:install_addon symlinks
            # addon/comonteur into extensions/user_default) loads *as well* as the copy under
            # test. Two registered depsgraph handlers then run with two separate journal
            # _state dicts, so the installed one sees batch_active() == False and flips the
            # datablocks the copy under test just created to `shared` mid-batch. Tests must
            # exercise the working tree alone.
            "--factory-startup",
            "--python-exit-code",
            "1",
            # Blender ignores PYTHONPATH and does not put the script's own directory on
            # sys.path the way `python <file>` does, so `import _bl` would fail. Blender runs
            # --python-expr / --python in the order given, so this bootstrap lands first.
            "--python-expr",
            f"import sys; sys.path.insert(0, {str(BLENDER_DIR)!r})",
            "--python",
            str(script),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        # journal.py and preview.py fall back to os.getcwd() when the .blend is unsaved, so
        # without this every run would drop a .comonteur/ into whatever directory pytest
        # started in — the repo root. tmp_path also gives each script a fresh journal.
        cwd=tmp_path,
    )
    if proc.returncode != 0:
        # Blender prepends its banner to stdout; the traceback is what matters, so show both
        # streams rather than making someone re-run the command by hand to see the failure.
        pytest.fail(
            f"{script.name} failed in Blender (exit {proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )


def test_scripts_are_discovered() -> None:
    """A glob that silently matches nothing would make this whole file vacuously green."""
    assert SCRIPTS, f"no in-Blender scripts found in {BLENDER_DIR}"
