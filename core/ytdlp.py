"""yt-dlp wrapper: video info, subtitle download, section download."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
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
        args += ["--cookies", str(Path(cookies).resolve())]
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        args += ["--ffmpeg-location", ffmpeg]
    deno = deno_path()
    if deno:
        args += ["--js-runtimes", f"deno:{deno}"]
    args += ["--", url]
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


def pick_subtitle(info: dict, language: str | None) -> dict | None:
    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    language = (language or "").strip()
    if language.lower() == "auto":
        language = ""

    def match_code(pool: dict, code: str) -> str | None:
        low = code.lower()
        for candidate in pool:
            if candidate.lower() == low:
                return candidate
        prefix = low + "-"
        for candidate in sorted(pool):
            if candidate.lower().startswith(prefix):
                return candidate
        return None

    def auto_for(code: str) -> str | None:
        low = code.lower()
        for candidate in automatic:
            if candidate.lower() == f"{low}-orig":
                return candidate
        return match_code(automatic, code)

    original = next((code for code in automatic if code.lower().endswith("-orig")), None)
    if language:
        low = language.lower()
        if original and (original[:-5].lower() == low or original.lower().startswith(low + "-")):
            return {"kind": "auto", "code": original}
        manual_hit = match_code(manual, language)
        if manual_hit:
            return {"kind": "manual", "code": manual_hit}
        auto_hit = auto_for(language)
        if auto_hit:
            return {"kind": "auto", "code": auto_hit}

    if original:
        return {"kind": "auto", "code": original}
    video_lang = str(info.get("language") or "").strip()
    if video_lang and video_lang.lower() not in ("auto", "und", "zxx"):
        manual_vid = match_code(manual, video_lang)
        if manual_vid:
            return {"kind": "manual", "code": manual_vid}
        auto_vid = auto_for(video_lang)
        if auto_vid:
            return {"kind": "auto", "code": auto_vid}
    en_manual = match_code(manual, "en")
    if en_manual:
        return {"kind": "manual", "code": en_manual}
    if manual:
        return {"kind": "manual", "code": sorted(manual)[0]}
    en_auto = auto_for("en")
    if en_auto:
        return {"kind": "auto", "code": en_auto}
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
    for stale in workdir.glob("sub.*"):
        stale.unlink()
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
    millis = int(round(max(0.0, seconds) * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    sec, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}.{ms:03d}"


def download_section(
    url: str,
    start: float,
    end: float,
    cookies: str | None,
    workdir: Path,
    on_line=None,
    timeout: int = 900,
    max_height: int = 1080,
    cancel_event: threading.Event | None = None,
    on_process=None,
) -> Path:
    if cancel_event and cancel_event.is_set():
        raise YtdlpError("Dibatalkan")
    workdir.mkdir(parents=True, exist_ok=True)
    if max_height > 1080:
        fmt = (
            f"bv*[height<={max_height}]+ba[acodec^=mp4a]/"
            f"bv*[height<={max_height}]+ba/"
            f"bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/"
            f"b[height<={max_height}]/b"
        )
    else:
        fmt = "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b"
    args = _base(url, cookies)
    args[3:3] = [
        "-f",
        fmt,
        "--download-sections",
        f"*{_clock(start)}-{_clock(end)}",
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
    timed_out = threading.Event()
    assert process.stdout is not None

    def _kill_tree() -> None:
        if os.name == "nt" and getattr(process, "pid", None):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True,
                    timeout=10,
                    creationflags=_CREATE_NO_WINDOW,
                )
                return
            except (OSError, subprocess.TimeoutExpired):
                pass
        process.kill()

    if on_process:
        on_process(_kill_tree)
    if cancel_event and cancel_event.is_set():
        _kill_tree()

    def _kill_on_timeout() -> None:
        timed_out.set()
        _kill_tree()

    watchdog = threading.Timer(timeout, _kill_on_timeout)
    watchdog.daemon = True
    watchdog.start()
    try:
        for raw in process.stdout:
            if cancel_event and cancel_event.is_set():
                _kill_tree()
                break
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            lines.append(line)
            lines = lines[-40:]
            if on_line:
                match = _PERCENT.search(line)
                on_line(line, float(match.group(1)) if match else None)
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        _kill_tree()
        raise YtdlpError("Timed out downloading video section")
    finally:
        watchdog.cancel()
        if on_process:
            on_process(None)
        if process.stdout:
            process.stdout.close()
    if cancel_event and cancel_event.is_set():
        raise YtdlpError("Dibatalkan")
    if timed_out.is_set():
        raise YtdlpError("Timed out downloading video section")
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
