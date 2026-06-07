"""Entry point: ``python -m srt2audio`` launches the GUI.

A small headless CLI is also provided for automation / testing:

    python -m srt2audio --cli input.srt output.wav --base-url http://localhost:8080
"""

from __future__ import annotations

import argparse
import sys


def _run_cli(argv: list[str]) -> int:
    from .processor import export_job, run_job
    from .srt_parser import parse_srt_file
    from .tts_client import CapCutTTSClient, DEFAULT_BASE_URL, TTSParams

    parser = argparse.ArgumentParser(prog="srt2audio", description="SRT -> audio via CapCut TTS")
    parser.add_argument("srt", help="Input .srt file")
    parser.add_argument("out", help="Output audio file")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--voice", type=int, default=0)
    parser.add_argument("--pitch", type=int, default=10)
    parser.add_argument("--speed", type=int, default=10)
    parser.add_argument("--volume", type=int, default=10)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--max-speed", type=float, default=2.0)
    parser.add_argument("--format", default="wav")
    args = parser.parse_args(argv)

    subtitles = parse_srt_file(args.srt)
    client = CapCutTTSClient(base_url=args.base_url)
    params = TTSParams(
        voice_type=args.voice, pitch=args.pitch, speed=args.speed, volume=args.volume
    )
    job = run_job(
        subtitles,
        client,
        params,
        max_workers=args.workers,
        max_speed=args.max_speed,
        log_cb=lambda m: print(m, flush=True),
    )
    if job.timeline is None:
        print("No audio produced.", file=sys.stderr)
        return 1
    export_job(job, args.out, fmt=args.format)
    print(f"Wrote {args.out} ({job.success_count} ok, {job.failure_count} failed)")
    return 0


def main() -> int:
    if "--cli" in sys.argv:
        argv = [a for a in sys.argv[1:] if a != "--cli"]
        return _run_cli(argv)
    from .gui import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
