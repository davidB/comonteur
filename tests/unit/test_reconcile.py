"""Pure-logic test for addon/comonteur/reconcile.py's diff() — no bpy needed
(SPEC.md §8). reconcile.py keeps its bpy-dependent submodules (journal/library/
provenance) imported locally inside apply(), so importing the module itself, and
calling diff(), never touches bpy.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "addon", "comonteur"))
import reconcile  # noqa: E402

pytestmark = pytest.mark.pure

FIELDS = ("frame_start", "frame_final_duration")


def test_new_id_is_created() -> None:
    desired = [{"id": "shot-01", "frame_start": 0, "frame_final_duration": 90}]
    plan = reconcile.diff(desired, existing={}, claimed={}, fields=FIELDS)
    assert plan.to_create == desired
    assert plan.to_update == []
    assert plan.to_delete == []


def test_unchanged_id_is_left_alone() -> None:
    desired = [{"id": "shot-01", "frame_start": 0, "frame_final_duration": 90}]
    existing = {
        "shot-01": {"origin": "agent", "fields": {"frame_start": 0, "frame_final_duration": 90}}
    }
    plan = reconcile.diff(desired, existing, claimed={}, fields=FIELDS)
    assert plan.to_create == []
    assert plan.to_update == []
    assert plan.to_delete == []


def test_changed_field_is_updated() -> None:
    desired = [{"id": "shot-01", "frame_start": 30, "frame_final_duration": 90}]
    existing = {
        "shot-01": {"origin": "agent", "fields": {"frame_start": 0, "frame_final_duration": 90}}
    }
    plan = reconcile.diff(desired, existing, claimed={}, fields=FIELDS)
    assert plan.to_update == [{"id": "shot-01", "fields": {"frame_start": 30}}]


def test_claimed_field_is_not_overwritten() -> None:
    desired = [{"id": "shot-01", "frame_start": 30, "frame_final_duration": 120}]
    existing = {
        "shot-01": {"origin": "shared", "fields": {"frame_start": 0, "frame_final_duration": 90}}
    }
    claimed = {"shot-01": {"frame_start"}}
    plan = reconcile.diff(desired, existing, claimed, fields=FIELDS)
    # frame_start is claimed (human edited it) -> skipped; frame_final_duration isn't -> updated
    assert plan.to_update == [{"id": "shot-01", "fields": {"frame_final_duration": 120}}]


def test_dropped_agent_owned_id_is_deleted() -> None:
    existing = {
        "shot-01": {"origin": "agent", "fields": {"frame_start": 0, "frame_final_duration": 90}}
    }
    plan = reconcile.diff([], existing, claimed={}, fields=FIELDS)
    assert plan.to_delete == ["shot-01"]


def test_dropped_shared_id_is_never_deleted() -> None:
    existing = {
        "shot-01": {"origin": "shared", "fields": {"frame_start": 0, "frame_final_duration": 90}}
    }
    plan = reconcile.diff([], existing, claimed={}, fields=FIELDS)
    assert plan.to_delete == []


def test_dropped_untagged_human_id_is_never_deleted() -> None:
    existing = {
        "hand-edit": {"origin": "human", "fields": {"frame_start": 0, "frame_final_duration": 90}}
    }
    plan = reconcile.diff([], existing, claimed={}, fields=FIELDS)
    assert plan.to_delete == []


def test_scene_range_derives_fps_resolution_and_frame_end() -> None:
    resolved = {
        "fps": 30,
        "resolution": [1920, 1080],
        "shots": [
            {"start_frame": 0, "duration_frames": 90},
            {"start_frame": 60, "duration_frames": 1174},  # ends latest, 1234
        ],
    }
    assert reconcile.scene_range(resolved) == {
        "fps": 30,
        "resolution": (1920, 1080),
        "frame_end": 1234,
    }


def test_scene_range_omits_frame_end_when_no_shots() -> None:
    resolved = {"fps": 30, "resolution": [1920, 1080], "shots": []}
    assert reconcile.scene_range(resolved) == {"fps": 30, "resolution": (1920, 1080)}


def test_scene_range_derives_container_from_codec() -> None:
    resolved = {"shots": [], "video_codec": "h264"}
    assert reconcile.scene_range(resolved)["video"] == ("H264", "MPEG4")


def test_scene_range_uses_explicit_container_override() -> None:
    resolved = {"shots": [], "video_codec": "av1", "video_container": "mkv"}
    assert reconcile.scene_range(resolved)["video"] == ("AV1", "MKV")


def test_scene_range_falls_back_to_mkv_for_unknown_codec() -> None:
    resolved = {"shots": [], "video_codec": "flac"}
    assert reconcile.scene_range(resolved)["video"] == ("FLAC", "MKV")


def test_scene_range_omits_video_when_no_codec() -> None:
    resolved = {"shots": []}
    assert "video" not in reconcile.scene_range(resolved)


def test_scene_range_passes_through_audio_codec() -> None:
    resolved = {"shots": [], "audio_codec": "opus"}
    assert reconcile.scene_range(resolved)["audio_codec"] == "OPUS"


def test_scene_range_omits_audio_codec_when_absent() -> None:
    resolved = {"shots": []}
    assert "audio_codec" not in reconcile.scene_range(resolved)


def test_dropped_agent_owned_id_with_claimed_field_is_not_deleted() -> None:
    # VSE strips aren't ID datablocks, so the automatic origin flip (SPEC.md §4.3)
    # never fires for a strip edit (docs/M4-FINDINGS.md) — origin can stay "agent"
    # even after a human touched the strip. `claimed` is the real signal here.
    existing = {
        "shot-01": {"origin": "agent", "fields": {"frame_start": 15, "frame_final_duration": 90}}
    }
    claimed = {"shot-01": {"frame_start"}}
    plan = reconcile.diff([], existing, claimed, fields=FIELDS)
    assert plan.to_delete == []
