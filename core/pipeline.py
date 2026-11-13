"""Background jobs: find highlights, then render selected clips."""
from __future__ import annotations

import copy
import json
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import cookies as cookie_store
from . import session as session_store
from .assets import ffmpeg_path
from .config import DATA, load
from .highlights import AIError, build_messages, chat, extract_clips, select_clips
from .render import render_clip
from .subtitles import Word, parse_subtitle, slice_words, transcript
from .ytdlp import YtdlpError, download_section, download_subtitle, pick_subtitle, video_info

JOBS: dict[str, dict] = {}
_lock = threading.RLock()
TMP = DATA / "tmp"


class JobError(RuntimeError):
    pass


def _now() -> str:
    return time.strftime("%H:%M:%S")


def _new_job(kind: str) -> dict:
    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id,
        "kind": kind,
        "status": "running",
        "progress": 0.0,
        "message": "Starting",
        "log": [],
        "result": None,
        "error": "",
        "createdAt": int(time.time()),
    }
    with _lock:
        JOBS[job_id] = job
    return job


def _update(job: dict, **fields) -> None:
    with _lock:
        job.update(fields)


def _log(job: dict, message: str) -> None:
    with _lock:
        job["log"] = (job["log"] + [f"{_now()}  {message}"])[-300:]


def get(job_id: str) -> dict:
    with _lock:
        job = JOBS.get(job_id)
        if not job:
            raise KeyError("Job not found")
        return copy.deepcopy(job)


def _cookies_path() -> Path:
    return DATA / "cookies.txt"


def _fail(job: dict, message: str) -> None:
    _log(job, message)
    _update(job, status="error", error=message, message="Failed")


def _highlight_worker(job: dict, params: dict) -> None:
    config = load()
    workdir = TMP / job["id"]
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        _update(job, message="Reading video info", progress=4)
        info = video_info(params["url"], str(_cookies_path()) if _cookies_path().is_file() else None)
        duration = float(info.get("duration") or 0)
        _log(job, f"Video: {info.get('title', '')} ({int(duration)}s)")

        choice = pick_subtitle(info, params.get("subtitleLanguage") or None)
        if not choice:
            raise JobError(
                "Video ini tidak punya subtitle. AI butuh transkrip; coba video lain atau upload subtitle manual (belum didukung)."
            )
        _log(job, f"Using {choice['kind']} subtitle: {choice['code']}")
        _update(job, message="Downloading subtitles", progress=12)
        subtitle_path = download_subtitle(
            params["url"],
            choice,
            str(_cookies_path()) if _cookies_path().is_file() else None,
            workdir,
        )
        _update(job, message="Parsing transcript", progress=22)
        cues, words = parse_subtitle(subtitle_path)
        if not words:
            raise JobError("Subtitle ditemukan tapi tidak berisi teks yang bisa dibaca.")
        text = transcript(cues, words)
        _log(job, f"Transcript: {len(words)} words, {len(text)} chars")

        _update(job, message="AI is finding highlights (this can take a minute)", progress=30)
        messages = build_messages(
            info,
            text,
            int(params["numClips"]),
            params.get("direction", ""),
            params.get("outputLanguage") or config.get("outputLanguage", "auto"),
            float(config["clip"]["minSeconds"]),
            float(config["clip"]["maxSeconds"]),
        )
        from .secret import api_key

        content, usage = chat(
            config["ai"]["baseUrl"],
            api_key(config),
            config["ai"]["model"],
            messages,
        )
        _log(job, f"AI responded ({len(content)} chars)")
        items = extract_clips(content)
        highlights = select_clips(
            items,
            int(params["numClips"]),
            duration,
            float(config["clip"]["minSeconds"]),
            float(config["clip"]["maxSeconds"]),
        )
        if not highlights:
            raise JobError(
                "AI tidak menghasilkan klip yang valid. Coba naikkan durasi maksimum atau ganti model."
            )
        result = session_store.create(
            params["url"], info, choice, words, cues, text, highlights, {"model": config["ai"]["model"], "usage": usage}
        )
        _update(
            job,
            status="done",
            progress=100,
            message="Highlights ready",
            result={
                "sessionId": result["id"],
                "title": result["title"],
                "channel": result["channel"],
                "highlights": highlights,
                "clipCount": len(highlights),
            },
        )
        _log(job, f"Saved session {result['id']} with {len(highlights)} highlights")
    except (JobError, AIError, YtdlpError, ValueError) as exc:
        _fail(job, str(exc))
    except Exception as exc:  # noqa: BLE001
        _log(job, traceback.format_exc(limit=3))
        _fail(job, f"Unexpected error: {exc}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def start_highlights(params: dict) -> str:
    job = _new_job("highlights")
    thread = threading.Thread(target=_highlight_worker, args=(job, params), daemon=True)
    thread.start()
    return job["id"]


def _render_worker(job: dict, params: dict) -> None:
    config = load()
    render_opts = dict(config["render"])
    render_opts.update(params.get("render") or {})
    workdir = TMP / job["id"]
    errors: list[str] = []
    try:
        session = session_store.load(params["sessionId"])
        stored_words = [Word(item["word"], float(item["start"]), float(item["end"])) for item in session_store.words(params["sessionId"])]
        highlights = session.get("highlights") or []
        indices = params.get("indices") or list(range(len(highlights)))
        indices = [int(index) for index in indices if 0 <= int(index) < len(highlights)]
        if not indices:
            raise JobError("Pilih minimal satu highlight.")
        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            raise JobError("ffmpeg tidak ditemukan. Letakkan ffmpeg.exe di AIKLIPYT\\assets\\ffmpeg atau install di PATH.")
        cookies_file = _cookies_path()
        cookies = str(cookies_file) if cookies_file.is_file() else None
        output_folder = session_store.output_dir(params["sessionId"])
        output_folder.mkdir(parents=True, exist_ok=True)
        existing: list[dict] = []
        clips_path = output_folder / "clips.json"
        if clips_path.is_file():
            try:
                existing = json.loads(clips_path.read_text(encoding="utf-8"))
            except ValueError:
                existing = []
        by_index = {int(item.get("index", -1)): item for item in existing}

        padding = float(config["clip"].get("padding") or 0)
        total = len(indices)
        overwrite = bool(params.get("overwrite"))
        for position, index in enumerate(indices):
            clip = highlights[index]
            start = max(0.0, float(clip["start"]) - padding)
            end = float(clip["end"]) + padding
            if session.get("duration"):
                end = min(float(session["duration"]), end)
            out = output_folder / f"clip_{index + 1:02d}.mp4"
            if out.exists() and out.stat().st_size > 1000 and not overwrite:
                _log(job, f"Clip {index + 1} already exists, skipping")
                by_index[index] = dict(by_index.get(index) or {}, index=index, file=out.name, title=clip.get("title", ""))
                _update(job, progress=(position + 1) / total * 100)
                continue
            job_dir = workdir / f"clip_{index + 1}"
            try:
                _update(job, message=f"Downloading clip {index + 1}/{total}", progress=(position / total) * 100)
                _log(job, f"Clip {index + 1}: {clip.get('start')}s - {clip.get('end')}s")
                section = download_section(
                    session["url"],
                    start,
                    end,
                    cookies,
                    job_dir,
                    on_line=lambda line, percent: (
                        _update(job, message=f"Downloading clip {index + 1}/{total} ({percent:.0f}%)")
                        if percent is not None
                        else None
                    ),
                )
                _update(
                    job,
                    message=f"Rendering clip {index + 1}/{total}",
                    progress=(position / total) * 100 + 5 / total,
                )
                clip_words = slice_words(stored_words, start, end)
                duration = end - start

                def progress(percent: float, position=position) -> None:
                    _update(job, progress=((position + percent / 100) / total) * 100)

                render_clip(
                    section,
                    out,
                    clip_words,
                    ffmpeg,
                    duration,
                    hook_text=clip.get("hook_text", "") if render_opts.get("hook", True) else "",
                    credit=render_opts.get("credit", ""),
                    hook_seconds=float(render_opts.get("hookSeconds", 3)),
                    portrait=bool(render_opts.get("portrait", True)),
                    background=render_opts.get("background", "black"),
                    captions=bool(render_opts.get("captions", True)),
                    hook=bool(render_opts.get("hook", True)),
                    watermark=render_opts.get("watermark", ""),
                    caption_color=render_opts.get("captionColor", "#FFD700"),
                    caption_style=render_opts.get("captionStyle", "highlight"),
                    on_progress=progress,
                    on_log=lambda message: _log(job, message),
                )
                by_index[index] = {
                    "index": index,
                    "file": out.name,
                    "title": clip.get("title", ""),
                    "description": clip.get("description", ""),
                    "hook": clip.get("hook_text", ""),
                    "start": clip.get("start"),
                    "end": clip.get("end"),
                    "duration": round(duration, 2),
                }
                _log(job, f"Clip {index + 1} done: {out.name}")
                _update(job, progress=(position + 1) / total * 100)
            except (JobError, YtdlpError, RuntimeError) as exc:
                errors.append(f"Clip {index + 1}: {exc}")
                _log(job, f"Clip {index + 1} failed: {exc}")
            finally:
                shutil.rmtree(job_dir, ignore_errors=True)
        session_store.write_clips(params["sessionId"], sorted(by_index.values(), key=lambda item: item["index"]))
        if errors and len(errors) == total:
            raise JobError("Semua klip gagal dirender. " + errors[0])
        _update(
            job,
            status="done",
            progress=100,
            message="Render selesai" if not errors else "Selesai dengan beberapa error",
            result={
                "sessionId": params["sessionId"],
                "clips": sorted(by_index.values(), key=lambda item: item["index"]),
                "outputDir": str(output_folder),
                "errors": errors,
            },
        )
    except (JobError, RuntimeError, ValueError) as exc:
        _fail(job, str(exc))
    except Exception as exc:  # noqa: BLE001
        _log(job, traceback.format_exc(limit=3))
        _fail(job, f"Unexpected error: {exc}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def start_render(params: dict) -> str:
    job = _new_job("render")
    thread = threading.Thread(target=_render_worker, args=(job, params), daemon=True)
    thread.start()
    return job["id"]
