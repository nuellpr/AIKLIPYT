"""Session storage under data/sessions and data/outputs."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .config import OUTPUTS, SESSIONS
from .subtitles import parse_timestamp

_ID = re.compile(r"[A-Za-z0-9_-]{3,80}")


def valid_id(session_id: str) -> bool:
    return bool(_ID.fullmatch(session_id or ""))


def session_dir(session_id: str) -> Path:
    if not valid_id(session_id):
        raise ValueError("Invalid session id")
    return SESSIONS / session_id


def output_dir(session_id: str) -> Path:
    if not valid_id(session_id):
        raise ValueError("Invalid session id")
    return OUTPUTS / session_id


def _slug(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").lower()).strip("-")[:28]
    return cleaned or fallback


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def create(
    url: str,
    info: dict,
    choice: dict,
    words: list,
    transcript_text: str,
    highlights: list,
    usage: dict,
    output_language: str = "auto",
) -> dict:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    video_id = re.sub(r"[^A-Za-z0-9_-]", "", str(info.get("id") or ""))[:16] or "video"
    base = time.strftime("%Y%m%d_%H%M%S") + "_" + _slug(info.get("title", ""), video_id)
    session_id = base
    counter = 1
    while (SESSIONS / session_id).exists():
        session_id = f"{base}_{counter}"
        counter += 1
    folder = SESSIONS / session_id
    folder.mkdir(parents=True, exist_ok=False)
    _write_atomic(
        folder / "words.json",
        json.dumps([word.as_dict() for word in words], ensure_ascii=False),
    )
    _write_atomic(folder / "transcript.txt", transcript_text)
    data = {
        "id": session_id,
        "createdAt": int(time.time()),
        "url": url,
        "videoId": video_id,
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": float(info.get("duration") or 0),
        "thumbnail": info.get("thumbnail") or "",
        "subtitle": choice,
        "outputLanguage": output_language or "auto",
        "highlights": highlights,
        "ai": {
            "model": usage.get("model", ""),
            "usage": usage.get("usage", {}) if "model" in usage else usage,
        },
    }
    _write_atomic(folder / "session.json", json.dumps(data, indent=2, ensure_ascii=False))
    output_dir(session_id).mkdir(parents=True, exist_ok=True)
    return data


def _fallback_clips_from_mp4(out_folder: Path, highlights: list) -> list[dict]:
    if not out_folder.is_dir():
        return []
    rebuilt: list[dict] = []
    for mp4 in sorted(out_folder.glob("clip_*.mp4")):
        match = re.match(r"^clip_(\d+)\.mp4$", mp4.name)
        if not match:
            continue
        try:
            if mp4.stat().st_size <= 1000:
                continue
        except OSError:
            continue
        idx = int(match.group(1)) - 1
        hl = highlights[idx] if 0 <= idx < len(highlights) and isinstance(highlights[idx], dict) else {}
        start = hl.get("start")
        end = hl.get("end")
        dur = hl.get("duration") or (
            round(float(end) - float(start), 2) if start is not None and end is not None else 0
        )
        rebuilt.append(
            {
                "index": idx,
                "file": mp4.name,
                "title": hl.get("title", ""),
                "description": hl.get("description", ""),
                "hook": hl.get("hook_text", ""),
                "start": start,
                "end": end,
                "duration": dur,
            }
        )
    return rebuilt


def load(session_id: str) -> dict:
    path = session_dir(session_id) / "session.json"
    if not path.is_file():
        raise FileNotFoundError("Session not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    out_folder = output_dir(session_id)
    clips_path = out_folder / "clips.json"
    data["clips"] = []
    if clips_path.is_file():
        try:
            data["clips"] = json.loads(clips_path.read_text(encoding="utf-8"))
        except ValueError:
            data["clips"] = []
    if not data["clips"]:
        data["clips"] = _fallback_clips_from_mp4(out_folder, data.get("highlights") or [])
    return data


def words(session_id: str) -> list[dict]:
    path = session_dir(session_id) / "words.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def list_all() -> list[dict]:
    if not SESSIONS.is_dir():
        return []
    out: list[dict] = []
    for folder in sorted(SESSIONS.iterdir(), reverse=True):
        meta = folder / "session.json"
        if not meta.is_file():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        clips_path = OUTPUTS / folder.name / "clips.json"
        clips: list = []
        if clips_path.is_file():
            try:
                clips = json.loads(clips_path.read_text(encoding="utf-8"))
            except ValueError:
                clips = []
        out.append(
            {
                "id": data.get("id", folder.name),
                "createdAt": data.get("createdAt", 0),
                "title": data.get("title", ""),
                "channel": data.get("channel", ""),
                "duration": data.get("duration", 0),
                "highlightCount": len(data.get("highlights") or []),
                "clipCount": len(clips) or len(list((OUTPUTS / folder.name).glob("clip_*.mp4"))),
                "thumbnail": data.get("thumbnail", ""),
            }
        )
    return out


def write_clips(session_id: str, clips: list[dict]) -> None:
    folder = output_dir(session_id)
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomic(folder / "clips.json", json.dumps(clips, indent=2, ensure_ascii=False))


def update_highlights(session_id: str, overrides: dict) -> dict:
    path = session_dir(session_id) / "session.json"
    if not path.is_file():
        raise FileNotFoundError("Session not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    highlights = data.get("highlights") or []
    max_dur = float(data.get("duration") or 0.0)
    changed = False
    for raw_idx, patch in (overrides or {}).items():
        if not isinstance(patch, dict):
            continue
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(highlights)) or not isinstance(highlights[idx], dict):
            continue
        clip = dict(highlights[idx])
        start = parse_timestamp(patch["start"]) if "start" in patch else parse_timestamp(clip.get("start"))
        end = parse_timestamp(patch["end"]) if "end" in patch else parse_timestamp(clip.get("end"))
        if start is not None and end is not None:
            start = max(0.0, start)
            if max_dur > 0:
                end = min(max_dur, end)
            if end - start >= 1.0:
                clip["start"] = round(start, 2)
                clip["end"] = round(end, 2)
                clip["duration"] = round(end - start, 2)
                changed = True
        if isinstance(patch.get("hook_text"), str):
            clip["hook_text"] = patch["hook_text"].strip()[:120]
            changed = True
        if isinstance(patch.get("title"), str) and patch["title"].strip():
            clip["title"] = patch["title"].strip()[:120]
            changed = True
        highlights[idx] = clip
    if changed:
        data["highlights"] = highlights
        _write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False))
    return data


def delete(session_id: str) -> None:
    folder = session_dir(session_id)
    if not folder.is_dir():
        raise FileNotFoundError("Session not found")
    out = output_dir(session_id)
    if out.is_dir():
        shutil.rmtree(out)
    shutil.rmtree(folder)
