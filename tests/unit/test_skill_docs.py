"""The skill's docs are the whole contract, so their checkable claims get checked.

Nobody clones this repo — users run `npx skills add`, so SKILL.md plus references/ is all an
agent ever sees. When those drift from the code there is no compiler, no import error and no
runtime failure on this side to catch it; the agent simply does the wrong thing in someone
else's Blender. Every assertion here corresponds to a drift that actually happened.

Only mechanically checkable claims belong here — task names, paths, forbidden invocations.
Prose accuracy is a review problem, not a test problem.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.task

SKILL = Path(__file__).resolve().parents[2] / "skills" / "comonteur"
TASKS_DIR = SKILL / "templates" / "mise-tasks" / "comonteur"
DOCS = sorted(SKILL.rglob("*.md"))
TASK_NAMES = {p.stem for p in TASKS_DIR.glob("*.py") if p.name != "_common.py"}


def test_docs_are_discovered() -> None:
    assert len(DOCS) >= 5, [p.name for p in DOCS]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_referenced_tasks_exist(doc: Path) -> None:
    """A `mise run comonteur:<task>` in the docs must name a real script."""
    named = set(re.findall(r"comonteur:(\w+)", doc.read_text()))
    # `comonteur:` also prefixes non-task things in prose (the namespace itself, `comonteur:*`).
    unknown = {n for n in named if n not in TASK_NAMES}
    assert not unknown, f"{doc.name} names tasks that do not exist: {sorted(unknown)}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_docs_do_not_teach_running_tasks_by_path(doc: Path) -> None:
    """SKILL.md tells the agent to prefer the task over the raw command it wraps; `init` is the
    documented single exception, since it is what creates the tasks in the first place.
    """
    text = doc.read_text()
    by_path = re.findall(r"(?:\./|uv run [^\n`]*)mise-tasks/comonteur/(\w+)\.py", text)
    offenders = {name for name in by_path if name != "init"}
    assert not offenders, (
        f"{doc.name} tells the agent to run {sorted(offenders)} by path; use "
        f"`mise run comonteur:<task>` so the human can re-run it and the tools stay pinned"
    )


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_docs_do_not_recommend_uvx_for_wrapped_tools(doc: Path) -> None:
    """convert_fonts exists because the raw fonttools CLI cannot do the job: `decompress`
    covers woff2 only, and plain .woff has no CLI verb at all. A doc that suggests the raw
    command sends the agent down a path that silently handles half the fonts.
    """
    hits = [line for line in doc.read_text().splitlines() if "uvx" in line and "fonttools" in line]
    assert not hits, f"{doc.name} recommends raw fonttools: {hits}"


def test_skill_frontmatter_is_present() -> None:
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\n"), "SKILL.md needs YAML frontmatter to be installable"
    front = text.split("---", 2)[1]
    assert re.search(r"^name: ", front, re.M), front
    assert re.search(r"^description: ", front, re.M), front


def test_routing_table_points_at_files_that_exist() -> None:
    text = (SKILL / "SKILL.md").read_text()
    for ref in set(re.findall(r"references/([\w.-]+\.md)", text)):
        assert (SKILL / "references" / ref).is_file(), f"SKILL.md routes to missing {ref}"
