"""Parsing of SubRip (.srt) subtitle files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

_TIME_RE = re.compile(
    r"(?P<h>\d+):(?P<m>\d{1,2}):(?P<s>\d{1,2})[,.](?P<ms>\d{1,3})"
)
_ARROW_RE = re.compile(r"-->")


@dataclass
class Subtitle:
    """A single subtitle cue parsed from an SRT file."""

    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


class SrtParseError(ValueError):
    """Raised when an SRT file cannot be parsed."""


def _timestamp_to_ms(value: str) -> int:
    match = _TIME_RE.search(value)
    if not match:
        raise SrtParseError(f"Invalid timestamp: {value!r}")
    h = int(match.group("h"))
    m = int(match.group("m"))
    s = int(match.group("s"))
    ms = int(match.group("ms").ljust(3, "0"))
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def parse_srt_string(content: str) -> List[Subtitle]:
    """Parse SRT text into a list of :class:`Subtitle` ordered by start time."""

    content = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    raw_blocks = re.split(r"\n\s*\n", content.strip())
    subtitles: List[Subtitle] = []

    for block in raw_blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue

        time_line_idx = None
        for i, line in enumerate(lines):
            if _ARROW_RE.search(line):
                time_line_idx = i
                break
        if time_line_idx is None:
            # No timing info in this block; skip it.
            continue

        index = len(subtitles) + 1
        if time_line_idx > 0:
            maybe_index = lines[0].strip()
            if maybe_index.isdigit():
                index = int(maybe_index)

        start_part, _, end_part = lines[time_line_idx].partition("-->")
        start_ms = _timestamp_to_ms(start_part)
        end_ms = _timestamp_to_ms(end_part)
        if end_ms < start_ms:
            end_ms = start_ms

        text = " ".join(ln.strip() for ln in lines[time_line_idx + 1 :]).strip()
        if text == "":
            continue

        subtitles.append(
            Subtitle(index=index, start_ms=start_ms, end_ms=end_ms, text=text)
        )

    subtitles.sort(key=lambda s: (s.start_ms, s.index))
    return subtitles


def parse_srt_file(path: str | Path) -> List[Subtitle]:
    """Read and parse an SRT file from ``path``."""

    file_path = Path(path)
    if not file_path.is_file():
        raise SrtParseError(f"File not found: {file_path}")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            content = file_path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - extremely unlikely
        raise SrtParseError(f"Unable to decode file: {file_path}")

    subtitles = parse_srt_string(content)
    if not subtitles:
        raise SrtParseError("No subtitle cues were found in the file.")
    return subtitles
