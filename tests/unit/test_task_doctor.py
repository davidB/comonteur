"""Pure-logic tests for the `comonteur:doctor` task script.

Only the version policy is testable without Blender, and it is the one piece with a real
decision in it: pinned 5.2 passes, newer warns (probably fine, just not reproducible —
docs/constraints-and-risks.md §11), unreadable fails.
"""

import pytest
from _tasks import load

pytestmark = pytest.mark.task

doctor = load("doctor")


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("Blender 5.2.1\n\tbuild date: 2025-01-01", "ok"),
        ("Blender 5.2.0", "ok"),
        ("Blender 5.3.0", "warn"),
        ("Blender 4.2.0", "warn"),
        ("", "bad"),
        ("Segmentation fault", "bad"),
    ],
)
def test_classify_blender_version(output: str, expected: str) -> None:
    status, _ = doctor.classify_blender_version(output)
    assert status == expected


def test_message_names_the_pin_when_the_version_differs() -> None:
    status, message = doctor.classify_blender_version("Blender 5.3.0", pin="5.2")
    assert status == "warn"
    assert "5.3.0" in message
    assert "5.2" in message


def test_every_task_script_doctor_checks_for_actually_exists() -> None:
    """Guards the list against a rename: doctor reporting a missing script that was only
    renamed would send the user into a `setup` that fixes nothing.
    """
    from _tasks import TASKS_DIR

    missing = [n for n in doctor.TASK_SCRIPTS if not (TASKS_DIR / f"{n}.py").is_file()]
    assert missing == []
