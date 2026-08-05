"""The resolved-plan JSON is a contract between two processes that cannot import each other.

`comonteur:reconcile` runs outside Blender and writes `.comonteur/timeline.resolved.json`;
`addon/comonteur/reconcile.py` reads it inside Blender. Nothing type-checks across that gap and
nothing fails loudly when a key is renamed on one side — `apply()` falls back to a CROSS
transition and the edit is silently wrong. These tests hold both ends to the same spelling.

They also cover validation that belongs on the outside-Blender side by design (CLAUDE.md: the
add-on's input is the resolved plan, not the source document), so a malformed `source` has to be
caught here rather than raising deep inside `apply()`.
"""

import sys
from pathlib import Path

import pytest
from _tasks import load

pytestmark = pytest.mark.pure

task = load("reconcile")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "addon" / "comonteur"))
import reconcile as addon_reconcile  # noqa: E402


def _doc(**shot: object) -> dict[str, object]:
    base = {
        "id": "shot-01",
        "title": "test title",
        "source": {"kind": "movie", "path": "assets/a.mp4"},
        "start": 0,
        "duration": 30,
    }
    base.update(shot)
    return {"fps": 30, "resolution": [1920, 1080], "shots": [base]}


def test_transition_key_is_type_on_both_sides() -> None:
    """references/timeline.md documented this as `kind`; both implementations say `type`."""
    doc = _doc(transition={"type": "cross", "duration": 0.4})
    resolved = task.resolve(doc, transcript=None, fps=30)

    transition = resolved["shots"][0]["transition"]
    assert set(transition) == {"type", "duration_frames"}, transition
    assert transition["type"] == "cross"
    assert transition["duration_frames"] == 12  # 0.4s at 30fps

    # The add-on's lookup table is keyed by exactly what the task emits.
    assert transition["type"] in addon_reconcile._TRANSITION_TYPES


def test_resolved_shot_keys_match_what_the_addon_reads() -> None:
    resolved = task.resolve(_doc(), transcript=None, fps=30)
    shot = resolved["shots"][0]
    assert {"id", "source", "start_frame", "duration_frames", "in_frame"} <= set(shot), shot
    assert isinstance(shot["start_frame"], int)


def test_validate_rejects_unknown_source_kind() -> None:
    """`apply()` raises ValueError deep inside Blender for this; catch it outside instead."""
    errors = task.validate(_doc(source={"kind": "clip", "path": "a.mp4"}))
    assert any("kind" in e for e in errors), errors


def test_validate_rejects_source_missing_its_keys() -> None:
    errors = task.validate(_doc(source={"kind": "scene", "blend": "a.blend"}))
    assert any("scene" in e for e in errors), errors

    errors = task.validate(_doc(source={"kind": "movie"}))
    assert any("path" in e for e in errors), errors


def test_missing_source_is_a_valid_intent_only_stub_not_an_error() -> None:
    """A shot with no `source` yet isn't malformed — it's not built yet. It's excluded
    from the resolved plan (test_task_reconcile.py) rather than rejected here."""
    doc = _doc()
    del doc["shots"][0]["source"]
    assert task.validate(doc) == []


def test_known_source_kinds_agree_with_the_addon() -> None:
    """The task must not accept a kind that apply() will then reject."""
    for kind, extra in (
        ("scene", {"blend": "a.blend", "scene": "s"}),
        ("movie", {"path": "a.mp4"}),
    ):
        assert task.validate(_doc(source={"kind": kind, **extra})) == []
