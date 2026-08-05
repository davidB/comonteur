"""comonteur:render must target the `timeline` scene explicitly.

A human can leave a different (possibly empty, cameraless) scene active in the GUI and
save — without `--scene timeline`, `blender -b timeline.blend -a` silently renders that
scene instead, failing with a generic "No camera found" error. No Blender needed: this
only checks the constructed command line.
"""

from pathlib import Path

import pytest
from _tasks import load

pytestmark = pytest.mark.task

render = load("render")


def test_render_targets_timeline_scene_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "timeline.blend").write_text("")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(render, "require_blender", lambda: "/usr/bin/blender")

    captured: list[str] = []

    def fake_execvp(_exe: str, cmd: list[str]) -> None:
        captured.extend(cmd)
        raise SystemExit(0)

    monkeypatch.setattr(render.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        render.main([])

    assert captured.index("--scene") < captured.index("-a")
    assert captured[captured.index("--scene") + 1] == "timeline"
