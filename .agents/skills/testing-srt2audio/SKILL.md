---
name: testing-srt2audio
description: Test the srt2audio SRT-to-audio tool end-to-end (GUI + CLI) against the CapCut-TTS wrapper. Use when verifying SRT parsing, per-cue speed-up, timeline alignment, threading, or the GUI.
---

# Testing srt2audio

srt2audio is a **client** of the `kuwacom/CapCut-TTS` wrapper server. It parses an
`.srt`, calls `GET /v1/synthesize` per cue (concurrently), speeds up over-long
cues with ffmpeg `atempo` to fit their slot, and overlays each cue at its
absolute start time so the result is timeline-aligned.

## Environment
- Needs `ffmpeg` on PATH and a venv with `PySide6`, `requests`, `pydub`.
  - `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- GUI is PySide6 and renders on `DISPLAY=:0`. Maximize with
  `wmctrl -r "SRT" -b add,maximized_vert,maximized_horz`.
- Note: the repo's pyenv python may lack `_tkinter`; that's fine — this app uses
  PySide6, not tkinter.

## Testing without real CapCut (recommended for logic/UI proof)
Real voices require a running CapCut-TTS server (see secrets below). For logic/UI
tests use the bundled mock, which returns a tone whose length scales with text:
```
.venv/bin/python tools/mock_tts_server.py --port 8080      # terminal 1
.venv/bin/python -m srt2audio                              # GUI, Base URL=http://localhost:8080
# or headless:
.venv/bin/python -m srt2audio --cli samples/sample.srt out.wav --base-url http://127.0.0.1:8080
```

## Decisive assertions (a broken impl fails these)
1. **Timeline alignment:** exported file duration == the SRT's last end time
   (e.g. `samples/sample.srt` → exactly 9.50s). Naive concatenation would differ
   (~10.2s). Check with `ffprobe -show_entries format=duration`.
2. **Silent gaps preserved:** for an SRT with a gap between cues, the gap region
   is silent (`-inf` dBFS). Measure per-window with pydub:
   `AudioSegment.from_file(f)[start:end].dBFS`.
3. **Per-cue speed-up:** a cue too long for its slot is sped up (log shows
   `tăng tốc x...`), capped at the GUI's "Tăng tốc tối đa" (default 2.0x). A cue
   that can't fit even at the cap may slightly overflow — this is by design.
4. **Ordering under concurrency:** output ordering is by absolute start time, so
   it is independent of thread completion order even at high worker counts.

## Gotchas
- `volumedetect` via ffmpeg input-seek (`-ss` before `-i`) sometimes emits no
  `mean_volume`; measuring RMS directly with pydub per slice is more reliable.
- The exec shell may return a previous command's buffered output; if results
  look stale, re-run in a fresh `shell_id`.

## Devin Secrets Needed (only for REAL CapCut voice tests)
The tool itself stores no secrets. To test real audio you need the
`kuwacom/CapCut-TTS` server reachable. Either:
- a running server Base URL (point the GUI/CLI at it), or
- `CAPCUT_DEVICE_TIME` and `CAPCUT_SIGN` (extracted from CapCut DevTools) to run
  that server locally.
Without these, restrict testing to the mock server and clearly state real voices
were not tested.
