"""Orchestration: synthesize every cue concurrently and assemble the timeline."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, List, Optional

from pydub import AudioSegment

from .audio import build_timeline, export_audio, fit_to_duration, load_wav_bytes, normalize
from .srt_parser import Subtitle
from .tts_client import CapCutTTSClient, TTSParams

MAX_WORKERS_LIMIT = 500

ProgressCallback = Callable[[int, int], None]
LogCallback = Callable[[str], None]


@dataclass
class SegmentResult:
    index: int
    start_ms: int
    end_ms: int
    text: str
    audio: Optional[AudioSegment] = None
    original_ms: int = 0
    final_ms: int = 0
    speed_factor: float = 1.0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.audio is not None


@dataclass
class JobResult:
    results: List[SegmentResult]
    timeline: Optional[AudioSegment]
    cancelled: bool = False

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.ok)


def _clamp_workers(value: int) -> int:
    return max(1, min(MAX_WORKERS_LIMIT, int(value)))


def _process_one(
    sub: Subtitle,
    client: CapCutTTSClient,
    params: TTSParams,
    max_speed: float,
) -> SegmentResult:
    result = SegmentResult(
        index=sub.index,
        start_ms=sub.start_ms,
        end_ms=sub.end_ms,
        text=sub.text,
    )
    try:
        wav_bytes = client.synthesize(sub.text, params)
        segment = normalize(load_wav_bytes(wav_bytes))
        result.original_ms = len(segment)
        fitted, factor = fit_to_duration(segment, sub.duration_ms, max_speed)
        result.audio = fitted
        result.final_ms = len(fitted)
        result.speed_factor = factor
    except Exception as exc:  # noqa: BLE001 - surface any failure per-segment
        result.error = str(exc)
    return result


def run_job(
    subtitles: List[Subtitle],
    client: CapCutTTSClient,
    params: TTSParams,
    *,
    max_workers: int = 16,
    max_speed: float = 2.0,
    progress_cb: Optional[ProgressCallback] = None,
    log_cb: Optional[LogCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> JobResult:
    """Synthesize every cue concurrently then assemble them in timeline order.

    Concurrency does not affect ordering: each result is stored against its cue
    index and the final timeline overlays segments at their absolute start
    times, so output is always correctly ordered.
    """

    workers = _clamp_workers(max_workers)
    total = len(subtitles)
    results_by_index: dict[int, SegmentResult] = {}
    done = 0

    def log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    def report() -> None:
        if progress_cb:
            progress_cb(done, total)

    log(f"Bắt đầu xử lý {total} đoạn với {workers} luồng (giới hạn {MAX_WORKERS_LIMIT}).")
    report()

    cancelled = False
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_sub = {}
        for sub in subtitles:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            future_to_sub[executor.submit(_process_one, sub, client, params, max_speed)] = sub

        for future in as_completed(future_to_sub):
            sub = future_to_sub[future]
            result = future.result()
            results_by_index[sub.index] = result
            done += 1
            if result.ok:
                note = ""
                if result.speed_factor > 1.0:
                    note = f" (tăng tốc x{result.speed_factor:.2f})"
                log(f"[{done}/{total}] OK #{sub.index} {result.original_ms}ms -> {result.final_ms}ms{note}")
            else:
                log(f"[{done}/{total}] LỖI #{sub.index}: {result.error}")
            report()
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True

    ordered = [results_by_index[s.index] for s in subtitles if s.index in results_by_index]
    ordered.sort(key=lambda r: (r.start_ms, r.index))

    if cancelled:
        log("Đã hủy. Không ghép timeline.")
        return JobResult(results=ordered, timeline=None, cancelled=True)

    placements = [(r.start_ms, r.audio) for r in ordered if r.ok and r.audio is not None]
    total_ms = max((s.end_ms for s in subtitles), default=0)
    log("Đang ghép các đoạn theo timeline...")
    timeline = build_timeline(placements, total_ms=total_ms) if placements else None
    log("Hoàn tất ghép timeline.")
    return JobResult(results=ordered, timeline=timeline, cancelled=False)


def export_job(job: JobResult, out_path: str, fmt: str = "wav", bitrate: str = "192k") -> None:
    if job.timeline is None:
        raise RuntimeError("No timeline to export (job had no successful segments).")
    export_audio(job.timeline, out_path, fmt=fmt, bitrate=bitrate)
