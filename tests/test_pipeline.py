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


if __name__ == "__main__":
    unittest.main()
