"""HTTP client for the CapCut TTS wrapper API (kuwacom/CapCut-TTS)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

# Voice catalogue exposed by the wrapper API. ``type`` is the query parameter
# value; the label is a human friendly description for the GUI.
VOICES: List[Dict[str, object]] = [
    {"type": 0, "label": "Nam 1 (BV525)"},
    {"type": 1, "label": "Bé trai (BV528)"},
    {"type": 2, "label": "Giọng dễ thương (BV017)"},
    {"type": 3, "label": "Chị gái (BV016)"},
    {"type": 4, "label": "Thiếu nữ (BV023)"},
    {"type": 5, "label": "Nữ (BV024)"},
    {"type": 6, "label": "Nam 2 (BV018)"},
    {"type": 7, "label": "Cậu ấm (BV523)"},
    {"type": 8, "label": "Nữ (BV521)"},
    {"type": 9, "label": "Nữ MC (BV522)"},
    {"type": 10, "label": "Nam MC (BV524)"},
    {"type": 11, "label": "Loli năng động (BV520)"},
    {"type": 12, "label": "Honey tươi sáng (VOV401)"},
    {"type": 13, "label": "Quý cô dịu dàng (VOV402)"},
    {"type": 14, "label": "Mezzo soprano (VOV402)"},
    {"type": 15, "label": "Sakura (jp_005)"},
]

DEFAULT_BASE_URL = "http://localhost:8080"


class TTSError(RuntimeError):
    """Raised when the TTS server fails to synthesize audio."""


@dataclass
class TTSParams:
    """Synthesis parameters shared across every segment of a job."""

    voice_type: int = 0
    pitch: int = 10
    speed: int = 10
    volume: int = 10
    method: str = "buffer"


@dataclass
class CapCutTTSClient:
    """Thin client around ``GET /v1/synthesize``.

    A :class:`requests.Session` is used so connection pooling works well when
    many segments are synthesized concurrently from a thread pool.
    """

    base_url: str = DEFAULT_BASE_URL
    timeout: float = 60.0
    max_retries: int = 3
    retry_backoff: float = 1.5
    session: requests.Session = field(default_factory=requests.Session)

    @property
    def synthesize_url(self) -> str:
        return self.base_url.rstrip("/") + "/v1/synthesize"

    def synthesize(self, text: str, params: Optional[TTSParams] = None) -> bytes:
        """Return WAV bytes for ``text``. Retries transient failures."""

        if not text or not text.strip():
            raise TTSError("Cannot synthesize empty text.")
        params = params or TTSParams()
        query = {
            "text": text,
            "type": params.voice_type,
            "pitch": params.pitch,
            "speed": params.speed,
            "volume": params.volume,
            "method": params.method,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    self.synthesize_url, params=query, timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code == 200:
                    if not response.content:
                        last_error = TTSError("Server returned empty audio body.")
                    else:
                        return response.content
                else:
                    snippet = response.text[:200].strip()
                    last_error = TTSError(
                        f"HTTP {response.status_code} from TTS server: {snippet}"
                    )
                    # 4xx other than 429 will not improve on retry.
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        break

            if attempt < self.max_retries:
                time.sleep(self.retry_backoff * attempt)

        raise TTSError(str(last_error) if last_error else "Unknown TTS failure.")

    def check_connection(self, params: Optional[TTSParams] = None) -> None:
        """Synthesize a tiny sample to verify the server is reachable."""

        self.synthesize("test", params or TTSParams())
