import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import (  # noqa: E402
    Handler,
    _normalize_caption_font,
    _normalize_caption_style,
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


class _FakeHandler:
    def __init__(self, headers):
        self.headers = headers
        self.chunks = []
        self.wfile = self
        self.status = None

    def write(self, data):
        self.chunks.append(data)
        return len(data)

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        pass

    def end_headers(self):
        pass

    def _headers(self, status, content_type, length, extra=None):
        self.status = status

    def _error(self, status, message):
        self.status = status


class RangeTests(unittest.TestCase):
    def test_suffix_range_returns_the_last_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clip.mp4"
            path.write_bytes(b"0123456789")
            handler = _FakeHandler({"Range": "bytes=-4"})
            Handler._serve_file(handler, path, "video/mp4")
            self.assertEqual(handler.status, 206)
            self.assertEqual(b"".join(handler.chunks), b"6789")

    def test_open_ended_range_returns_rest(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clip.mp4"
            path.write_bytes(b"0123456789")
            handler = _FakeHandler({"Range": "bytes=6-"})
            Handler._serve_file(handler, path, "video/mp4")
            self.assertEqual(b"".join(handler.chunks), b"6789")


class CaptionStyleTests(unittest.TestCase):
    def test_all_caption_styles_are_accepted(self):
        from core.render import CAPTION_STYLES

        for style in CAPTION_STYLES:
            config = {"render": {"captionStyle": style}}
            _normalize_caption_style(config)
            self.assertEqual(config["render"]["captionStyle"], style)

    def test_unknown_style_falls_back(self):
        config = {"render": {"captionStyle": "nonsense"}}
        _normalize_caption_style(config)
        self.assertEqual(config["render"]["captionStyle"], "highlight")


class CaptionFontTests(unittest.TestCase):
    def test_all_caption_fonts_are_accepted(self):
        from core.render import CAPTION_FONTS

        for font in CAPTION_FONTS:
            config = {"render": {"captionFont": font}}
            _normalize_caption_font(config)
            self.assertEqual(config["render"]["captionFont"], font)

    def test_unknown_font_falls_back(self):
        config = {"render": {"captionFont": "NotAFont,99"}}
        _normalize_caption_font(config)
        self.assertEqual(config["render"]["captionFont"], "Arial Black")

    def test_ui_font_options_match_whitelist(self):
        import re
        from core.render import CAPTION_FONTS

        html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
        block = re.search(r'<select id="captionFont">(.*?)</select>', html, re.S)
        self.assertIsNotNone(block)
        values = re.findall(r'<option value="([^"]+)">', block.group(1))
        self.assertEqual(tuple(values), CAPTION_FONTS)


if __name__ == "__main__":
    unittest.main()
