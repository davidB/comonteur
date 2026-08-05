"""The `comonteur:*` task scripts declare what they take and what they need.

Two claims in the skill's own reference docs are only true if these hold, and an agent acts on
them without checking:

- references/workflows.md: "Check `--help` on a task rather than guessing its arguments; each
  one declares them in its own `#USAGE` header." A task that parses argv without a `#USAGE`
  header gives `mise run comonteur:<task> --help` nothing to print, so the agent guesses.
- The PEP 723 rule in CLAUDE.md: every task is stdlib-only so nothing has to be installed,
  with `convert_fonts` the single exception (WOFF2 needs a Brotli decoder the stdlib lacks).

These are cheap to check statically and expensive to notice by hand, which is why they drifted.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.task

TASKS_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "comonteur"
    / "templates"
    / "mise-tasks"
    / "comonteur"
)

# `_common.py` is deliberately not a task (no shebang, mode 644) — that is what keeps mise
# from listing it.
TASKS = sorted(p for p in TASKS_DIR.glob("*.py") if p.name != "_common.py")

# The one script allowed a third-party dependency, and why.
DEPS_EXEMPT = {"convert_fonts": "WOFF2 needs a Brotli decoder; the stdlib has none"}


def test_tasks_are_discovered() -> None:
    assert len(TASKS) == 11, [p.stem for p in TASKS]


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.stem)
def test_task_is_a_uv_script(task: Path) -> None:
    lines = task.read_text().splitlines()
    assert lines[0] == "#!/usr/bin/env -S uv run --script", lines[0]
    assert task.stat().st_mode & 0o111, "a task mise runs has to be executable"
    assert any(line.startswith("#MISE description=") for line in lines), (
        "without a description the task is invisible in `mise tasks`"
    )


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.stem)
def test_task_declares_its_arguments(task: Path) -> None:
    """A task that reads argv must say so in `#USAGE`, or `--help` is silent."""
    text = task.read_text()
    # Every task takes `argv` for symmetry, but `doctor` and `install` ignore it. What matters
    # is real use: indexing it, forwarding it, or handing it to argparse.
    body = text.replace("sys.argv[1:]", "")  # the entrypoint hand-off is not a use
    uses_argv = re.search(r"argv\[|\*argv|argparse", body) is not None
    declares = re.search(r"^#USAGE (arg|flag|complete)", text, re.M) is not None
    if uses_argv:
        assert declares, (
            f"{task.name} reads its arguments but declares no #USAGE header, so "
            f"`mise run comonteur:{task.stem} --help` documents nothing"
        )


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.stem)
def test_task_dependencies_stay_stdlib(task: Path) -> None:
    block = re.search(r"^# dependencies = (\[[^\]]*\])", task.read_text(), re.M)
    assert block, f"{task.name} has no PEP 723 dependencies line"
    declared = block.group(1) != "[]"
    if task.stem in DEPS_EXEMPT:
        assert declared, f"{task.stem} is listed as exempt but declares nothing — drop the entry"
    else:
        assert not declared, (
            f"{task.name} declares {block.group(1)}; tasks are stdlib-only so a user needs "
            f"nothing installed. If the stdlib genuinely cannot do it, add it to DEPS_EXEMPT "
            f"with a reason and update references/workflows.md."
        )
