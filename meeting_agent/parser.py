"""TranscriptParser: pre-process raw meeting transcripts before sending to the agent."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A single timestamped speech segment from one speaker."""

    speaker: str
    timestamp: str  # raw string from transcript, e.g. "00:03:15" or "3:15"
    text: str

    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.speaker}: {self.text}"


# ---------------------------------------------------------------------------
# Filler word list
# ---------------------------------------------------------------------------

DEFAULT_FILLER_WORDS: tuple[str, ...] = (
    r"\buh+\b",
    r"\bum+\b",
    r"\blike\b(?=,|\s+(?:I|we|it|so|you|that|this|just|really|kind|sort))",
    r"\byou\s+know\b",
    r"\bkind\s+of\b",
    r"\bsort\s+of\b",
    r"\bbasically\b",
    r"\bliterally\b",
    r"\bright\?\s*",
    r"\bokay\s+so\b",
    r"\bI\s+mean\b",
)


# ---------------------------------------------------------------------------
# Timestamp pattern helpers
# ---------------------------------------------------------------------------

# Matches lines like:
#   [00:12:34] Alice: ...
#   (0:05) Bob: ...
#   Alice [00:01]: ...
#   00:12 - Alice: ...
TIMESTAMP_SPEAKER_PATTERN = re.compile(
    r"^(?:"
    r"(?P<ts1>\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—]?\s*(?P<sp1>[A-Z][\w .]+?)\s*:"
    r"|"
    r"[\[\(](?P<ts2>\d{1,2}:\d{2}(?::\d{2})?)[])]\s*(?P<sp2>[A-Z][\w .]+?)\s*:"
    r"|"
    r"(?P<sp3>[A-Z][\w .]+?)\s*[\[\(](?P<ts3>\d{1,2}:\d{2}(?::\d{2})?)[])]\s*:"
    r"|"
    r"(?P<sp4>[A-Z][\w .]+?)\s*:"
    r")\s*(?P<text>.+)$",
    re.MULTILINE,
)

# Standalone timestamp on its own line, e.g. "[00:05:30]"
STANDALONE_TS_PATTERN = re.compile(
    r"^[\[\(]?(\d{1,2}:\d{2}(?::\d{2})?)[])]?\s*$"
)


# ---------------------------------------------------------------------------
# TranscriptParser
# ---------------------------------------------------------------------------


class TranscriptParser:
    """Parse and clean raw meeting transcripts.

    Capabilities
    ------------
    * Identify speakers and extract their individual speech segments.
    * Associate timestamps with each segment where available.
    * Remove common filler words / disfluencies.
    * Produce a cleaned, normalised transcript string.

    Parameters
    ----------
    filler_patterns:
        Iterable of regex patterns for filler words to strip.  Defaults to
        :data:`DEFAULT_FILLER_WORDS`.
    """

    def __init__(
        self,
        filler_patterns: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        patterns = filler_patterns if filler_patterns is not None else DEFAULT_FILLER_WORDS
        self._filler_re = re.compile(
            "|".join(patterns),
            re.IGNORECASE,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse(self, raw: str) -> list[Segment]:
        """Parse *raw* transcript text into a list of :class:`Segment` objects.

        Handles several common transcript formats:
        * ``[HH:MM:SS] Speaker: text``
        * ``Speaker [MM:SS]: text``
        * ``MM:SS - Speaker: text``
        * Simple ``Speaker: text`` (no timestamp)

        Parameters
        ----------
        raw:
            The full transcript as a plain string.

        Returns
        -------
        list[Segment]
            Ordered list of cleaned segments.
        """
        segments: list[Segment] = []
        current_ts = "N/A"

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Check for standalone timestamp line
            ts_match = STANDALONE_TS_PATTERN.match(line)
            if ts_match:
                current_ts = ts_match.group(1)
                continue

            m = TIMESTAMP_SPEAKER_PATTERN.match(line)
            if not m:
                # Continuation line: append to previous segment
                if segments:
                    segments[-1].text += " " + self._clean(line)
                continue

            # Extract timestamp and speaker from whichever group matched
            ts = (
                m.group("ts1")
                or m.group("ts2")
                or m.group("ts3")
                or current_ts
            )
            speaker = (
                m.group("sp1")
                or m.group("sp2")
                or m.group("sp3")
                or m.group("sp4")
                or "Unknown"
            ).strip()
            text = self._clean(m.group("text") or "")

            if ts:
                current_ts = ts

            segments.append(Segment(speaker=speaker, timestamp=current_ts, text=text))

        return segments

    def speakers(self, segments: list[Segment]) -> list[str]:
        """Return a deduplicated list of speaker names preserving first occurrence."""
        seen: set[str] = set()
        result: list[str] = []
        for seg in segments:
            if seg.speaker not in seen:
                seen.add(seg.speaker)
                result.append(seg.speaker)
        return result

    def clean(self, raw: str) -> str:
        """Return a cleaned, normalised version of the transcript.

        * Parses segments.
        * Removes filler words.
        * Re-emits as ``[timestamp] Speaker: text`` lines.
        """
        segments = self.parse(raw)
        return "\n".join(str(s) for s in segments)

    def by_speaker(self, segments: list[Segment]) -> dict[str, list[Segment]]:
        """Group segments by speaker name.

        Returns
        -------
        dict
            Mapping from speaker name to their ordered list of segments.
        """
        result: dict[str, list[Segment]] = {}
        for seg in segments:
            result.setdefault(seg.speaker, []).append(seg)
        return result

    def segment_by_time(
        self,
        segments: list[Segment],
        window_minutes: int = 10,
    ) -> list[list[Segment]]:
        """Group segments into time windows of *window_minutes* each.

        Segments without a parseable timestamp are placed in the first window.

        Parameters
        ----------
        segments:
            Ordered list of segments from :meth:`parse`.
        window_minutes:
            Duration of each time window in minutes.

        Returns
        -------
        list[list[Segment]]
            List of windows, each being a list of segments.
        """
        if not segments:
            return []

        def _to_seconds(ts: str) -> int:
            """Convert HH:MM:SS or MM:SS to total seconds."""
            parts = ts.split(":")
            try:
                parts_int = [int(p) for p in parts]
            except ValueError:
                return 0
            if len(parts_int) == 3:
                return parts_int[0] * 3600 + parts_int[1] * 60 + parts_int[2]
            if len(parts_int) == 2:
                return parts_int[0] * 60 + parts_int[1]
            return 0

        window_seconds = window_minutes * 60
        windows: list[list[Segment]] = [[]]
        window_start = 0

        for seg in segments:
            seg_seconds = _to_seconds(seg.timestamp)
            # Advance window if needed
            while seg_seconds >= window_start + window_seconds:
                window_start += window_seconds
                windows.append([])
            windows[-1].append(seg)

        return [w for w in windows if w]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clean(self, text: str) -> str:
        """Strip filler words and normalise whitespace in *text*."""
        cleaned = self._filler_re.sub("", text)
        # Collapse multiple spaces and strip
        cleaned = re.sub(r" {2,}", " ", cleaned).strip()
        # Fix spacing around punctuation introduced by removal
        cleaned = re.sub(r" ([,\.!?;:])", r"\1", cleaned)
        return cleaned
