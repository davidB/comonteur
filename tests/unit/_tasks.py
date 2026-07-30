"""Loader for the `comonteur:*` mise task scripts (SPEC.md §8.2).

The task scripts live in `skills/comonteur/templates/mise-tasks/comonteur/` — the single
copy that `comonteur:init` installs into a user project — so tests reach across to them
rather than duplicating the logic.

They are loaded under prefixed module names because `reconcile.py` exists on both sides of
the Blender boundary: the task script here, and `addon/comonteur/reconcile.py` which
`test_reconcile.py` imports. A plain `import reconcile` would return whichever landed in
`sys.modules` first.

Each script guards its side effects behind `if __name__ == "__main__":`, so importing one
runs no I/O. PEP 723 headers declare the deps for `uv run`; the pytest env declares them
separately in `tests/pyproject.toml`.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

TASKS_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "comonteur"
    / "templates"
    / "mise-tasks"
    / "comonteur"
)


def load(name: str) -> ModuleType:
    """Import task script `<name>.py` as module `cmt_task_<name>`."""
    mod_name = f"cmt_task_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    path = TASKS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load task script {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    # No __pycache__ inside the skill: comonteur:init copies that directory into a user's
    # project file by file, and a stray subdirectory there makes its `cp` fail.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module
