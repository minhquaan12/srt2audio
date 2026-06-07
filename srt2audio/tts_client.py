"""HTTP client for the CapCut TTS wrapper API (kuwacom/CapCut-TTS)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

# Endpoint versions exposed by the kuwacom/CapCut-TTS wrapper.
#   v2 -> account-login flow (``/v2/synthesize``, MP3, real speaker ids). This
#         is the current default the upstream server supports out of the box.
#   v1 -> legacy token flow (``/v1/synthesize``, WAV) which only works when the
#         server is configured with LEGACY_DEVICE_TIME / LEGACY_SIGN.
API_V2 = "v2"
API_V1 = "v1"

# Legacy ``type`` voice catalogue (used by the v1 flow and as a fallback when
# the live speaker list cannot be fetched). ``type`` is the query parameter
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
    speaker: Optional[str] = None
    pitch: int = 10
    speed: int = 10
    volume: int = 10
    method: str = "buffer"


@dataclass
class CapCutTTSClient:
    """Thin client around the CapCut-TTS wrapper ``/synthesize`` endpoint.

    ``api_version`` selects the upstream flow (``v2`` account-login by default,
    ``v1`` legacy token flow). A :class:`requests.Session` is used so connection
    pooling works well when many segments are synthesized concurrently from a
    thread pool.
    """

    base_url: str = DEFAULT_BASE_URL
    api_version: str = API_V2
    timeout: float = 60.0
    max_retries: int = 3
    retry_backoff: float = 1.5
    session: requests.Session = field(default_factory=requests.Session)

    @property
    def synthesize_url(self) -> str:
        version = self.api_version if self.api_version in (API_V1, API_V2) else API_V2
        return self.base_url.rstrip("/") + f"/{version}/synthesize"

    @property
    def speakers_url(self) -> str:
        return self.base_url.rstrip("/") + "/v2/speakers"

    def synthesize(self, text: str, params: Optional[TTSParams] = None) -> bytes:
        """Return audio bytes for ``text`` (WAV on v1, MP3 on v2).

        Retries transient failures.
        """

        if not text or not text.strip():
            raise TTSError("Cannot synthesize empty text.")
        params = params or TTSParams()
        query: Dict[str, object] = {
            "text": text,
            "pitch": params.pitch,
            "speed": params.speed,
            "volume": params.volume,
            "method": params.method,
        }
        # On v2 a real speaker id is preferred when provided; otherwise fall
        # back to the legacy numeric ``type``. v1 only understands ``type``.
        if self.api_version == API_V2 and params.speaker:
            query["speaker"] = params.speaker
        else:
            query["type"] = params.voice_type

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

    def list_speakers(self) -> List[Dict[str, str]]:
        """Fetch the live speaker catalogue from ``GET /v2/speakers``.

        Returns a list of ``{"id": ..., "name": ...}`` dictionaries. Raises
        :class:`TTSError` if the server is unreachable or returns an error.
        """

        try:
            response = self.session.get(self.speakers_url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TTSError(str(exc)) from exc
        if response.status_code != 200:
            snippet = response.text[:200].strip()
            raise TTSError(f"HTTP {response.status_code} from /v2/speakers: {snippet}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TTSError("Server did not return a valid speaker list.") from exc

        items = payload if isinstance(payload, list) else payload.get("speakers", [])
        speakers: List[Dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            speaker_id = item.get("id") or item.get("speaker") or item.get("effectId")
            if not speaker_id:
                continue
            name = item.get("name") or speaker_id
            speakers.append({"id": str(speaker_id), "name": str(name)})
        return speakers

    def check_connection(self, params: Optional[TTSParams] = None) -> None:
        """Verify the server is reachable for the selected API version.

        On v2 this lists speakers (fast, also confirms the CapCut session is
        alive). On v1 it synthesizes a tiny sample.
        """

        if self.api_version == API_V2:
            self.list_speakers()
        else:
            self.synthesize("test", params or TTSParams())
