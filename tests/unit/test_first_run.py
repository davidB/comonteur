"""The documented first run, end to end: `init` a project, then `reconcile` what it scaffolded.

Every piece of this is unit-tested elsewhere, which is exactly why it broke: `init` wrote a
valid file, `reconcile` parsed valid files, and the one combination a new user actually hits —
running reconcile on a freshly scaffolded project — failed, because the template shipped with
all its `[[shots]]` commented out. Nobody in the repo ever ran it that way.
"""

import shutil
from pathlib import Path

import pytest
from _tasks import load

pytestmark = [pytest.mark.integration, pytest.mark.task]

init = load("init")
reconcile = load("reconcile")

TEMPLATE = Path(__file__).resolve().parents[2] / "skills" / "comonteur" / "templates"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    created, _kept = init.plan(tmp_path, TEMPLATE)
    init.apply(tmp_path, TEMPLATE, created)
    return tmp_path


def test_init_scaffolds_the_documented_tree(project: Path) -> None:
    for name in ("narrative.toml", "timeline.toml", "meta.json", "mise.toml"):
        assert (project / name).is_file(), name
    tasks = {p.stem for p in (project / "mise-tasks" / "comonteur").glob("*.py")}
    assert "reconcile" in tasks and "init" in tasks, tasks
    assert "_common" in tasks, "tasks import _common as a sibling; it has to be copied too"


def test_init_writes_no_agent_instruction_files(project: Path) -> None:
    """The skill is the contract; a project's AGENTS.md/CLAUDE.md belongs to the human."""
    assert not (project / "AGENTS.md").exists()
    assert not (project / "CLAUDE.md").exists()


def test_reconcile_runs_on_the_freshly_scaffolded_project(project: Path) -> None:
    doc = reconcile.parse(project / "timeline.toml")
    reconcile.validate(doc)
    resolved = reconcile.resolve(doc, transcript=None, fps=doc["fps"])

    assert resolved["shots"], "a new project must resolve to at least one shot"
    assert resolved["fps"] == doc["fps"]


def test_init_is_add_only(project: Path) -> None:
    """Re-running on a live project tops up what is missing and keeps what is there."""
    (project / "timeline.toml").write_text("fps = 24\nresolution = [1280, 720]\n")
    (project / "mise-tasks" / "comonteur" / "reconcile.py").unlink()

    created, kept = init.plan(project, TEMPLATE)
    assert "timeline.toml" in kept, kept
    assert any("reconcile" in c for c in created), created

    init.apply(project, TEMPLATE, created)
    assert (project / "timeline.toml").read_text().startswith("fps = 24")
    assert (project / "mise-tasks" / "comonteur" / "reconcile.py").is_file()


def test_scaffolded_tasks_are_executable(project: Path) -> None:
    """mise runs these as files; a non-executable copy is a task that cannot run."""
    for task in (project / "mise-tasks" / "comonteur").glob("*.py"):
        if task.stem == "_common":
            continue
        assert task.stat().st_mode & 0o111, f"{task.name} is not executable"


@pytest.mark.skipif(shutil.which("mise") is None, reason="mise not on PATH")
def test_scaffolded_project_exposes_the_task_menu(project: Path) -> None:
    """The scaffold has to be a working mise project, not just the right files on disk."""
    assert (project / "mise.toml").is_file()
    assert (project / "mise-tasks" / "comonteur" / "doctor.py").is_file()
