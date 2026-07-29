"""M4 VSE assembly spike — run with: blender -b -P tests/m4/run_checks.py
Closes the VSE unknowns M0/M3 didn't cover: new_movie/new_sound signatures,
new_effect(CROSS) crossfade, linking a non-asset Scene (assets_only=False), custom
properties on movie/sound/effect strips surviving save/load, and channel-overlap
behaviour. Source for docs/M4-FINDINGS.md.
"""

import os
import shutil
import subprocess
import tempfile

import bpy

R: list[tuple[str, str, str]] = []


def report(id_: str, status: str, detail: str = "") -> None:
    R.append((id_, status, detail))
    print(f"[{id_}] {status}: {detail}")


def reset_file() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


tmpdir = tempfile.mkdtemp(prefix="cmt_m4_")

# --- fixture media: a tiny real movie + sound file via ffmpeg, so new_movie/new_sound
# have something real to point at (VSE strip creation reads the file's metadata) ---
movie_path = os.path.join(tmpdir, "clip.mp4")
sound_path = os.path.join(tmpdir, "tone.wav")
have_ffmpeg = shutil.which("ffmpeg") is not None
if have_ffmpeg:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:d=1:r=30",
            movie_path,
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            sound_path,
        ],
        check=True,
    )
else:
    report("M4.fixtures", "FAIL", "ffmpeg not on PATH, skipping media-strip checks")

# --- non-asset scene to link: a plain generated scene, NOT asset_mark()-ed ---
lib_path = os.path.join(tmpdir, "shot-01.blend")
reset_file()
plain_scene = bpy.data.scenes[0]
plain_scene.name = "GEN_hook"
plain_scene["cmt_id"] = "shot-01"
plain_scene["cmt_origin"] = "agent"
bpy.ops.wm.save_as_mainfile(filepath=lib_path)

# --- M4.link_non_asset: bpy.data.libraries.load without assets_only ---
reset_file()
host = bpy.data.scenes[0]
host.name = "Host"
if not host.sequence_editor:
    host.sequence_editor_create()
try:
    with bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
        if "GEN_hook" not in data_from.scenes:
            raise ValueError(f"GEN_hook not in {list(data_from.scenes)}")
        data_to.scenes = ["GEN_hook"]
    linked_scene = bpy.data.scenes["GEN_hook"]
    report(
        "M4.link_non_asset",
        linked_scene.get("cmt_id") == "shot-01",
        f"linked plain scene, cmt_id={linked_scene.get('cmt_id')!r}",
    )
except Exception as e:  # noqa: BLE001
    report("M4.link_non_asset", False, f"raised: {e!r}")
    linked_scene = None

scene_strip = None
if linked_scene is not None:
    try:
        scene_strip = host.sequence_editor.strips.new_scene(
            name="ShotStrip", scene=linked_scene, channel=1, frame_start=1
        )
        scene_strip["cmt_id"] = "shot-01"
        scene_strip["cmt_origin"] = "agent"
        report("M4.new_scene_strip", True, f"created {scene_strip.name!r}")
    except Exception as e:  # noqa: BLE001
        report("M4.new_scene_strip", False, f"raised: {e!r}")

# --- M4.new_movie: signature/kwargs, frame_final_duration reflects media length ---
movie_strip = None
if have_ffmpeg:
    try:
        movie_strip = host.sequence_editor.strips.new_movie(
            name="MovieStrip", filepath=movie_path, channel=2, frame_start=100
        )
        movie_strip["cmt_id"] = "shot-02"
        movie_strip["cmt_origin"] = "agent"
        report(
            "M4.new_movie",
            True,
            f"created {movie_strip.name!r} frame_final_duration={movie_strip.frame_final_duration}",
        )
    except Exception as e:  # noqa: BLE001
        report("M4.new_movie", False, f"raised: {e!r}")

# --- M4.new_sound: signature/kwargs ---
sound_strip = None
if have_ffmpeg:
    try:
        sound_strip = host.sequence_editor.strips.new_sound(
            name="SoundStrip", filepath=sound_path, channel=3, frame_start=1
        )
        sound_strip["cmt_id"] = "vo"
        sound_strip["cmt_origin"] = "agent"
        report(
            "M4.new_sound",
            True,
            f"created {sound_strip.name!r} frame_final_duration={sound_strip.frame_final_duration}",
        )
    except Exception as e:  # noqa: BLE001
        report("M4.new_sound", False, f"raised: {e!r}")

# --- M4.new_effect CROSS: crossfade between two overlapping strips ---
if have_ffmpeg:
    try:
        a = host.sequence_editor.strips.new_movie(
            name="A", filepath=movie_path, channel=4, frame_start=1
        )
        b = host.sequence_editor.strips.new_movie(
            name="B", filepath=movie_path, channel=4, frame_start=int(a.frame_final_end - 10)
        )
        cross = host.sequence_editor.strips.new_effect(
            name="AxB",
            type="CROSS",
            channel=5,
            frame_start=int(b.frame_start),
            length=int(a.frame_final_end - b.frame_start),
            input1=a,
            input2=b,
        )
        cross["cmt_id"] = "shot-01:transition"
        cross["cmt_origin"] = "agent"
        report(
            "M4.new_effect_cross",
            True,
            f"created {cross.name!r} frame_start={cross.frame_start} "
            f"frame_final_duration={cross.frame_final_duration}",
        )
    except Exception as e:  # noqa: BLE001
        report("M4.new_effect_cross", False, f"raised: {e!r}")
        cross = None
else:
    cross = None

# --- M4.channel_overlap: two strips, same channel, overlapping frame ranges ---
try:
    c1 = host.sequence_editor.strips.new_effect(
        name="Overlap1", type="COLOR", channel=10, frame_start=1, length=50
    )
    c2 = host.sequence_editor.strips.new_effect(
        name="Overlap2", type="COLOR", channel=10, frame_start=25, length=50
    )
    report(
        "M4.channel_overlap",
        "INFO",
        f"no exception; c1=[{c1.frame_start},{c1.frame_final_end}) "
        f"c2=[{c2.frame_start},{c2.frame_final_end}) channel={c1.channel}/{c2.channel}",
    )
except Exception as e:  # noqa: BLE001
    report("M4.channel_overlap", "INFO", f"raised: {e!r}")

# --- M4.custom_props_survive: save/load round trip for movie/sound/effect strips ---
saved_path = os.path.join(tmpdir, "m4_strips.blend")
bpy.ops.wm.save_as_mainfile(filepath=saved_path)
reset_file()
bpy.ops.wm.open_mainfile(filepath=saved_path)
host2 = bpy.data.scenes["Host"]
strips2 = host2.sequence_editor.strips

checks = []
if scene_strip is not None:
    checks.append(("scene", strips2.get("ShotStrip")))
if movie_strip is not None:
    checks.append(("movie", strips2.get("MovieStrip")))
if sound_strip is not None:
    checks.append(("sound", strips2.get("SoundStrip")))
if cross is not None:
    checks.append(("effect", strips2.get("AxB")))

for kind, strip in checks:
    ok = strip is not None and strip.get("cmt_id") is not None
    report(
        "M4.custom_props_survive",
        ok,
        f"{kind} strip cmt_id after save/load: {strip.get('cmt_id') if strip else None!r}",
    )

failures = [r for r in R if r[1] is False]
print(f"\n{len(R) - len(failures)}/{len(R)} passed")
if failures:
    raise SystemExit(1)
