"""Background jobs: find highlights, then render selected clips."""
from __future__ import annotations

import atexit
from concurrent.futures import Future, ThreadPoolExecutor
import copy
import json
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from . import session as session_store
from .assets import ffmpeg_path
from .config import DATA, load
from .highlights import AIError, LANGUAGES, build_messages, chat, extract_clips, select_clips, translate_groups
from .reframe import analyze_reframe
from .render import group_words, render_clip
from .subtitles import Word, parse_subtitle, slice_words, transcript
from .ytdlp import YtdlpError, download_section, download_subtitle, pick_subtitle, video_info

JOBS: dict[str, dict] = {}
_ACTIVE_SESSIONS: set[str] = set()
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_JOB_KILLERS: dict[str, Any] = {}
_lock = threading.RLock()
TMP = DATA / "tmp"


class SessionBusyError(RuntimeError):
    pass


class JobCancelledError(RuntimeError):
    pass


def is_session_busy(session_id: str) -> bool:
    with _lock:
        return session_id in _ACTIVE_SESSIONS


def cleanup_tmp(tmp_dir: Path | None = None) -> int:
    """Remove leftover temp folders from interrupted runs; call at server startup only."""
    root = tmp_dir or TMP
    if not root.is_dir():
        return 0
    removed = 0
    for entry in list(root.iterdir()):
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return removed


def _bilingual_translations(words, target, base, key, model, translate=None, on_error=None) -> list[str] | None:
    lines = [" ".join(word.word for word in group) for group in group_words(words)]
    if not lines:
        return None
    try:
        return (translate or translate_groups)(lines, target, base, key, model)
    except Exception as exc:  # noqa: BLE001 - translation is optional; never fail the render
        if on_error:
            on_error(exc)
        return None


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
        _CANCEL_EVENTS[job_id] = threading.Event()
        if len(JOBS) > 100:
            oldest = sorted(JOBS.values(), key=lambda item: item["createdAt"])[: len(JOBS) - 100]
            for old in oldest:
                if old["status"] != "running":
                    JOBS.pop(old["id"], None)
                    _CANCEL_EVENTS.pop(old["id"], None)
                    _JOB_KILLERS.pop(old["id"], None)
    return job


def _set_killer(job_id: str, slot: str, killer) -> None:
    with _lock:
        bucket = _JOB_KILLERS.get(job_id)
        if killer is None:
            if isinstance(bucket, dict):
                bucket.pop(slot, None)
                if not bucket:
                    _JOB_KILLERS.pop(job_id, None)
            elif slot == "main":
                _JOB_KILLERS.pop(job_id, None)
        else:
            if not isinstance(bucket, dict):
                bucket = {"main": bucket} if callable(bucket) else {}
                _JOB_KILLERS[job_id] = bucket
            bucket[slot] = killer


def _register_killer(job_id: str, killer) -> None:
    _set_killer(job_id, "main", killer)


def _add_killer(job_id: str, killer):
    slot = f"extra_{uuid.uuid4().hex[:8]}"
    _set_killer(job_id, slot, killer)
    return lambda: _set_killer(job_id, slot, None)


def _clear_killers(job_id: str) -> None:
    with _lock:
        _JOB_KILLERS.pop(job_id, None)


def _cancel_event(job_id: str) -> threading.Event:
    with _lock:
        return _CANCEL_EVENTS.setdefault(job_id, threading.Event())


def _check_cancel(job_id: str) -> None:
    with _lock:
        job = JOBS.get(job_id)
        ev = _CANCEL_EVENTS.get(job_id)
        cancelled = bool((ev and ev.is_set()) or (job and job.get("status") == "cancelled"))
    if cancelled:
        raise JobCancelledError("Dibatalkan")


def cancel(job_id: str) -> dict:
    with _lock:
        job = JOBS.get(job_id)
        if not job:
            raise KeyError("Job not found")
        ev = _CANCEL_EVENTS.setdefault(job_id, threading.Event())
        ev.set()
        raw_killers = _JOB_KILLERS.pop(job_id, None)
        if isinstance(raw_killers, dict):
            killers = list(raw_killers.values())
        elif callable(raw_killers):
            killers = [raw_killers]
        else:
            killers = []
        if job["status"] == "running":
            job["status"] = "cancelled"
            job["message"] = "Dibatalkan"
            job["log"] = (job["log"] + [f"{_now()}  Dibatalkan oleh pengguna"])[-300:]
    for killer in killers:
        try:
            killer()
        except Exception:  # noqa: BLE001
            pass
    return get(job_id)


def _shutdown_active_jobs() -> None:
    with _lock:
        running_ids = [jid for jid, job in JOBS.items() if job.get("status") == "running"]
    for jid in running_ids:
        try:
            cancel(jid)
        except Exception:  # noqa: BLE001
            pass


atexit.register(_shutdown_active_jobs)


def _update(job: dict, **fields) -> None:
    with _lock:
        if job.get("status") == "cancelled":
            return
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


def active_job() -> dict | None:
    with _lock:
        for job in reversed(list(JOBS.values())):
            if job["status"] == "running":
                return copy.deepcopy(job)
        return None


def _cookies_path() -> Path:
    return DATA / "cookies.txt"


def _fail(job: dict, message: str) -> None:
    with _lock:
        if job.get("status") == "cancelled":
            return
    _log(job, message)
    _update(job, status="error", error=message, message="Failed")


def _highlight_worker(job: dict, params: dict) -> None:
    config = load()
    workdir = TMP / job["id"]
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        _check_cancel(job["id"])
        _update(job, message="Reading video info", progress=4)
        info = video_info(params["url"], str(_cookies_path()) if _cookies_path().is_file() else None)
        _check_cancel(job["id"])
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
        _check_cancel(job["id"])
        _update(job, message="Parsing transcript", progress=22)
        cues, words = parse_subtitle(subtitle_path)
        if not words:
            raise JobError("Subtitle ditemukan tapi tidak berisi teks yang bisa dibaca.")
        text = transcript(cues, words)
        _log(job, f"Transcript: {len(words)} words, {len(text)} chars")
        if "[transcript truncated]" in text:
            _log(job, "Transkrip sangat panjang; diringkas dari bagian awal, tengah, dan akhir.")

        _update(job, message="AI is finding highlights (this can take a minute)", progress=30)
        direction = params.get("direction", "")
        output_language = params.get("outputLanguage") or config.get("outputLanguage", "auto")
        min_seconds = float(config["clip"]["minSeconds"])
        max_seconds = float(config["clip"]["maxSeconds"])
        requested = int(params["numClips"])
        messages = build_messages(
            info,
            text,
            requested,
            direction,
            output_language,
            min_seconds,
            max_seconds,
        )
        from .secret import api_key

        base_url = config["ai"]["baseUrl"]
        key = api_key(config)
        model = config["ai"]["model"]
        content, usage = chat(base_url, key, model, messages)
        _check_cancel(job["id"])
        _log(job, f"AI responded ({len(content)} chars)")
        items = extract_clips(content)
        highlights = select_clips(items, requested, duration, min_seconds, max_seconds)
        attempts = 0
        while len(highlights) < requested and attempts < 2:
            _check_cancel(job["id"])
            missing = requested - len(highlights)
            _log(job, f"AI returned {len(highlights)}/{requested} valid clips; requesting {missing} more")
            _update(job, message=f"AI is finding {missing} more highlights", progress=35 + attempts * 5)
            try:
                extra_content, _extra_usage = chat(
                    base_url,
                    key,
                    model,
                    build_messages(
                        info,
                        text,
                        missing,
                        direction,
                        output_language,
                        min_seconds,
                        max_seconds,
                        exclude=highlights,
                    ),
                )
            except AIError as exc:
                _log(job, f"Follow-up AI call failed: {exc}")
                break
            extra_items = extract_clips(extra_content)
            if not extra_items:
                break
            merged = select_clips(items + extra_items, requested, duration, min_seconds, max_seconds)
            if len(merged) <= len(highlights):
                break
            items = items + extra_items
            highlights = merged
            attempts += 1
        _log(job, f"Highlights selected: {len(highlights)}/{requested}")
        if not highlights:
            raise JobError(
                "AI tidak menghasilkan klip yang valid. Coba naikkan durasi maksimum atau ganti model."
            )
        result = session_store.create(
            params["url"],
            info,
            choice,
            words,
            text,
            highlights,
            {"model": config["ai"]["model"], "usage": usage},
            output_language=output_language,
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
                "requested": requested,
                "short": len(highlights) < requested,
            },
        )
        _log(job, f"Saved session {result['id']} with {len(highlights)} highlights")
    except JobCancelledError:
        pass
    except (JobError, AIError, YtdlpError, ValueError) as exc:
        _fail(job, str(exc))
    except Exception as exc:  # noqa: BLE001
        _log(job, traceback.format_exc(limit=3))
        _fail(job, f"Unexpected error: {exc}")
    finally:
        _register_killer(job["id"], None)
        with _lock:
            _CANCEL_EVENTS.pop(job["id"], None)
        shutil.rmtree(workdir, ignore_errors=True)


def start_highlights(params: dict) -> str:
    with _lock:
        if active_job() is not None:
            raise SessionBusyError("Masih ada proses yang sedang berjalan. Tunggu atau batalkan dulu.")
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
    cancel_ev = _cancel_event(job["id"])
    try:
        if isinstance(params.get("overrides"), dict) and params["overrides"]:
            session_store.update_highlights(params["sessionId"], params["overrides"])
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
        max_height = int(render_opts.get("maxHeight") or 1080)
        is_smart_fill = bool(render_opts.get("portrait", True)) and render_opts.get("background", "black") == "fill"

        plan: list[tuple[int, int, dict, float, float, Path, bool]] = []
        for position, index in enumerate(indices):
            clip = highlights[index]
            start = max(0.0, float(clip["start"]) - padding)
            end = float(clip["end"]) + padding
            if session.get("duration"):
                end = min(float(session["duration"]), end)
            out = output_folder / f"clip_{index + 1:02d}.mp4"
            skip = bool(out.exists() and out.stat().st_size > 1000 and not overwrite)
            plan.append((position, index, clip, start, end, out, skip))

        to_fetch = [(position, index, clip, start, end) for position, index, clip, start, end, _out, skip in plan if not skip]
        queue_pos_by_index = {item[1]: q_idx for q_idx, item in enumerate(to_fetch)}
        prefetched: dict[int, Future[Path]] = {}
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            def _fetch_clip(q_idx: int, is_prefetch: bool) -> Path:
                p_pos, p_idx, _p_clip, p_start, p_end = to_fetch[q_idx]
                slot = f"dl_{p_idx}"
                clip_dir = workdir / f"clip_{p_idx + 1}"

                def _on_line(line, percent, p=p_pos, i=p_idx, pf=is_prefetch):
                    if percent is not None and not pf:
                        _update(job, message=f"Downloading clip {p + 1}/{total} (#{i + 1}) ({percent:.0f}%)")

                try:
                    return download_section(
                        session["url"],
                        p_start,
                        p_end,
                        cookies,
                        clip_dir,
                        on_line=_on_line,
                        max_height=max_height,
                        cancel_event=cancel_ev,
                        on_process=lambda fn, s=slot: _set_killer(job["id"], s, fn),
                    )
                finally:
                    _set_killer(job["id"], slot, None)

            def _ensure_submitted(q_idx: int, is_prefetch: bool) -> None:
                if 0 <= q_idx < len(to_fetch) and q_idx not in prefetched and not cancel_ev.is_set():
                    prefetched[q_idx] = pool.submit(_fetch_clip, q_idx, is_prefetch)

            for position, index, clip, start, end, out, skip in plan:
                _check_cancel(job["id"])
                if skip:
                    _log(job, f"Clip {index + 1} already exists, skipping")
                    prev = by_index.get(index) or {}
                    by_index[index] = {
                        "index": index,
                        "file": out.name,
                        "title": clip.get("title", "") or prev.get("title", ""),
                        "description": clip.get("description", "") or prev.get("description", ""),
                        "hook": clip.get("hook_text", "") or prev.get("hook", ""),
                        "start": clip.get("start") if clip.get("start") is not None else prev.get("start"),
                        "end": clip.get("end") if clip.get("end") is not None else prev.get("end"),
                        "duration": prev.get("duration") or round(end - start, 2),
                    }
                    _update(job, progress=(position + 1) / total * 100)
                    continue
                job_dir = workdir / f"clip_{index + 1}"
                q_idx = queue_pos_by_index[index]
                try:
                    _update(job, message=f"Downloading clip {position + 1}/{total} (#{index + 1})", progress=(position / total) * 100)
                    _log(job, f"Clip {index + 1}: {clip.get('start')}s - {clip.get('end')}s")
                    _ensure_submitted(q_idx, is_prefetch=False)
                    section = prefetched.pop(q_idx).result()
                    _check_cancel(job["id"])
                    # shortcut: single-clip lookahead keeps temp disk usage bounded to 2 clip sections
                    _ensure_submitted(q_idx + 1, is_prefetch=True)
                    reframe_shots = None
                    if is_smart_fill:
                        _update(job, message="Menganalisis wajah & shot...")
                        try:
                            reframe_shots = analyze_reframe(section, ffmpeg, on_log=lambda m: _log(job, m))
                        except Exception as exc:  # noqa: BLE001 - fallback to static crop cleanly
                            _log(job, f"Auto-reframe gagal ({exc}); memakai center crop")
                            reframe_shots = None
                        if reframe_shots:
                            _log(job, f"Auto-reframe: {len(reframe_shots)} segmen shot")
                    _update(
                        job,
                        message=f"Rendering clip {position + 1}/{total} (#{index + 1})",
                        progress=(position / total) * 100 + 5 / total,
                    )
                    clip_words = slice_words(
                        stored_words,
                        start,
                        end,
                        clip_start=float(clip["start"]),
                        clip_end=float(clip["end"]),
                    )
                    duration = end - start

                    translations = None
                    if render_opts.get("captions", True) and render_opts.get("captionStyle") == "bilingual" and clip_words:
                        target = str(
                            render_opts.get("outputLanguage")
                            or session.get("outputLanguage")
                            or config.get("outputLanguage")
                            or "auto"
                        )
                        src_code = str((session.get("subtitle") or {}).get("code") or "").lower()
                        if target == "auto":
                            target = "id" if (src_code == "en" or src_code.startswith("en-")) else "en"
                        target_name = LANGUAGES.get(target, target)
                        from .secret import api_key

                        error_detail: list[str] = []
                        translations = _bilingual_translations(
                            clip_words,
                            target_name,
                            config["ai"]["baseUrl"],
                            api_key(config),
                            config["ai"]["model"],
                            on_error=lambda exc: error_detail.append(str(exc)),
                        )
                        if translations:
                            _log(job, f"Translated captions to {target_name}")
                        else:
                            reason = f" ({error_detail[0]})" if error_detail else ""
                            _log(job, f"Translation unavailable{reason}; rendering single-layer captions")

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
                        facecam_corner=render_opts.get("facecamCorner", "top-right"),
                        reframe_shots=reframe_shots,
                        captions=bool(render_opts.get("captions", True)),
                        hook=bool(render_opts.get("hook", True)),
                        watermark=render_opts.get("watermark", ""),
                        caption_color=render_opts.get("captionColor", "#FFD700"),
                        caption_style=render_opts.get("captionStyle", "highlight"),
                        caption_font=render_opts.get("captionFont", "Arial Black"),
                        caption_bold=bool(render_opts.get("captionBold", True)),
                        caption_uppercase=bool(render_opts.get("captionUppercase", False)),
                        hook_style=render_opts.get("hookStyle", "classic"),
                        watermark_position=render_opts.get("watermarkPosition", "top-right"),
                        credit_position=render_opts.get("creditPosition", "bottom-center"),
                        logo_opacity=float(render_opts.get("watermarkOpacity", 0.9)),
                        credit_opacity=float(render_opts.get("creditOpacity", 1.0)),
                        translations=translations,
                        on_progress=progress,
                        on_log=lambda message: _log(job, message),
                        cancel_event=cancel_ev,
                        on_process=lambda fn: _register_killer(job["id"], fn),
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
                    session_store.write_clips(
                        params["sessionId"],
                        sorted(by_index.values(), key=lambda item: item["index"]),
                    )
                    _log(job, f"Clip {index + 1} done: {out.name}")
                    _update(job, progress=(position + 1) / total * 100)
                except JobCancelledError:
                    out.unlink(missing_ok=True)
                    raise
                except (JobError, YtdlpError, RuntimeError, OSError) as exc:
                    if cancel_ev.is_set():
                        out.unlink(missing_ok=True)
                        raise JobCancelledError("Dibatalkan") from exc
                    if not (out.exists() and out.stat().st_size > 1000):
                        out.unlink(missing_ok=True)
                        by_index.pop(index, None)
                    errors.append(f"Clip {index + 1}: {exc}")
                    _log(job, f"Clip {index + 1} failed: {exc}")
                finally:
                    shutil.rmtree(job_dir, ignore_errors=True)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        _check_cancel(job["id"])
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
    except JobCancelledError:
        pass
    except (JobError, RuntimeError, ValueError) as exc:
        _fail(job, str(exc))
    except Exception as exc:  # noqa: BLE001
        _log(job, traceback.format_exc(limit=3))
        _fail(job, f"Unexpected error: {exc}")
    finally:
        _clear_killers(job["id"])
        with _lock:
            _ACTIVE_SESSIONS.discard(params.get("sessionId", ""))
            _CANCEL_EVENTS.pop(job["id"], None)
        shutil.rmtree(workdir, ignore_errors=True)


def start_render(params: dict) -> str:
    session_id = str(params.get("sessionId", ""))
    with _lock:
        if session_id in _ACTIVE_SESSIONS:
            raise SessionBusyError("Sesi ini sedang dirender. Tunggu render selesai.")
        if active_job() is not None:
            raise SessionBusyError("Masih ada proses yang sedang berjalan. Tunggu atau batalkan dulu.")
        _ACTIVE_SESSIONS.add(session_id)
        job = _new_job("render")
    try:
        thread = threading.Thread(target=_render_worker, args=(job, params), daemon=True)
        thread.start()
        return job["id"]
    except Exception:
        with _lock:
            _ACTIVE_SESSIONS.discard(session_id)
            JOBS.pop(job["id"], None)
            _CANCEL_EVENTS.pop(job["id"], None)
        raise
