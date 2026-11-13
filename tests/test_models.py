import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import ModelsError, list_models  # noqa: E402


class ModelsTests(unittest.TestCase):
    def test_lists_unique_sorted_models(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                captured["path"] = self.path
                captured["auth"] = self.headers.get("Authorization")
                data = json.dumps(
                    {"data": [{"id": "zeta"}, {"id": "alpha"}, {"id": "alpha"}, {"id": "models/beta"}]}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            models = list_models(f"http://127.0.0.1:{server.server_address[1]}/v1", "sk-test")
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(models, ["alpha", "beta", "zeta"])
        self.assertEqual(captured["path"], "/v1/models")
        self.assertEqual(captured["auth"], "Bearer sk-test")

    def test_provider_error_is_reported(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                data = b'{"error":"invalid key"}'
                self.send_response(401)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(ModelsError) as error:
                list_models(f"http://127.0.0.1:{server.server_address[1]}/v1", "bad")
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("401", str(error.exception))

    def test_requires_url_and_key(self):
        with self.assertRaises(ModelsError):
            list_models("ftp://example.com", "key")
        with self.assertRaises(ModelsError):
            list_models("https://example.com/v1", "")


if __name__ == "__main__":
    unittest.main()
