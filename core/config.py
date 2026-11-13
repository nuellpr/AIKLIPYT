"""Configuration and portable data paths.

Everything lives next to the app (portable), with AIKLIPYT_DATA as an override.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AIKLIPYT_DATA") or (ROOT / "data"))
SESSIONS = DATA / "sessions"
OUTPUTS = DATA / "outputs"
CONFIG_PATH = DATA / "config.json"

DEFAULTS: dict[str, Any] = {
    "ai": {
        "baseUrl": "https://api.openai.com/v1",
        "model": "",
        "apiKeyEnc": "",
    },
    "outputLanguage": "auto",
    "clip": {"minSeconds": 20, "maxSeconds": 120, "padding": 0.25},
    "render": {
        "portrait": True,
        "background": "black",
        "captions": True,
        "hook": True,
        "hookSeconds": 3.0,
        "captionColor": "#FFD700",
        "captionStyle": "highlight",
        "watermark": "",
        "credit": "",
    },
    "paths": {"ffmpeg": "", "deno": ""},
}

_lock = threading.RLock()
_cache: dict[str, Any] | None = None


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return copy.deepcopy(_cache)
        DATA.mkdir(parents=True, exist_ok=True)
        raw: dict = {}
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
        _cache = _merge(DEFAULTS, raw)
        return copy.deepcopy(_cache)


def save(config: dict) -> dict:
    global _cache
    with _lock:
        merged = _merge(DEFAULTS, config)
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
        _cache = merged
        return copy.deepcopy(merged)


def update(section: str, values: dict) -> dict:
    with _lock:
        current = load()
        current[section] = _merge(current.get(section, {}), values)
        return save(current)


def ensure_dirs() -> None:
    for path in (DATA, SESSIONS, OUTPUTS):
        path.mkdir(parents=True, exist_ok=True)
