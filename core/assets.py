"""Locate ffmpeg and deno without bundling 300 MB into the repository."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import ROOT, load

_PARENT = ROOT.parent


def _candidates(name: str, *subdirs: str) -> list[Path]:
    paths: list[Path] = [ROOT / subdir / name for subdir in subdirs]
    paths.append(ROOT / name)
    paths.extend(_PARENT / subdir / name for subdir in subdirs)
    paths.append(_PARENT / name)
    return paths


def ffmpeg_path() -> str:
    configured = load().get("paths", {}).get("ffmpeg", "")
    if configured and Path(configured).is_file():
        return configured
    env = os.environ.get("AIKLIPYT_FFMPEG")
    if env and Path(env).is_file():
        return env
    for candidate in _candidates("ffmpeg.exe" if os.name == "nt" else "ffmpeg", "assets/ffmpeg", "ffmpeg"):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg")
    return found or ""


def deno_path() -> str:
    configured = load().get("paths", {}).get("deno", "")
    if configured and Path(configured).is_file():
        return configured
    env = os.environ.get("AIKLIPYT_DENO")
    if env and Path(env).is_file():
        return env
    for candidate in _candidates("deno.exe" if os.name == "nt" else "deno", "bin"):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("deno") or ""
