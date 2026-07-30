"""Pure-logic tests for the `comonteur:init` task script (docs/data-contracts.md §5.1b).

The one rule worth a test is add-only: an existing file must land in `kept`, never in
`created`, because `apply()` writes exactly what `plan()` put in `created`.
"""

from pathlib import Path

import pytest
from _tasks import load

init = load("init")


@pytest.fixture
def template(tmp_path: Path) -> Path:
    """A minimal stand-in for skills/comonteur/templates/."""
    root = tmp_path / "template"
    tasks = root / "mise-tasks" / "comonteur"
    tasks.mkdir(parents=True)
    (tasks / "doctor.py").write_text("#!x")
    (tasks / "_common.py").write_text("x = 1")
    (tasks / "__pycache__").mkdir()
    (tasks / "__pycache__" / "stale.pyc").write_bytes(b"")
    for name in [*init.ROOT_FILES, "mise.toml"]:
        (root / name).write_text(f"{name} for __PROJECT_NAME__")
    return root


def test_sources_lists_tasks_and_root_files_but_not_pycache(template: Path) -> None:
    rels = init.sources(template)
    assert "mise-tasks/comonteur/doctor.py" in rels
    assert "mise-tasks/comonteur/_common.py" in rels
    assert not any("__pycache__" in rel for rel in rels)
    assert rels[-1] == "mise.toml"


def test_plan_on_empty_target_creates_everything(template: Path, tmp_path: Path) -> None:
    created, kept = init.plan(tmp_path / "project", template)
    assert kept == []
    assert set(created) == set(init.sources(template))


def test_plan_never_recreates_an_existing_file(template: Path, tmp_path: Path) -> None:
    target = tmp_path / "project"
    (target / "mise-tasks" / "comonteur").mkdir(parents=True)
    (target / "timeline.toml").write_text("mine")
    (target / "mise.toml").write_text("mine too")

    created, kept = init.plan(target, template)

    assert set(kept) == {"timeline.toml", "mise.toml"}
    assert "timeline.toml" not in created
    assert (target / "timeline.toml").read_text() == "mine"


def test_apply_is_idempotent(template: Path, tmp_path: Path) -> None:
    target = tmp_path / "my-video"
    target.mkdir()

    created, _ = init.plan(target, template)
    init.apply(target, template, created)

    # Everything is copied verbatim: no template file is rewritten on the way in.
    assert (target / "meta.json").read_text() == "meta.json for __PROJECT_NAME__"
    for d in init.DIRS:
        assert (target / d).is_dir()

    created_again, kept_again = init.plan(target, template)
    assert created_again == []
    assert set(kept_again) == set(created)


def test_lfs_without_git_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        init.parse_args(["--lfs"])
    assert excinfo.value.code == 2


def test_defaults_to_the_current_directory() -> None:
    args = init.parse_args([])
    assert (args.dir, args.git, args.lfs) == (".", False, False)
