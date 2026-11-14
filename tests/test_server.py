import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import (  # noqa: E402
    _model_auth,
    _origin_allowed,
    _static_path,
    _trusted_host,
    _trusted_origin,
)


class HostCheckTests(unittest.TestCase):
    def test_accepts_local_origins_and_hosts(self):
        for value in (
            "http://127.0.0.1:8799",
            "http://localhost:8765",
            "https://localhost",
            "127.0.0.1:8799",
            "localhost:8765",
            "[::1]:8799",
            "::1",
        ):
            self.assertTrue(_trusted_host(value), value)

    def test_rejects_other_hosts(self):
        for value in (
            "",
            "http://evil.example",
            "https://127.0.0.1.evil.example",
            "http://localhost.evil.example:8799",
            "null",
        ):
            self.assertFalse(_trusted_host(value), value)


class OriginCheckTests(unittest.TestCase):
    def test_accepts_exact_serving_origin(self):
        for origin, host in (
            ("http://127.0.0.1:8765", "127.0.0.1:8765"),
            ("http://localhost:8765", "localhost:8765"),
            ("http://[::1]:8765", "[::1]:8765"),
        ):
            self.assertTrue(_trusted_origin(origin, host))

    def test_rejects_other_port_scheme_or_host(self):
        for origin, host in (
            ("http://127.0.0.1:5173", "127.0.0.1:8765"),
            ("https://127.0.0.1:8765", "127.0.0.1:8765"),
            ("http://evil.example:8765", "127.0.0.1:8765"),
            ("http://user@127.0.0.1:8765", "127.0.0.1:8765"),
            ("null", "127.0.0.1:8765"),
            ("", "127.0.0.1:8765"),
        ):
            self.assertFalse(_trusted_origin(origin, host))

    def test_missing_origin_only_allowed_for_reads(self):
        self.assertTrue(_origin_allowed(None, "127.0.0.1:8765", "GET"))
        self.assertFalse(_origin_allowed(None, "127.0.0.1:8765", "POST"))
        self.assertTrue(_origin_allowed("http://127.0.0.1:8765", "127.0.0.1:8765", "POST"))
        self.assertFalse(_origin_allowed("http://127.0.0.1:5173", "127.0.0.1:8765", "POST"))
        self.assertFalse(_origin_allowed(None, "evil.example:8765", "GET"))


class StaticPathTests(unittest.TestCase):
    def test_serves_plain_web_files(self):
        self.assertIsNotNone(_static_path("app.js"))
        self.assertIsNotNone(_static_path("sub/../app.js"))

    def test_rejects_traversal_and_windows_paths(self):
        for value in (
            "../server.py",
            "..\\server.py",
            "C:/Windows/win.ini",
            "\\\\attacker\\share\\preview.png",
        ):
            self.assertIsNone(_static_path(value), value)


class ModelAuthTests(unittest.TestCase):
    def setUp(self):
        self.config = {"ai": {"baseUrl": "https://saved.example/v1", "apiKeyEnc": ""}}

    def test_explicit_key_may_use_a_new_base_url(self):
        base, key = _model_auth(
            {"baseUrl": "https://other.example/v1", "apiKey": "sk-user"},
            self.config,
        )
        self.assertEqual(base, "https://other.example/v1")
        self.assertEqual(key, "sk-user")

    def test_stored_key_is_not_sent_to_a_new_base_url(self):
        with self.assertRaises(ValueError):
            _model_auth({"baseUrl": "https://other.example/v1"}, self.config)

    def test_saved_base_url_may_use_the_stored_key(self):
        base, _ = _model_auth({"baseUrl": "https://saved.example/v1/"}, self.config)
        self.assertEqual(base, "https://saved.example/v1/")


if __name__ == "__main__":
    unittest.main()
