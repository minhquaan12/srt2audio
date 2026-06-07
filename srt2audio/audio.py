"""Audio helpers: load, time-stretch (atempo) and timeline assembly."""

from __future__ import annotations

import io
from typing import Iterable, List, Tuple

from pydub import AudioSegment

# Common output format for the assembled timeline. The CapCut TTS server
# returns 24 kHz mono WAV; we normalise every segment to this so overlays line
# up sample-for-sample.
TARGET_FRAME_RATE = 24000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # 16-bit


def load_wav_bytes(data: bytes) -> AudioSegment:
    """Load WAV bytes returned by the TTS server into an :class:`AudioSegment`."""

    return AudioSegment.from_file(io.BytesIO(data))


def normalize(segment: AudioSegment) -> AudioSegment:
    """Coerce a segment to the canonical frame rate / channels / width."""

    return (
        segment.set_frame_rate(TARGET_FRAME_RATE)
        .set_channels(TARGET_CHANNELS)
        .set_sample_width(TARGET_SAMPLE_WIDTH)
    )


def _atempo_chain(factor: float) -> List[str]:
    """Decompose a tempo ``factor`` into ffmpeg ``atempo`` filters.

    ffmpeg's ``atempo`` only accepts values in [0.5, 2.0], so larger speed-ups
    are achieved by chaining multiple filters together.
    """

    filters: List[str] = []
    remaining = factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return filters


def time_stretch(segment: AudioSegment, factor: float) -> AudioSegment:
    """Change playback speed by ``factor`` while preserving pitch.

    ``factor > 1`` makes the audio faster (shorter); ``factor < 1`` slower.
    """

    if abs(factor - 1.0) < 1e-3 or len(segment) == 0:
        return segment

    filters = ",".join(_atempo_chain(factor))
    out = io.BytesIO()
    segment.export(
        out,
        format="wav",
        parameters=["-filter:a", filters],
    )
    out.seek(0)
    return AudioSegment.from_file(out, format="wav")


def fit_to_duration(
    segment: AudioSegment,
    target_ms: int,
    max_speed: float = 2.0,
) -> Tuple[AudioSegment, float]:
    """Speed up ``segment`` so it fits within ``target_ms``.

    Returns the (possibly stretched) segment and the applied speed factor.
    Audio shorter than ``target_ms`` is returned unchanged (the surrounding
    silence on the timeline fills the remaining gap). The speed factor is
    capped at ``max_speed`` so the voice stays intelligible; in that case the
    segment may slightly exceed ``target_ms``.
    """

    duration = len(segment)
    if target_ms <= 0 or duration <= target_ms:
        return segment, 1.0

    factor = duration / target_ms
    if max_speed > 0:
        factor = min(factor, max_speed)
    if factor <= 1.0:
        return segment, 1.0
    return time_stretch(segment, factor), factor


def build_timeline(
    placements: Iterable[Tuple[int, AudioSegment]],
    total_ms: int = 0,
) -> AudioSegment:
    """Overlay segments onto a silent base track at their start positions.

    ``placements`` is an iterable of ``(start_ms, segment)``. The result length
    is at least ``total_ms`` and large enough to contain every placed segment.
    """

    items = list(placements)
    end_ms = total_ms
    for start_ms, segment in items:
        end_ms = max(end_ms, start_ms + len(segment))

    base = AudioSegment.silent(duration=max(end_ms, 0), frame_rate=TARGET_FRAME_RATE)
    base = base.set_channels(TARGET_CHANNELS).set_sample_width(TARGET_SAMPLE_WIDTH)

    for start_ms, segment in items:
        base = base.overlay(normalize(segment), position=max(0, start_ms))
    return base


def export_audio(
    segment: AudioSegment,
    out_path: str,
    fmt: str = "wav",
    bitrate: str = "192k",
) -> None:
    """Export the assembled timeline to ``out_path`` in ``fmt``."""

    params = {}
    if fmt in ("mp3", "m4a", "aac"):
        params["bitrate"] = bitrate
    export_format = "ipod" if fmt == "m4a" else fmt
    segment.export(out_path, format=export_format, **params)
