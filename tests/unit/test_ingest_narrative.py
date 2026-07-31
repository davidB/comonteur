"""Pure-logic tests for the `comonteur:ingest_narrative` task script (SPEC.md §5.3).

Ported from cli/src/narrative.rs's #[cfg(test)] module when the Rust CLI was dissolved into
mise tasks.
"""

from pathlib import Path
from typing import Any

import pytest
from _tasks import load

pytestmark = pytest.mark.task

narrative = load("ingest_narrative")


def shot(shot_id: str, intent: str, target_duration: float | None = None) -> dict[str, Any]:
    return {"id": shot_id, "intent": intent, "target_duration": target_duration}


def test_valid_doc_has_no_errors() -> None:
    doc = {"shots": [shot("shot-01", "Hook", 6.0), shot("shot-02", "Payoff")]}
    assert narrative.validate(doc) == []


def test_empty_shots_errors() -> None:
    assert len(narrative.validate({"shots": []})) == 1


def test_missing_shots_key_errors() -> None:
    assert len(narrative.validate({})) == 1


def test_duplicate_id_errors() -> None:
    doc = {"shots": [shot("shot-01", "A"), shot("shot-01", "B")]}
    assert any("duplicate id" in e for e in narrative.validate(doc))


def test_missing_intent_errors() -> None:
    doc = {"shots": [shot("shot-01", "  ")]}
    assert any("empty `intent`" in e for e in narrative.validate(doc))


def test_empty_id_errors() -> None:
    doc = {"shots": [shot("", "Hook")]}
    assert any("empty `id`" in e for e in narrative.validate(doc))


def test_non_positive_duration_errors() -> None:
    doc = {"shots": [shot("shot-01", "Hook", 0.0)]}
    assert any("target_duration" in e for e in narrative.validate(doc))


def test_load_parses_real_toml(tmp_path: Path) -> None:
    path = tmp_path / "narrative.toml"
    path.write_text('[[shots]]\nid = "shot-01"\nintent = "Hook"\ntarget_duration = 6\n')
    doc = narrative.parse(path)
    assert len(doc["shots"]) == 1
    assert doc["shots"][0]["id"] == "shot-01"


def test_parse_raises_on_invalid_doc(tmp_path: Path) -> None:
    path = tmp_path / "narrative.toml"
    path.write_text("shots = []\n")
    with pytest.raises(SystemExit):
        narrative.parse(path)
