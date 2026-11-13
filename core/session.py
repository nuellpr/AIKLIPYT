"""Session storage under data/sessions and data/outputs."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .config import OUTPUTS, SESSIONS

_ID = re.compile(r"^[A-Za-z0-9_-]{3,80}$")


def valid_id(session_id: str) -> bool:
    return bool(_ID.match(session_id or ""))


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


def create(url: str, info: dict, choice: dict, words: list, cues: list, transcript_text: str, highlights: list, usage: dict) -> dict:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    video_id = re.sub(r"[^A-Za-z0-9_-]", "", str(info.get("id") or ""))[:16] or "video"
    session_id = time.strftime("%Y%m%d_%H%M%S") + "_" + _slug(info.get("title", ""), video_id)
    folder = SESSIONS / session_id
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "words.json").write_text(
        json.dumps([word.as_dict() for word in words], ensure_ascii=False),
        encoding="utf-8",
    )
    (folder / "transcript.txt").write_text(transcript_text, encoding="utf-8")
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
        "highlights": highlights,
        "ai": {"model": usage.get("model", ""), "usage": usage},
    }
    (folder / "session.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    output_dir(session_id).mkdir(parents=True, exist_ok=True)
    return data


def load(session_id: str) -> dict:
    path = session_dir(session_id) / "session.json"
    if not path.is_file():
        raise FileNotFoundError("Session not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    clips_path = output_dir(session_id) / "clips.json"
    data["clips"] = []
    if clips_path.is_file():
        try:
            data["clips"] = json.loads(clips_path.read_text(encoding="utf-8"))
        except ValueError:
            data["clips"] = []
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
    (folder / "clips.json").write_text(json.dumps(clips, indent=2, ensure_ascii=False), encoding="utf-8")


def delete(session_id: str) -> None:
    folder = session_dir(session_id)
    if not folder.is_dir():
        raise FileNotFoundError("Session not found")
    shutil.rmtree(folder)
    out = output_dir(session_id)
    if out.is_dir():
        shutil.rmtree(out)
