"""Subtitle parsing and timestamp helpers.

The useful part of YouTube captions is per-word timing: only the original
auto-caption track (``*-orig``) carries it. Manual subtitles are cue-level, so
word times there are approximated by character length.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

_TS = re.compile(
    r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$"
)
_INLINE_TS = re.compile(r"<((?:\d{1,2}:)?\d{1,2}:\d{2}\.\d{3})>")


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Word:
    word: str
    start: float
    end: float

    def as_dict(self) -> dict:
        return {"word": self.word, "start": round(self.start, 3), "end": round(self.end, 3)}


def parse_timestamp(value) -> float | None:
    """Accept 62.5, "1:02", "01:02:03,500" or "0:12.250"."""
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    match = _TS.match(text)
    if not match:
        try:
            return max(0.0, float(text))
        except ValueError:
            return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int((match.group(4) or "0").ljust(3, "0")[:3])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def parse_srt(text: str) -> list[Cue]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        index = 0
        if "-->" not in lines[0] and len(lines) > 1:
            index = 1
        if index >= len(lines) or "-->" not in lines[index]:
            continue
        left, right = lines[index].split("-->", 1)
        start = parse_timestamp(left.strip())
        end = parse_timestamp(right.strip().split()[0] if right.strip() else "")
        if start is None or end is None or end <= start:
            continue
        body = html.unescape(" ".join(lines[index + 1:])).strip()
        body = re.sub(r"<[^>]+>", "", body)
        if body:
            cues.append(Cue(start, end, body))
    return cues


def parse_vtt(text: str) -> tuple[list[Cue], list[Word]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cues: list[Cue] = []
    words: list[Word] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        index = 0
        if "-->" not in lines[0] and len(lines) > 1:
            index = 1
        if index >= len(lines) or "-->" not in lines[index]:
            continue
        left, right = lines[index].split("-->", 1)
        start = parse_timestamp(left.strip())
        end = parse_timestamp(right.strip().split()[0] if right.strip() else "")
        if start is None or end is None or end <= start:
            continue
        body = "\n".join(lines[index + 1:]).strip()
        plain = html.unescape(re.sub(r"<[^>]+>", "", body)).strip()
        plain = plain.replace("\u00a0", " ")
        if not plain:
            continue
        cues.append(Cue(start, end, " ".join(plain.split())))
        stamps = list(_INLINE_TS.finditer(body))
        if len(stamps) >= 2:
            for position, match in enumerate(stamps):
                word_start = parse_timestamp(match.group(1))
                word_end = (
                    parse_timestamp(stamps[position + 1].group(1))
                    if position + 1 < len(stamps)
                    else end
                )
                chunk = body[match.end(): stamps[position + 1].start() if position + 1 < len(stamps) else len(body)]
                chunk = html.unescape(re.sub(r"<[^>]+>", "", chunk)).strip()
                tokens = chunk.split()
                if word_start is None or word_end is None or word_end <= word_start or not tokens:
                    continue
                weights = [len(token) + 2 for token in tokens]
                total = sum(weights) or 1
                cursor = word_start
                for token, weight in zip(tokens, weights):
                    span = (word_end - word_start) * weight / total
                    words.append(Word(token, cursor, min(word_end, cursor + max(0.06, span))))
                    cursor += span
    return cues, normalize_words(words)


def parse_json3(data: dict) -> list[Word]:
    words: list[Word] = []
    for event in data.get("events", []) or []:
        segs = event.get("segs") or []
        if not segs:
            continue
        base = float(event.get("tStartMs", 0))
        event_end = base + float(event.get("dDurationMs", 0) or 0)
        starts = [base + float(seg.get("tOffsetMs", 0) or 0) for seg in segs]
        for position, seg in enumerate(segs):
            text = (seg.get("utf8") or "").replace("\n", " ").strip()
            if not text:
                continue
            start = starts[position] / 1000.0
            end = (starts[position + 1] if position + 1 < len(starts) else event_end) / 1000.0
            if end <= start:
                end = start + 0.12
            tokens = text.split()
            if len(tokens) <= 1:
                words.append(Word(text, start, end))
                continue
            # Manual json3 tracks store whole sentences per segment; split them
            # and approximate timing so caption rendering still works.
            weights = [len(token) + 2 for token in tokens]
            total = sum(weights) or 1
            cursor = start
            for token, weight in zip(tokens, weights):
                span = (end - start) * weight / total
                words.append(Word(token, cursor, min(end, cursor + max(0.06, span))))
                cursor += span
    return normalize_words(words)


def normalize_words(words: list[Word]) -> list[Word]:
    """Drop empty words, sort, and collapse rolling-caption duplicates."""
    cleaned = [w for w in words if w.word.strip() and w.end > w.start - 0.02]
    cleaned.sort(key=lambda w: (w.start, w.end))
    out: list[Word] = []
    for word in cleaned:
        if out:
            prev = out[-1]
            if (
                word.word == prev.word
                and abs(word.start - prev.start) < 0.08
                and abs(word.end - prev.end) < 0.08
            ):
                continue
            if word.start < prev.start - 0.25:
                continue
        out.append(word)
    return out


def words_from_cues(cues: list[Cue]) -> list[Word]:
    """Approximate word timing so captions still work for manual subtitles."""
    words: list[Word] = []
    for cue in cues:
        tokens = cue.text.split()
        if not tokens:
            continue
        weights = [len(token) + 2 for token in tokens]
        total = sum(weights) or 1
        span = max(0.2, cue.end - cue.start)
        cursor = cue.start
        for token, weight in zip(tokens, weights):
            duration = max(0.08, span * weight / total)
            words.append(Word(token, cursor, min(cue.end, cursor + duration)))
            cursor += duration
    return normalize_words(words)


def slice_words(words: list[Word], start: float, end: float) -> list[Word]:
    out: list[Word] = []
    for word in words:
        if word.end <= start or word.start >= end:
            continue
        out.append(Word(word.word, max(0.0, word.start - start), min(end, word.end) - start))
    return out


def transcript(cues: list[Cue], words: list[Word], max_chars: int = 90000) -> str:
    if cues:
        lines = [f"[{format_timestamp(c.start)}] {c.text}" for c in cues]
        text = "\n".join(lines)
    else:
        chunks: list[list[Word]] = []
        current: list[Word] = []
        for word in words:
            if current and (word.start - current[-1].end > 1.0 or len(" ".join(w.word for w in current)) > 220):
                chunks.append(current)
                current = []
            current.append(word)
        if current:
            chunks.append(current)
        text = "\n".join(
            f"[{format_timestamp(chunk[0].start)}] " + " ".join(w.word for w in chunk)
            for chunk in chunks
        )
    if len(text) > max_chars:
        head = text[: max_chars // 2]
        tail = text[-max_chars // 4:]
        text = head + "\n...[transcript truncated]...\n" + tail
    return text


def parse_subtitle(path) -> tuple[list[Cue], list[Word]]:
    from pathlib import Path

    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".json3":
        import json

        return [], parse_json3(json.loads(raw))
    if suffix == ".vtt":
        return parse_vtt(raw)
    if suffix in (".srt",):
        cues = parse_srt(raw)
        return cues, words_from_cues(cues)
    # Unknown extension: try JSON first, then SRT.
    try:
        import json

        return [], parse_json3(json.loads(raw))
    except ValueError:
        cues = parse_srt(raw)
        return cues, words_from_cues(cues)
