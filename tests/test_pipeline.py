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


if __name__ == "__main__":
    unittest.main()
