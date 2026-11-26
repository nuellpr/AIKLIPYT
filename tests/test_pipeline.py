import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import pipeline  # noqa: E402
from core.pipeline import SessionBusyError, _bilingual_translations, cleanup_tmp, is_session_busy  # noqa: E402
from core.subtitles import Word  # noqa: E402


class BilingualTranslationTests(unittest.TestCase):
    def test_builds_one_line_per_group_in_order(self):
        words = [Word("a", 0.1, 0.4), Word("b", 0.5, 0.8), Word("c", 3.0, 3.4)]
        seen = {}

        def fake(texts, target, base, key, model):
            seen["texts"] = texts
            return [f"T{i}" for i in range(len(texts))]

        out = _bilingual_translations(words, "Indonesian", "base", "key", "model", translate=fake)
        self.assertEqual(seen["texts"], ["a b", "c"])
        self.assertEqual(out, ["T0", "T1"])

    def test_ai_failure_returns_none_and_reports_error(self):
        def boom(*a, **k):
            raise RuntimeError("offline")

        errors = []
        self.assertIsNone(
            _bilingual_translations(
                [Word("a", 0.1, 0.4)],
                "id",
                "b",
                "k",
                "m",
                translate=boom,
                on_error=lambda exc: errors.append(str(exc)),
            )
        )
        self.assertEqual(errors, ["offline"])


class TmpCleanupTests(unittest.TestCase):
    def test_cleanup_tmp_removes_stale_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            nested = tmp / "deadjob" / "clip_1"
            nested.mkdir(parents=True)
            (nested / "section.mp4").write_bytes(b"stale")
            (tmp / "orphan.tmp").write_text("x", encoding="utf-8")

            removed = cleanup_tmp(tmp)
            self.assertEqual(removed, 2)
            self.assertEqual(list(tmp.iterdir()), [])
            self.assertEqual(cleanup_tmp(tmp / "missing"), 0)


class SessionGuardTests(unittest.TestCase):
    def test_concurrent_render_for_same_session_is_rejected(self):
        sid = "20260101_000000_busytest"
        with pipeline._lock:
            pipeline._ACTIVE_SESSIONS.add(sid)
        try:
            self.assertTrue(is_session_busy(sid))
            with self.assertRaises(SessionBusyError):
                pipeline.start_render({"sessionId": sid, "indices": [0]})
        finally:
            with pipeline._lock:
                pipeline._ACTIVE_SESSIONS.discard(sid)
        self.assertFalse(is_session_busy(sid))


class WorkerIntegrationTests(unittest.TestCase):
    def test_highlight_worker_retries_and_avoids_double_nested_usage(self):
        import copy
        import json
        from unittest import mock
        from core.config import DEFAULTS
        from core import session as session_store

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sessions_dir = root / "sessions"
            outputs_dir = root / "outputs"
            tmp_dir = root / "tmp"
            cfg = copy.deepcopy(DEFAULTS)
            cfg["ai"]["baseUrl"] = "https://api.example/v1"
            cfg["ai"]["model"] = "demo-model"
            cfg["ai"]["apiKeyEnc"] = "env"

            responses = iter([
                ('{"clips":[{"start":0,"end":30,"title":"One","virality_score":9}]}', {"total_tokens": 50}),
                ('{"clips":[{"start":40,"end":75,"title":"Two","virality_score":8}]}', {"total_tokens": 30}),
            ])
            sub_file = root / "sub.en.srt"
            sub_file.write_text("1\n00:00:01,000 --> 00:00:05,000\nhello world\n", encoding="utf-8")

            with (
                mock.patch.dict(pipeline.JOBS, {}, clear=True),
                mock.patch.object(pipeline, "TMP", tmp_dir),
                mock.patch.object(pipeline, "DATA", root),
                mock.patch.object(pipeline, "load", return_value=cfg),
                mock.patch("core.secret.unprotect", return_value="sk-test"),
                mock.patch.object(session_store, "SESSIONS", sessions_dir),
                mock.patch.object(session_store, "OUTPUTS", outputs_dir),
                mock.patch.object(pipeline, "video_info", return_value={"id": "abc", "title": "Demo", "duration": 120}),
                mock.patch.object(pipeline, "pick_subtitle", return_value={"kind": "manual", "code": "en"}),
                mock.patch.object(pipeline, "download_subtitle", return_value=sub_file),
                mock.patch.object(pipeline, "chat", side_effect=lambda *a, **k: next(responses)),
            ):
                job = pipeline._new_job("highlights")
                self.assertEqual(pipeline.active_job()["id"], job["id"])
                pipeline._highlight_worker(
                    job,
                    {"url": "https://www.youtube.com/watch?v=abc", "numClips": 2, "subtitleLanguage": "auto"},
                )
                self.assertIsNone(pipeline.active_job())
                self.assertEqual(job["status"], "done")
                self.assertEqual(job["result"]["clipCount"], 2)
                sid = job["result"]["sessionId"]
                saved = json.loads((sessions_dir / sid / "session.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["ai"], {"model": "demo-model", "usage": {"total_tokens": 50}})
                self.assertFalse((tmp_dir / job["id"]).exists())

    def test_render_worker_preserves_existing_clip_and_drops_missing_on_failure(self):
        import copy
        import json
        from unittest import mock
        from core.config import DEFAULTS
        from core import session as session_store

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sessions_dir = root / "sessions"
            outputs_dir = root / "outputs"
            tmp_dir = root / "tmp"
            sid = "20260101_000000_partial"
            (sessions_dir / sid).mkdir(parents=True)
            (sessions_dir / sid / "words.json").write_text("[]", encoding="utf-8")
            (sessions_dir / sid / "session.json").write_text(
                json.dumps({
                    "id": sid,
                    "url": "https://www.youtube.com/watch?v=abc",
                    "duration": 120,
                    "highlights": [
                        {"start": 0, "end": 20, "title": "Zero"},
                        {"start": 30, "end": 50, "title": "One"},
                        {"start": 60, "end": 80, "title": "Two"},
                    ],
                }),
                encoding="utf-8",
            )
            out_dir = outputs_dir / sid
            out_dir.mkdir(parents=True)
            good_existing = b"good-mp4" * 200
            (out_dir / "clip_01.mp4").write_bytes(good_existing)
            (out_dir / "clips.json").write_text(
                json.dumps([
                    {"index": 0, "file": "clip_01.mp4", "title": "Zero"},
                    {"index": 1, "file": "clip_02.mp4", "title": "Stale"},
                ]),
                encoding="utf-8",
            )

            def fake_render(section, out, *args, **kwargs):
                if out.name == "clip_03.mp4":
                    out.write_bytes(b"new-mp4" * 200)
                    return out
                raise RuntimeError("boom")

            with (
                mock.patch.dict(pipeline.JOBS, {}, clear=True),
                mock.patch.object(pipeline, "TMP", tmp_dir),
                mock.patch.object(pipeline, "DATA", root),
                mock.patch.object(pipeline, "load", return_value=copy.deepcopy(DEFAULTS)),
                mock.patch.object(pipeline, "ffmpeg_path", return_value="ffmpeg"),
                mock.patch.object(session_store, "SESSIONS", sessions_dir),
                mock.patch.object(session_store, "OUTPUTS", outputs_dir),
                mock.patch.object(pipeline, "download_section", return_value=root / "sec.mp4"),
                mock.patch.object(pipeline, "render_clip", side_effect=fake_render),
            ):
                job = pipeline._new_job("render")
                pipeline._render_worker(job, {"sessionId": sid, "indices": [0, 1, 2], "overwrite": True})

            self.assertEqual(job["status"], "done")
            self.assertEqual(len(job["result"]["errors"]), 2)
            self.assertEqual((out_dir / "clip_01.mp4").read_bytes(), good_existing)
            self.assertFalse((out_dir / "clip_02.mp4").exists())
            clips = json.loads((out_dir / "clips.json").read_text(encoding="utf-8"))
            self.assertEqual([c["index"] for c in clips], [0, 2])

    def test_bilingual_uses_session_output_language_and_avoids_en_to_en_default(self):
        import copy
        import json
        from unittest import mock
        from core.config import DEFAULTS
        from core import session as session_store

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sessions_dir = root / "sessions"
            outputs_dir = root / "outputs"
            tmp_dir = root / "tmp"
            cfg = copy.deepcopy(DEFAULTS)
            cfg["ai"]["baseUrl"] = "https://api.example/v1"
            cfg["ai"]["model"] = "demo-model"
            cfg["ai"]["apiKeyEnc"] = "env"
            cfg["outputLanguage"] = "auto"
            cfg["render"]["captionStyle"] = "bilingual"

            sub_file = root / "sub.en.srt"
            sub_file.write_text("1\n00:00:01,000 --> 00:00:04,000\nhello world\n", encoding="utf-8")
            targets_seen = []

            def fake_translate(lines, target, *a, **k):
                targets_seen.append(target)
                return ["halo dunia" for _ in lines]

            def fake_render(section, out, *args, **kwargs):
                out.write_bytes(b"mp4" * 500)
                return out

            with (
                mock.patch.dict(pipeline.JOBS, {}, clear=True),
                mock.patch.object(pipeline, "TMP", tmp_dir),
                mock.patch.object(pipeline, "DATA", root),
                mock.patch.object(pipeline, "load", return_value=cfg),
                mock.patch("core.secret.unprotect", return_value="sk-test"),
                mock.patch.object(pipeline, "ffmpeg_path", return_value="ffmpeg"),
                mock.patch.object(session_store, "SESSIONS", sessions_dir),
                mock.patch.object(session_store, "OUTPUTS", outputs_dir),
                mock.patch.object(pipeline, "video_info", return_value={"id": "abc", "title": "Demo", "duration": 60}),
                mock.patch.object(pipeline, "pick_subtitle", return_value={"kind": "auto", "code": "en-orig"}),
                mock.patch.object(pipeline, "download_subtitle", return_value=sub_file),
                mock.patch.object(pipeline, "chat", return_value=('{"clips":[{"start":0,"end":25,"title":"One"}]}', {})),
                mock.patch.object(pipeline, "download_section", return_value=root / "sec.mp4"),
                mock.patch.object(pipeline, "translate_groups", side_effect=fake_translate),
                mock.patch.object(pipeline, "render_clip", side_effect=fake_render),
            ):
                h_job = pipeline._new_job("highlights")
                pipeline._highlight_worker(
                    h_job,
                    {"url": "https://www.youtube.com/watch?v=abc", "numClips": 1, "outputLanguage": "id"},
                )
                sid_id = h_job["result"]["sessionId"]
                r_job = pipeline._new_job("render")
                pipeline._render_worker(r_job, {"sessionId": sid_id, "indices": [0], "overwrite": True})

                h_job_auto = pipeline._new_job("highlights")
                pipeline._highlight_worker(
                    h_job_auto,
                    {"url": "https://www.youtube.com/watch?v=abc", "numClips": 1, "outputLanguage": "auto"},
                )
                sid_auto = h_job_auto["result"]["sessionId"]
                r_job_auto = pipeline._new_job("render")
                pipeline._render_worker(r_job_auto, {"sessionId": sid_auto, "indices": [0], "overwrite": True})

            self.assertEqual(targets_seen, ["Indonesian", "Indonesian"])

    def test_cancel_stops_running_job_and_rejects_parallel_jobs(self):
        from unittest import mock

        killed = []
        with mock.patch.dict(pipeline.JOBS, {}, clear=True):
            job = pipeline._new_job("render")
            pipeline._register_killer(job["id"], lambda: killed.append("ffmpeg"))
            pipeline._add_killer(job["id"], lambda: killed.append("ytdlp_prefetch"))
            with self.assertRaises(SessionBusyError):
                pipeline.start_highlights({"url": "https://www.youtube.com/watch?v=abc", "numClips": 1})
            cancelled = pipeline.cancel(job["id"])
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertCountEqual(killed, ["ffmpeg", "ytdlp_prefetch"])
            self.assertIsNone(pipeline.active_job())

    def test_render_worker_applies_highlight_overrides(self):
        import copy
        import json
        from unittest import mock
        from core.config import DEFAULTS
        from core import session as session_store

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sessions_dir = root / "sessions"
            outputs_dir = root / "outputs"
            tmp_dir = root / "tmp"
            sid = "20260101_000000_edit"
            (sessions_dir / sid).mkdir(parents=True)
            (sessions_dir / sid / "words.json").write_text("[]", encoding="utf-8")
            (sessions_dir / sid / "session.json").write_text(
                json.dumps({
                    "id": sid,
                    "url": "https://www.youtube.com/watch?v=abc",
                    "duration": 120,
                    "highlights": [{"start": 10, "end": 30, "title": "Old", "hook_text": "Old hook"}],
                }),
                encoding="utf-8",
            )
            seen = {}

            def fake_download(url, start, end, *a, **kw):
                seen["range"] = (start, end)
                return root / "sec.mp4"

            def fake_render(section, out, *args, **kwargs):
                seen["hook_text"] = kwargs.get("hook_text")
                out.write_bytes(b"mp4" * 500)
                return out

            cfg = copy.deepcopy(DEFAULTS)
            cfg["clip"]["padding"] = 0.0
            with (
                mock.patch.dict(pipeline.JOBS, {}, clear=True),
                mock.patch.object(pipeline, "TMP", tmp_dir),
                mock.patch.object(pipeline, "DATA", root),
                mock.patch.object(pipeline, "load", return_value=cfg),
                mock.patch.object(pipeline, "ffmpeg_path", return_value="ffmpeg"),
                mock.patch.object(session_store, "SESSIONS", sessions_dir),
                mock.patch.object(session_store, "OUTPUTS", outputs_dir),
                mock.patch.object(pipeline, "download_section", side_effect=fake_download),
                mock.patch.object(pipeline, "render_clip", side_effect=fake_render),
            ):
                job = pipeline._new_job("render")
                pipeline._render_worker(
                    job,
                    {
                        "sessionId": sid,
                        "indices": [0],
                        "overwrite": True,
                        "overrides": {"0": {"start": 15.5, "end": 40.0, "hook_text": "Hook Baru"}},
                    },
                )
            self.assertEqual(job["status"], "done")
            self.assertEqual(seen["range"], (15.5, 40.0))
            self.assertEqual(seen["hook_text"], "Hook Baru")
            updated_session = json.loads((sessions_dir / sid / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_session["highlights"][0]["hook_text"], "Hook Baru")

    def test_render_worker_prefetches_next_clip_and_uses_1080p_default(self):
        import copy
        import json
        import threading
        from unittest import mock
        from core.config import DEFAULTS
        from core import session as session_store

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sessions_dir = root / "sessions"
            outputs_dir = root / "outputs"
            tmp_dir = root / "tmp"
            sid = "20260101_000000_prefetch"
            (sessions_dir / sid).mkdir(parents=True)
            (sessions_dir / sid / "words.json").write_text("[]", encoding="utf-8")
            (sessions_dir / sid / "session.json").write_text(
                json.dumps({
                    "id": sid,
                    "url": "https://www.youtube.com/watch?v=abc",
                    "duration": 120,
                    "highlights": [
                        {"start": 0, "end": 20, "title": "First"},
                        {"start": 40, "end": 60, "title": "Second"},
                    ],
                }),
                encoding="utf-8",
            )
            clip2_started = threading.Event()
            max_heights = []
            overlapped = []

            def fake_download(url, start, end, cookies, workdir, **kwargs):
                max_heights.append(kwargs.get("max_height"))
                workdir.mkdir(parents=True, exist_ok=True)
                sec = workdir / "section.mp4"
                sec.write_bytes(b"sec")
                if start >= 30:
                    clip2_started.set()
                return sec

            def fake_render(section, out, *args, **kwargs):
                if out.name == "clip_01.mp4":
                    overlapped.append(clip2_started.wait(timeout=1.5))
                out.write_bytes(b"mp4" * 500)
                return out

            cfg = copy.deepcopy(DEFAULTS)
            cfg["render"]["background"] = "fill"
            with (
                mock.patch.dict(pipeline.JOBS, {}, clear=True),
                mock.patch.object(pipeline, "TMP", tmp_dir),
                mock.patch.object(pipeline, "DATA", root),
                mock.patch.object(pipeline, "load", return_value=cfg),
                mock.patch.object(pipeline, "ffmpeg_path", return_value="ffmpeg"),
                mock.patch.object(session_store, "SESSIONS", sessions_dir),
                mock.patch.object(session_store, "OUTPUTS", outputs_dir),
                mock.patch.object(pipeline, "analyze_reframe", return_value=None),
                mock.patch.object(pipeline, "download_section", side_effect=fake_download),
                mock.patch.object(pipeline, "render_clip", side_effect=fake_render),
            ):
                job = pipeline._new_job("render")
                pipeline._render_worker(job, {"sessionId": sid, "indices": [0, 1], "overwrite": True})

            self.assertEqual(job["status"], "done")
            self.assertEqual(overlapped, [True])
            self.assertEqual(max_heights, [1080, 1080])


if __name__ == "__main__":
    unittest.main()
