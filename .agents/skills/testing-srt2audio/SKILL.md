---
name: testing-srt2audio
description: Test the srt2audio SRT-to-audio tool end-to-end (GUI + CLI) against the CapCut-TTS wrapper. Use when verifying SRT parsing, per-cue speed-up, timeline alignment, threading, real CapCut voices, or the GUI.
---

# Testing srt2audio

srt2audio is a **client** of the `kuwacom/CapCut-TTS` wrapper server. It parses an
`.srt`, calls the server's synthesize endpoint per cue (concurrently), speeds up
over-long cues with ffmpeg `atempo` to fit their slot, and overlays each cue at its
absolute start time so the result is timeline-aligned.

## Two API flows (set via the GUI "API" dropdown / `--api-version`)
- **v2 (default, account login):** `GET /v2/synthesize`, returns **MP3**, exposes a
  **real speaker catalogue** via `GET /v2/speakers`. The server is configured with
  `CAPCUT_EMAIL`/`CAPCUT_PASSWORD` in its `.env`. srt2audio sends `speaker=<id>`.
- **v1 (legacy, token):** `GET /v1/synthesize`, returns WAV, needs the server to have
  `LEGACY_DEVICE_TIME`/`LEGACY_SIGN`. srt2audio sends a numeric `type`.
Upstream `kuwacom/CapCut-TTS` made v2 the default; v1 is legacy-only. If srt2audio
were still hard-wired to v1, connecting to an account-login server would FAIL.

## Environment
- Needs `ffmpeg` on PATH and a venv with `PySide6`, `requests`, `pydub`.
  - `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- GUI is PySide6 and renders on `DISPLAY=:0`. Maximize with
  `wmctrl -r "SRT" -b add,maximized_vert,maximized_horz`.
- Note: the repo's pyenv python may lack `_tkinter`; that's fine — this app uses
  PySide6, not tkinter.

## Running the real CapCut-TTS server (for real-voice tests)
```
git clone https://github.com/kuwacom/CapCut-TTS /home/ubuntu/CapCut-TTS
cd /home/ubuntu/CapCut-TTS && npm install
# put CAPCUT_EMAIL / CAPCUT_PASSWORD in .env, then:
npm run dev            # serves on :8080; GET /v2/speakers should return 200
```
If port 8080 is busy (e.g. a leftover mock server), find/kill it with
`ss -ltnp | grep 8080`. Login may log warnings for some voice categories but still
establishes a session — `GET /v2/speakers` returning 200 with ~43 voices is the
ready signal.

## Testing without real CapCut (logic/UI proof only)
Use the bundled mock, which returns a constant tone whose length scales with text:
```
.venv/bin/python tools/mock_tts_server.py --port 8080      # terminal 1
.venv/bin/python -m srt2audio                              # GUI, Base URL=http://localhost:8080, API=v1
```
The mock implements the v1-style endpoint; select API=v1 (or use `--api-version v1`).

## GUI flow for a v2 real-voice test
1. SRT = `samples/sample.srt`; Output = `/tmp/out.mp3`; Định dạng = `mp3`.
2. API = `v2 (đăng nhập tài khoản)`; Base URL = `http://localhost:8080`.
3. Click **Kiểm tra kết nối** → expect dialog "Kết nối tới server TTS thành công."
   and log "Đã tải N giọng từ server"; the **Giọng** dropdown fills with real ids.
4. Pick a speaker (e.g. `ICL_en_male_henry1`) → **Bắt đầu**.
CLI equivalent:
`.venv/bin/python -m srt2audio --cli samples/sample.srt /tmp/out.mp3 --base-url http://127.0.0.1:8080 --api-version v2 --speaker ICL_en_male_henry1 --workers 4 --format mp3`

## Decisive assertions (a broken impl fails these)
1. **v2 path actually used:** connection test loads the live speaker list and the
   dropdown shows real `ICL_…` ids (not the static legacy voice names).
2. **Timeline alignment:** exported file duration == the SRT's last end time
   (`samples/sample.srt` → ~9.5s; allow a few ms for MP3 frame padding). Naive
   concatenation of the fitted segments would be noticeably longer (~10.5s). Check
   with `ffprobe -show_entries format=duration`.
3. **Per-cue speed-up:** a cue too long for its slot is sped up (log shows
   `tăng tốc x...`), capped at the GUI's "Tăng tốc tối đa" (default 2.0x).
4. **Ordering under concurrency:** completion order in the log differs from cue
   index order, but final assembly is ordered by absolute start time.
5. **Real speech (not mock tone):** per-100ms-window dBFS within a cue varies a lot
   (stdev ~10+ dB); a mock tone is nearly flat. Measure with pydub.

## Gotchas
- **Long cues overflow with real audio.** In `samples/sample.srt`, cue #3 is so long
  it only fits to ~2.99s even at the x2.00 cap, so it overflows its 1.0s slot into
  the following 6–7s "gap" (region is NOT silent). This is by design. The
  silent-gap assertion only holds for SRTs whose cue audio is short enough to fit —
  use a dedicated short-text/large-gap SRT to prove silence preservation.
- v2 returns MP3, v1 returns WAV; `pydub.AudioSegment.from_file` auto-detects both,
  so `audio.py` needs no format-specific handling.
- `volumedetect` via ffmpeg input-seek (`-ss` before `-i`) sometimes emits no
  `mean_volume`; measuring RMS directly with pydub per slice is more reliable.
- The exec shell may return a previous command's buffered output; if results look
  stale, re-run in a fresh `shell_id`.

## Devin Secrets Needed (only for REAL CapCut voice tests)
The tool itself stores no secrets. To test real audio you need the
`kuwacom/CapCut-TTS` server reachable. Preferred (v2): run that server with
`CAPCUT_EMAIL` and `CAPCUT_PASSWORD` (saved as user-scoped secrets) in its `.env`.
Legacy (v1) alternative: `LEGACY_DEVICE_TIME` and `LEGACY_SIGN` extracted from CapCut
DevTools. Without either, restrict testing to the mock server and clearly state that
real voices were not tested.
