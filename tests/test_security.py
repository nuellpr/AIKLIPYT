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


class SecretTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "DPAPI is Windows-only")
    def test_dpapi_roundtrip(self):
        token = "sk-test-1234567890"
        encrypted = protect(token)
        self.assertTrue(encrypted.startswith("dpapi:"))
        self.assertNotIn(token, encrypted)
        self.assertEqual(unprotect(encrypted), token)


class SessionTests(unittest.TestCase):
    def test_ids(self):
        self.assertTrue(session.valid_id("20260101_120000_demo"))
        self.assertTrue(session.valid_id("abc"))
        self.assertFalse(session.valid_id("../../etc/passwd"))
        self.assertFalse(session.valid_id("a b"))
        self.assertFalse(session.valid_id(""))


if __name__ == "__main__":
    unittest.main()
