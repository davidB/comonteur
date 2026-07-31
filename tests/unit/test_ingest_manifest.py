"""Pure-logic tests for the `comonteur:ingest_manifest` task script (SPEC.md §5.3).

Ported from cli/src/manifest.rs's #[cfg(test)] module when the Rust CLI was dissolved into
mise tasks. parse_probe() is tested against literal ffprobe fixtures — no subprocess.
"""

from pathlib import Path

import pytest
from _tasks import load

pytestmark = pytest.mark.task

manifest = load("ingest_manifest")


def test_plain_video_no_alpha() -> None:
    probe = {
        "format": {"duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "r_frame_rate": "30/1",
            }
        ],
    }
    info = manifest.parse_probe(probe)
    assert info["duration"] == 12.5
    assert info["fps"] == 30.0
    assert info["resolution"] == [1920, 1080]
    assert info["has_alpha"] is False
    assert info["codec"] == "h264"


def test_video_with_alpha() -> None:
    probe = {
        "format": {"duration": "3.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "prores",
                "width": 800,
                "height": 600,
                "pix_fmt": "yuva444p10le",
                "r_frame_rate": "24/1",
            }
        ],
    }
    assert manifest.parse_probe(probe)["has_alpha"] is True


def test_audio_only_has_no_resolution_or_fps() -> None:
    probe = {
        "format": {"duration": "45.2"},
        "streams": [{"codec_type": "audio", "codec_name": "pcm_s24le"}],
    }
    info = manifest.parse_probe(probe)
    assert info["duration"] == 45.2
    assert info["fps"] is None
    assert info["resolution"] is None
    assert info["has_alpha"] is False
    assert info["codec"] == "pcm_s24le"


def test_no_streams_returns_none_fields() -> None:
    info = manifest.parse_probe({"format": {}, "streams": []})
    assert info["duration"] is None
    assert info["resolution"] is None
    assert info["codec"] is None


def test_stream_duration_wins_over_format_duration() -> None:
    probe = {
        "format": {"duration": "99.0"},
        "streams": [{"codec_type": "video", "duration": "12.5", "r_frame_rate": "30/1"}],
    }
    assert manifest.parse_probe(probe)["duration"] == 12.5


def test_parse_rate_handles_zero_denominator() -> None:
    assert manifest.parse_rate("0/0") is None
    assert manifest.parse_rate("30000/1001") == 30000 / 1001
    assert manifest.parse_rate("garbage") is None


def test_sha256_matches_known_vector(tmp_path: Path) -> None:
    path = tmp_path / "hello.txt"
    path.write_bytes(b"hello world")
    assert (
        manifest.sha256_file(path)
        == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    )


def test_walk_files_skips_dotfiles_and_recurses(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "sub" / "b.mp4").write_bytes(b"b")
    (tmp_path / ".hidden").write_bytes(b"x")
    (tmp_path / "sub" / ".DS_Store").write_bytes(b"x")
    found = {p.relative_to(tmp_path).as_posix() for p in manifest.walk_files(tmp_path)}
    assert found == {"a.mp4", "sub/b.mp4"}
