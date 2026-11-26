import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import cookies, session  # noqa: E402
from core.secret import protect, unprotect  # noqa: E402


COOKIE_TEXT = """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tTRUE\t1999999999\tSID\tyoutube-secret
.youtube.com\tTRUE\t/\tTRUE\t1999999999\tPREF\tpref-value
.google.com\tTRUE\t/\tTRUE\t1999999999\tSID\tgoogle-login
.google.com\tTRUE\t/\tTRUE\t1999999999\tGMAIL_AT\tmust-not-leak
.example.com\tTRUE\t/\tTRUE\t1999999999\ttracker\tmust-not-leak
.youtube.com\tTRUE\t/\tTRUE\t1999999999\tVISITOR_INFO1_LIVE\tvisitor
"""


class CookieFilterTests(unittest.TestCase):
    def test_filters_unrelated_domains(self):
        filtered, stats = cookies.filter_cookies(COOKIE_TEXT)
        self.assertIn("youtube-secret", filtered)
        self.assertIn("google-login", filtered)
        self.assertNotIn("must-not-leak", filtered)
        self.assertEqual(stats["skipped"], 2)
        self.assertEqual(stats["kept"], 4)
        self.assertTrue(stats["hasAuth"])
        self.assertTrue(filtered.startswith(cookies.HEADER))

    def test_rejects_non_youtube_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                cookies.save(Path(folder) / "cookies.txt", "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tx\ty\n")

    def test_status_counts(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cookies.txt"
            cookies.save(path, COOKIE_TEXT)
            status = cookies.status(path)
            self.assertTrue(status["saved"])
            self.assertEqual(status["count"], 4)
            self.assertTrue(status["hasAuth"])

    def test_preserves_httponly_youtube_and_auth_cookies(self):
        import tempfile

        raw = (
            "# Netscape HTTP Cookie File\n"
            "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\tsecret-login\n"
            "#HttpOnly_.google.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-1PSID\tgoogle-1psid\n"
            "#HttpOnly_.google.com\tTRUE\t/\tTRUE\t1999999999\tGMAIL_AT\tmust-not-leak\n"
        )
        filtered, stats = cookies.filter_cookies(raw)
        self.assertIn("#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\tsecret-login", filtered)
        self.assertIn("#HttpOnly_.google.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-1PSID\tgoogle-1psid", filtered)
        self.assertNotIn("GMAIL_AT", filtered)
        self.assertEqual(stats["kept"], 2)
        self.assertEqual(stats["skipped"], 1)
        self.assertTrue(stats["hasAuth"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cookies.txt"
            cookies.save(path, raw)
            status = cookies.status(path)
            self.assertEqual(status["count"], 2)
            self.assertTrue(status["hasAuth"])


class SecretTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "DPAPI is Windows-only")
    def test_dpapi_roundtrip(self):
        token = "sk-test-1234567890"
        encrypted = protect(token)
        self.assertTrue(encrypted.startswith("dpapi:"))
        self.assertNotIn(token, encrypted)
        self.assertEqual(unprotect(encrypted), token)

    def test_unprotect_corrupt_returns_empty(self):
        self.assertEqual(unprotect("dpapi:not-valid-base64!!!"), "")
        self.assertEqual(unprotect("dpapi:AAAA"), "")


class SessionTests(unittest.TestCase):
    def test_ids(self):
        self.assertTrue(session.valid_id("20260101_120000_demo"))
        self.assertTrue(session.valid_id("abc"))
        self.assertFalse(session.valid_id("../../etc/passwd"))
        self.assertFalse(session.valid_id("a b"))
        self.assertFalse(session.valid_id(""))

    def test_delete_preserves_session_if_outputs_locked(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as folder:
            sessions_dir = Path(folder) / "sessions"
            outputs_dir = Path(folder) / "outputs"
            sid = "20260101_000000_locked"
            (sessions_dir / sid).mkdir(parents=True)
            (sessions_dir / sid / "session.json").write_text('{"id":"%s"}' % sid, encoding="utf-8")
            (outputs_dir / sid).mkdir(parents=True)
            (outputs_dir / sid / "clip_01.mp4").write_bytes(b"video")

            real_rmtree = session.shutil.rmtree

            def fail_outputs(path, *a, **kw):
                if Path(path) == outputs_dir / sid:
                    raise PermissionError("file in use")
                return real_rmtree(path, *a, **kw)

            with (
                mock.patch.object(session, "SESSIONS", sessions_dir),
                mock.patch.object(session, "OUTPUTS", outputs_dir),
                mock.patch.object(session.shutil, "rmtree", side_effect=fail_outputs),
            ):
                with self.assertRaises(PermissionError):
                    session.delete(sid)
            self.assertTrue((sessions_dir / sid / "session.json").is_file())

    def test_session_lifecycle_and_ai_usage_shape(self):
        import tempfile
        from unittest import mock
        from core.subtitles import Word

        with tempfile.TemporaryDirectory() as folder:
            sessions_dir = Path(folder) / "sessions"
            outputs_dir = Path(folder) / "outputs"
            with (
                mock.patch.object(session, "SESSIONS", sessions_dir),
                mock.patch.object(session, "OUTPUTS", outputs_dir),
            ):
                created = session.create(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    {"id": "dQw4w9WgXcQ", "title": "Demo Video", "channel": "Demo", "duration": 60},
                    {"kind": "auto", "code": "en-orig"},
                    [Word("halo", 0.1, 0.5)],
                    "[0:00] halo",
                    [{"start": 0, "end": 30, "title": "Clip 1"}],
                    {"model": "gpt-4.1-mini", "usage": {"total_tokens": 99}},
                )
                sid = created["id"]
                loaded = session.load(sid)
                self.assertEqual(loaded["ai"], {"model": "gpt-4.1-mini", "usage": {"total_tokens": 99}})
                session.write_clips(sid, [{"index": 0, "file": "clip_01.mp4"}])
                listing = session.list_all()
                self.assertEqual(len(listing), 1)
                self.assertEqual(listing[0]["clipCount"], 1)
                session.delete(sid)
                self.assertEqual(session.list_all(), [])
                self.assertFalse((outputs_dir / sid).exists())

    def test_session_load_reconstructs_clips_from_mp4_when_clips_json_missing(self):
        import tempfile
        from unittest import mock
        from core.subtitles import Word

        with tempfile.TemporaryDirectory() as folder:
            sessions_dir = Path(folder) / "sessions"
            outputs_dir = Path(folder) / "outputs"
            with (
                mock.patch.object(session, "SESSIONS", sessions_dir),
                mock.patch.object(session, "OUTPUTS", outputs_dir),
            ):
                created = session.create(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    {"id": "dQw4w9WgXcQ", "title": "Demo", "duration": 60},
                    {"kind": "auto", "code": "id-orig"},
                    [Word("halo", 0.1, 0.5)],
                    "[0:00] halo",
                    [{"start": 5, "end": 25, "title": "Klip Satu", "description": "Desc #tag"}],
                    {"model": "m", "usage": {}},
                )
                sid = created["id"]
                mp4 = outputs_dir / sid / "clip_01.mp4"
                mp4.write_bytes(b"v" * 2000)
                loaded = session.load(sid)
                self.assertEqual(len(loaded["clips"]), 1)
                self.assertEqual(loaded["clips"][0]["file"], "clip_01.mp4")
                self.assertEqual(loaded["clips"][0]["title"], "Klip Satu")
                self.assertEqual(loaded["clips"][0]["description"], "Desc #tag")


if __name__ == "__main__":
    unittest.main()
