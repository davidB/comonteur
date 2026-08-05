"""The files `comonteur:init` scaffolds must survive the tools that read them next.

`init` is the first thing a user runs, and `reconcile` is close behind. A template that its own
parser rejects turns the documented first run into an error message, which is exactly the kind
of thing nobody notices from inside the repo — the maintainer always has a real timeline.toml.
"""

from pathlib import Path

import pytest
from _tasks import load

pytestmark = pytest.mark.task

TEMPLATES = Path(__file__).resolve().parents[2] / "skills" / "comonteur" / "templates"

reconcile = load("reconcile")


def test_timeline_template_passes_reconcile() -> None:
    """Shipped commented-out, `shots` parsed as empty and reconcile refused to resolve it."""
    doc = reconcile.parse(TEMPLATES / "timeline.toml")
    reconcile.validate(doc)  # raises SystemExit on a bad document

    assert doc["shots"], "the template must ship at least one usable [[shots]] block"
    assert doc["fps"] == 30
    assert doc["resolution"] == [1920, 1080]
    assert doc["shots"][0].get("intent"), "the shipped shot must state its intent too"


def test_timeline_template_resolves_to_frames() -> None:
    """The whole point of the template is to be runnable, not merely parseable."""
    doc = reconcile.parse(TEMPLATES / "timeline.toml")
    resolved = reconcile.resolve(doc, transcript=None, fps=doc["fps"])

    assert resolved["shots"], resolved
    for shot in resolved["shots"]:
        assert isinstance(shot["start_frame"], int), shot
        assert shot["duration_frames"] > 0, shot


def test_meta_template_is_valid_json() -> None:
    import json

    meta = json.loads((TEMPLATES / "meta.json").read_text())
    assert isinstance(meta, dict) and meta, meta
