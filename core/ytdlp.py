"""yt-dlp wrapper: video info, subtitle download, section download."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .assets import deno_path, ffmpeg_path

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_PERCENT = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%")


class YtdlpError(RuntimeError):
    pass


def _env() -> dict:
    env = os.environ.copy()
    env.pop("AIKLIPYT_API_KEY", None)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _base(url: str, cookies: str | None) -> list[str]:
    args = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--ignore-config",
        "--no-warnings",
        "--no-playlist",
        "--socket-timeout",
        "20",
        "--retries",
        "3",
    ]
    if cookies and Path(cookies).is_file():
        args += ["--cookies", cookies]
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        args += ["--ffmpeg-location", ffmpeg]
    deno = deno_path()
    if deno:
        args += ["--js-runtimes", f"deno:{deno}"]
    args.append(url)
    return args


def _error(stderr: str) -> str:
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("ERROR:"):
            return line[6:].strip()
    return lines[-1] if lines else "yt-dlp failed"


def video_info(url: str, cookies: str | None = None, timeout: int = 180) -> dict:
    args = _base(url, cookies)
    args[3:3] = ["-J", "--skip-download"]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            env=_env(),
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise YtdlpError("yt-dlp timed out while reading video info") from exc
    if proc.returncode != 0:
        raise YtdlpError(_error(proc.stderr.decode("utf-8", "replace")))
    try:
        return json.loads(proc.stdout.decode("utf-8", "replace"))
    except ValueError as exc:
        raise YtdlpError("Could not parse yt-dlp video info") from exc


def subtitle_catalog(info: dict) -> dict:
    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    original = next((code for code in automatic if code.endswith("-orig")), None)
    return {
        "manual": sorted(manual),
        "automatic": sorted(automatic),
        "original": original,
    }


def pick_subtitle(info: dict, language: str | None) -> dict | None:
    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    language = (language or "").strip()

    def auto_for(code: str) -> str | None:
        for candidate in (f"{code}-orig", code):
            if candidate in automatic:
                return candidate
        for candidate in automatic:
            if candidate.startswith(code + "-"):
                return candidate
        return None

    if language:
        original = next((code for code in automatic if code.endswith("-orig")), None)
        if original and (original[:-5] == language or original.startswith(language + "-")):
            return {"kind": "auto", "code": original}
        if language in manual:
            return {"kind": "manual", "code": language}
        auto = auto_for(language)
        if auto:
            return {"kind": "auto", "code": auto}

    original = next((code for code in automatic if code.endswith("-orig")), None)
    if original:
        return {"kind": "auto", "code": original}
    if "en" in manual:
        return {"kind": "manual", "code": "en"}
    if manual:
        return {"kind": "manual", "code": sorted(manual)[0]}
    if automatic:
        return {"kind": "auto", "code": sorted(automatic)[0]}
    return None


def download_subtitle(
    url: str,
    choice: dict,
    cookies: str | None,
    workdir: Path,
    timeout: int = 180,
) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    args = _base(url, cookies)
    args[3:3] = [
        "--skip-download",
        "--write-subs" if choice["kind"] == "manual" else "--write-auto-subs",
        "--sub-langs",
        choice["code"],
        "--sub-format",
        "json3/srt/vtt/best",
        "-o",
        "sub.%(ext)s",
    ]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            cwd=str(workdir),
            env=_env(),
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise YtdlpError("Timed out downloading subtitles") from exc
    if proc.returncode != 0:
        raise YtdlpError(_error(proc.stderr.decode("utf-8", "replace")))
    found = sorted(workdir.glob("sub.*"))
    if not found:
        raise YtdlpError(f"No subtitle file produced for {choice['code']}")
    for suffix in (".json3", ".vtt", ".srt"):
        preferred = workdir / f"sub.{choice['code']}{suffix}"
        if preferred.exists():
            return preferred
    return found[0]


def _clock(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, sec = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{sec:06.3f}"


def download_section(
    url: str,
    start: float,
    end: float,
    cookies: str | None,
    workdir: Path,
    on_line=None,
    timeout: int = 900,
) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    args = _base(url, cookies)
    args[3:3] = [
        "-f",
        "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "--download-sections",
        f"*{_clock(start)}-{_clock(end)}",
        "--force-keyframes-at-cuts",
        "--merge-output-format",
        "mp4",
        "-o",
        "section.%(ext)s",
    ]
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(workdir),
        env=_env(),
        creationflags=_CREATE_NO_WINDOW,
    )
    lines: list[str] = []
    assert process.stdout is not None
    try:
        for raw in process.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            lines.append(line)
            lines = lines[-40:]
            if on_line:
                match = _PERCENT.search(line)
                on_line(line, float(match.group(1)) if match else None)
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise YtdlpError("Timed out downloading video section")
    finally:
        if process.stdout:
            process.stdout.close()
    if process.returncode != 0:
        raise YtdlpError(_error("\n".join(lines)))
    for name in ("section.mp4", "section.mkv", "section.webm"):
        candidate = workdir / name
        if candidate.exists():
            return candidate
    candidates = [p for p in workdir.glob("section.*") if p.suffix not in (".part", ".ytdl")]
    if not candidates:
        raise YtdlpError("Downloaded section file not found")
    return candidates[0]
