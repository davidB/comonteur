"""Real F-curve tweens — SPEC.md §6.2. No drivers-as-animation, no baked transforms.
Every write goes through journal.set()/keyframe_insert inside journal.batch() — see
docs/M1-FINDINGS.md ("anim.tween/stagger must go through journal.set() ... or this bug
comes back per-module").
"""

import math
from typing import Any, Iterable

from . import journal, paths

# GSAP name -> (interpolation, easing). `.in`/`.out`/`.inOut` select easing; the base
# name selects interpolation. BEZIER's handles are computed separately (see _keyframe).
_INTERPOLATION = {
    "power1": "QUAD",
    "power2": "CUBIC",
    "power3": "QUART",
    "power4": "QUINT",
    "sine": "SINE",
    "expo": "EXPO",
    "circ": "CIRC",
    "back": "BACK",
    "elastic": "ELASTIC",
    "bounce": "BOUNCE",
    "linear": "LINEAR",
}
_EASING = {
    "in": "EASE_IN",
    "out": "EASE_OUT",
    "inOut": "EASE_IN_OUT",
}


def _parse_ease(ease: str | None) -> tuple[str, str]:
    if ease is None:
        return "BEZIER", "EASE_IN_OUT"
    if ease.startswith("cubic-bezier(") or ease == "CustomEase":
        return "BEZIER", "EASE_IN_OUT"
    name, _, suffix = ease.partition(".")
    interpolation = _INTERPOLATION.get(name, "BEZIER")
    easing = _EASING.get(suffix, "EASE_IN_OUT")
    return interpolation, easing


def _keyframe(
    obj: Any,
    path: str,
    index: int | None,
    frame: float,
    value: float,
    interpolation: str,
    easing: str,
) -> None:
    # A scalar property has no array index at all; passing index=0 for one is not a harmless
    # default — keyframe_insert rejects it and paths.resolve cannot subscript the value.
    # Fractional frames (e.g. pulse()'s start + dur*0.3) don't round-trip through
    # keyframe_insert() bit-for-bit, so an exact-float lookup below can miss. Round to
    # the whole frame a human scrubbing the timeline expects anyway.
    frame = round(frame)
    kw = {} if index is None else {"index": index}
    obj.keyframe_insert(path, frame=frame, **kw)
    # 5.2's layered-Action rework replaced Action.fcurves (see docs/M3-FINDINGS.md
    # Check 3) with layers/strips/channelbags; fcurve_ensure_for_datablock() is the
    # documented way to get the fcurve back without walking that structure.
    fc = obj.animation_data.action.fcurve_ensure_for_datablock(obj, path, index=index or 0)
    kf = next(k for k in fc.keyframe_points if k.co[0] == frame)
    kf.interpolation = interpolation
    kf.easing = easing
    if interpolation == "BEZIER":
        # Symmetric handles around the keyframe; a real editable Bezier, not a
        # custom evaluator (§6.2 forbids that) — the agent can still drag handles.
        kf.handle_left_type = kf.handle_right_type = "AUTO_CLAMPED"


def _sequence(
    obj: Any,
    path: str,
    index: int | None,
    start: float,
    dur: float,
    waypoints: Iterable[tuple[float, float]],
    interpolation: str,
    easing: str,
) -> None:
    """Emit one real keyframe per (t, value) waypoint, t a fraction of dur in [0, 1].
    Shared by pulse()/idle_jitter() — both are "base, then offsets of dur, back to
    base"; this keeps the frame math and _keyframe() insert/lookup in one place.
    """
    journal_path = path if index is None else f"{path}[{index}]"
    for t, value in waypoints:
        journal.set(obj, journal_path, value)
        _keyframe(obj, path, index, start + dur * t, value, interpolation, easing)


def tween(
    obj: Any,
    path: str,
    index: int | None,
    frm: float,
    to: float,
    start: float,
    dur: float,
    ease: str | None = None,
) -> None:
    """Set `path[index]` to `frm` at `start` and `to` at `start+dur`, both real
    keyframes. Must run inside journal.batch() (see module docstring).

    `index` is the array component (`location` X/Y/Z = 0/1/2, `rotation_euler` Y = 1 for a
    rotateY-equivalent tilt). Pass `index=None` for a scalar property, which has no
    components — the journal then records the bare path, so revert and claimed_paths() see
    the same string the human's edit would touch.
    """
    if not journal.batch_active():
        raise RuntimeError("anim.tween() must run inside journal.batch()")
    interpolation, easing = _parse_ease(ease)
    journal_path = path if index is None else f"{path}[{index}]"
    journal.set(obj, journal_path, frm)
    _keyframe(obj, path, index, start, frm, interpolation, easing)
    journal.set(obj, journal_path, to)
    _keyframe(obj, path, index, start + dur, to, interpolation, easing)


def stagger(
    objs: Iterable[Any], path: str, index: int | None, offset: float, **tween_kwargs: Any
) -> None:
    """tween() each object in objs, incrementing `start` by `offset` per object."""
    base_start = tween_kwargs.pop("start")
    for i, obj in enumerate(objs):
        tween(obj, path, index=index, start=base_start + i * offset, **tween_kwargs)


def idle_jitter(
    obj: Any,
    path: str,
    index: int | None,
    amplitude: float,
    cycles: int,
    start: float,
    dur: float,
    ease: str | None = None,
) -> None:
    """Sine-like oscillation around `path[index]`'s current value, baked as real
    keyframes (§6.2 forbids drivers-as-animation). Pre-sampled tween(), not a
    generic curve sampler: base -> (peak, trough) per cycle -> base.
    """
    if not journal.batch_active():
        raise RuntimeError("anim.idle_jitter() must run inside journal.batch()")
    interpolation, easing = _parse_ease(ease)
    journal_path = path if index is None else f"{path}[{index}]"
    base = paths.resolve(obj, journal_path)

    cycle = 1.0 / cycles
    waypoints = [(0.0, base)]
    for i in range(cycles):
        waypoints.append((cycle * (i + 0.25), base + amplitude))
        waypoints.append((cycle * (i + 0.75), base - amplitude))
    waypoints.append((1.0, base))
    _sequence(obj, path, index, start, dur, waypoints, interpolation, easing)


def pulse(
    obj: Any,
    path: str,
    index: int | None,
    peak: float,
    start: float,
    dur: float,
    ease: str | None = None,
) -> None:
    """One-shot spike around `path[index]`'s current value: base -> peak at 30% of
    `dur` -> back to base at `dur`. Distinct from idle_jitter() (a repeating
    peak/trough oscillation, base+amplitude/base-amplitude per cycle) — a flash-pulse
    decays back to base once, it doesn't wobble.
    """
    if not journal.batch_active():
        raise RuntimeError("anim.pulse() must run inside journal.batch()")
    interpolation, easing = _parse_ease(ease)
    journal_path = path if index is None else f"{path}[{index}]"
    base = paths.resolve(obj, journal_path)

    _sequence(
        obj, path, index, start, dur, [(0.0, base), (0.3, peak), (1.0, base)], interpolation, easing
    )


def hard_cut(obj: Any, visible_ranges: Iterable[tuple[int, int]]) -> None:
    """Instant show/hide (no crossfade): CONSTANT-interpolation keyframes on both
    hide_render and hide_viewport, hidden everywhere except the given inclusive
    (start_frame, end_frame) ranges. Must run inside journal.batch().

    Both properties get identical keyframes since hide_viewport also gates preview
    renders and measure()/dimensions (see text.measure()'s docstring) — a cut visible
    only in the final render but not in preview would silently mismeasure.
    """
    if not journal.batch_active():
        raise RuntimeError("anim.hard_cut() must run inside journal.batch()")
    events = [(1, True)]
    for start, end in sorted(visible_ranges):
        events.append((start, False))
        events.append((end + 1, True))
    for path in ("hide_render", "hide_viewport"):
        for frame, hidden in events:
            journal.set(obj, path, hidden)
            _keyframe(obj, path, None, frame, hidden, "CONSTANT", "EASE_IN_OUT")


def instance_as_nla(obj: Any, track_name: str, frame_offset: float) -> Any:
    """Push obj's current action onto an NLA track at frame_offset, so reusable
    motion is an Action instance (§6.2), not re-emitted keyframes.
    """
    if obj.animation_data is None or obj.animation_data.action is None:
        raise ValueError(f"{obj.name!r} has no action to instance")
    anim = obj.animation_data
    action = anim.action
    track = anim.nla_tracks.new()
    track.name = track_name
    anim.action = None
    strip = track.strips.new(action.name, math.ceil(frame_offset), action)
    strip.frame_start = frame_offset
    strip.frame_end = frame_offset + (action.frame_range[1] - action.frame_range[0])
    return strip
