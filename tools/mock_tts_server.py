"""A tiny mock of the CapCut TTS wrapper API for local testing.

It serves ``GET /v1/synthesize`` and returns a WAV tone whose length is
proportional to the text length, so the time-fitting / speed-up logic can be
exercised without a real CapCut server. Do NOT use this for real audio.

Run:
    python tools/mock_tts_server.py --port 8080
"""

from __future__ import annotations

import argparse
import io
import math
import struct
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FRAME_RATE = 24000
MS_PER_CHAR = 70  # synthetic speaking rate


def make_wav(text: str, voice_type: int) -> bytes:
    duration_ms = max(300, len(text) * MS_PER_CHAR)
    n_samples = int(FRAME_RATE * duration_ms / 1000)
    freq = 220.0 + (voice_type % 8) * 40.0
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(FRAME_RATE)
        frames = bytearray()
        for i in range(n_samples):
            # Gentle amplitude envelope so it sounds like a pulse, not a flat tone.
            env = 0.3 * (1.0 + math.sin(2 * math.pi * 3 * i / FRAME_RATE))
            sample = int(12000 * env * math.sin(2 * math.pi * freq * i / FRAME_RATE))
            frames += struct.pack("<h", max(-32768, min(32767, sample)))
        wav.writeframes(bytes(frames))
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence default logging
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/v1/synthesize":
            self.send_error(404, "Not found")
            return
        qs = parse_qs(parsed.query)
        text = (qs.get("text") or [""])[0]
        voice_type = int((qs.get("type") or ["0"])[0])
        if not text.strip():
            self.send_error(400, "Missing text")
            return
        audio = make_wav(text, voice_type)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mock TTS server on http://{args.host}:{args.port}/v1/synthesize", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
