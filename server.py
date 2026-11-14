"""Local-only web server for AIKLIPYT."""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from core import cookies as cookie_store
from core import models as model_catalog
from core import pipeline, session as session_store
from core.assets import deno_path, ffmpeg_path
from core.config import DATA, ROOT, ensure_dirs, load, save
from core.secret import api_key, protect

WEB = ROOT / "web"
VERSION = "1.0.2"
POSITIONS = {
    "top-left",
    "top-center",
    "top-right",
    "middle-left",
    "center",
    "middle-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
}
COOKIES = DATA / "cookies.txt"
WATERMARKS = DATA / "watermarks"
MAX_BODY = 8 * 1024 * 1024


def _public_config() -> dict:
    config = load()
    key = api_key(config)
    config["ai"].pop("apiKeyEnc", None)
    config["ai"]["hasKey"] = bool(key)
    return config


def _state() -> dict:
    return {
        "version": VERSION,
        "config": _public_config(),
        "cookies": cookie_store.status(COOKIES),
        "assets": {
            "ffmpeg": ffmpeg_path(),
            "deno": deno_path(),
        },
    }


def _trusted_host(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    if value == "::1":
        return True
    try:
        parsed = urlsplit(value if "://" in value else "//" + value)
        host = parsed.hostname
    except ValueError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


def _apply_settings(body: dict) -> dict:
    config = load()
    ai = body.get("ai")
    if isinstance(ai, dict):
        ai = dict(ai)
        if "apiKey" in ai:
            key = ai.pop("apiKey")
            if isinstance(key, str) and key:
                config["ai"]["apiKeyEnc"] = protect(key)
            elif key == "":
                config["ai"]["apiKeyEnc"] = ""
        for field in ("baseUrl", "model"):
            if isinstance(ai.get(field), str):
                config["ai"][field] = ai[field].strip()
    for section in ("clip", "render", "paths"):
        values = body.get(section)
        if isinstance(values, dict):
            for key, value in values.items():
                if key in ("minSeconds", "maxSeconds", "padding", "hookSeconds", "watermarkOpacity", "creditOpacity"):
                    try:
                        config[section][key] = float(value)
                    except (TypeError, ValueError):
                        continue
                elif key in ("portrait", "captions", "hook"):
                    config[section][key] = bool(value)
                elif isinstance(value, str):
                    config[section][key] = value.strip()
    if isinstance(body.get("outputLanguage"), str):
        config["outputLanguage"] = body["outputLanguage"]
    config["clip"]["minSeconds"] = max(5.0, min(600.0, config["clip"]["minSeconds"]))
    config["clip"]["maxSeconds"] = max(config["clip"]["minSeconds"], min(600.0, config["clip"]["maxSeconds"]))
    config["clip"]["padding"] = max(0.0, min(5.0, config["clip"]["padding"]))
    color = str(config["render"].get("captionColor") or "").strip()
    config["render"]["captionColor"] = color if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else "#FFD700"
    if config["render"].get("captionStyle") not in (
        "highlight",
        "box",
        "pop",
        "smart-bg-focus",
        "box-highlight",
        "word-focus",
        "underline-focus",
        "outline-focus",
        "temp-0",
    ):
        config["render"]["captionStyle"] = "highlight"
    if config["render"].get("watermarkPosition") not in POSITIONS:
        config["render"]["watermarkPosition"] = "top-right"
    if config["render"].get("creditPosition") not in POSITIONS:
        config["render"]["creditPosition"] = "bottom-center"
    for key, default in (("watermarkOpacity", 0.9), ("creditOpacity", 1.0)):
        try:
            value = float(config["render"].get(key, default))
        except (TypeError, ValueError):
            value = default
        config["render"][key] = max(0.0, min(1.0, value))
    return save(config)


class Handler(BaseHTTPRequestHandler):
    server_version = f"AIKLIPYT/{VERSION}"
    protocol_version = "HTTP/1.1"

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def log_message(self, fmt, *args):  # noqa: A003 - stdlib signature
        pass

    # ---------- helpers ----------
    def _headers(self, status: int, content_type: str, length: int, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' https://i.ytimg.com data: blob:; "
                "media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'",
            )
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()

    def _json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data), {"Cache-Control": "no-store"})
        self.wfile.write(data)

    def _error(self, status: int, message: str):
        self._json(status, {"ok": False, "error": message})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Request body is empty or too large")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise ValueError("Invalid JSON body") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _check_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and not _trusted_host(origin):
            self._error(403, "Cross-origin request blocked")
            return False
        if not _trusted_host(self.headers.get("Host", "")):
            self._error(403, "Invalid host")
            return False
        return True

    def _serve_file(self, path: Path, content_type: str | None = None, download_name: str | None = None):
        if not path.is_file():
            self._error(404, "File not found")
            return
        content_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        extra = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match:
                self._error(416, "Invalid range")
                return
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = min(size - 1, int(match.group(2)))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        length = end - start + 1
        if download_name:
            extra["Content-Disposition"] = f'attachment; filename="{download_name}"'
        self._headers(status, content_type, length, extra)
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                remaining -= len(chunk)

    # ---------- HTTP ----------
    def do_GET(self):  # noqa: N802
        if not self._check_origin():
            return
        path = unquote(urlsplit(self.path).path)
        if path == "/api/state":
            self._json(200, {"ok": True, **_state()})
            return
        if path == "/api/sessions":
            self._json(200, {"ok": True, "sessions": session_store.list_all()})
            return
        if path.startswith("/api/sessions/"):
            try:
                data = session_store.load(path.rsplit("/", 1)[-1])
                self._json(200, {"ok": True, "session": data})
            except (FileNotFoundError, ValueError) as exc:
                self._error(404, str(exc))
            return
        if path.startswith("/api/jobs/"):
            try:
                self._json(200, {"ok": True, "job": pipeline.get(path.rsplit("/", 1)[-1])})
            except KeyError as exc:
                self._error(404, str(exc))
            return
        if path == "/api/watermark":
            source = Path(load()["render"].get("watermark") or "")
            if not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                self._error(404, "Watermark belum ada")
                return
            self._serve_file(source, mimetypes.guess_type(source.name)[0] or "application/octet-stream")
            return
        if path.startswith("/api/media/"):
            parts = path.split("/")
            if len(parts) != 5:
                self._error(404, "Not found")
                return
            session_id, name = parts[3], parts[4]
            if not re.match(r"^clip_\d{2}\.mp4$", name):
                self._error(404, "Not found")
                return
            try:
                self._serve_file(session_store.output_dir(session_id) / name, "video/mp4")
            except ValueError:
                self._error(400, "Invalid session id")
            return

        relative = path.lstrip("/") or "index.html"
        candidate = (WEB / relative).resolve()
        try:
            candidate.relative_to(WEB.resolve())
        except ValueError:
            self._error(404, "Not found")
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.is_file():
            self._error(404, "Not found")
            return
        self._serve_file(candidate)

    def do_POST(self):  # noqa: N802
        if not self._check_origin():
            return
        path = urlsplit(self.path).path
        try:
            body = self._body()
        except ValueError as exc:
            self._error(400, str(exc))
            return
        try:
            if path == "/api/models":
                current = load()
                base = str(body.get("baseUrl") or current["ai"].get("baseUrl") or "").strip()
                key = str(body.get("apiKey") or "").strip() or api_key(current) or ""
                try:
                    models = model_catalog.list_models(base, key)
                except model_catalog.ModelsError as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
                self._json(200, {"ok": True, "models": models})
                return
            if path == "/api/settings":
                _apply_settings(body)
                self._json(200, {"ok": True, **_state()})
                return
            if path == "/api/cookies":
                stats = cookie_store.save(COOKIES, body.get("content", ""))
                self._json(200, {"ok": True, "cookies": cookie_store.status(COOKIES), "filtered": stats})
                return
            if path == "/api/cookies/delete":
                cookie_store.remove(COOKIES)
                self._json(200, {"ok": True, "cookies": cookie_store.status(COOKIES)})
                return
            if path == "/api/watermark":
                raw_name = str(body.get("name") or "watermark")
                data = str(body.get("data") or "")
                match = re.match(r"^data:image/(png|jpe?g);base64,(.+)$", data, re.S)
                if not match:
                    self._error(400, "Format gambar tidak didukung. Gunakan PNG atau JPG.")
                    return
                try:
                    payload = base64.b64decode(match.group(2), validate=True)
                except (ValueError, TypeError):
                    self._error(400, "Gambar tidak valid.")
                    return
                if not payload or len(payload) > 6 * 1024 * 1024:
                    self._error(400, "Ukuran gambar maksimal 6 MB.")
                    return
                ext = ".png" if match.group(1).lower() == "png" else ".jpg"
                stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(raw_name).stem).strip("-")[:40] or "watermark"
                WATERMARKS.mkdir(parents=True, exist_ok=True)
                target = WATERMARKS / f"{stem}-{int(time.time() * 1000)}{ext}"
                target.write_bytes(payload)
                self._json(200, {"ok": True, "path": str(target)})
                return
            if path == "/api/highlights":
                url = str(body.get("url", "")).strip()
                if not re.match(r"^https?://", url):
                    self._error(400, "URL video tidak valid")
                    return
                try:
                    num = max(1, min(20, int(body.get("numClips", 5))))
                except (TypeError, ValueError):
                    num = 5
                job_id = pipeline.start_highlights(
                    {
                        "url": url,
                        "numClips": num,
                        "subtitleLanguage": str(body.get("subtitleLanguage", "auto")),
                        "direction": str(body.get("direction", ""))[:2000],
                        "outputLanguage": str(body.get("outputLanguage", "auto")),
                    }
                )
                self._json(200, {"ok": True, "jobId": job_id})
                return
            if path == "/api/render":
                session_id = str(body.get("sessionId", ""))
                if not session_store.valid_id(session_id):
                    self._error(400, "Session tidak valid")
                    return
                indices = body.get("indices")
                if not isinstance(indices, list):
                    indices = []
                job_id = pipeline.start_render(
                    {
                        "sessionId": session_id,
                        "indices": [int(item) for item in indices if isinstance(item, (int, str)) and str(item).isdigit()],
                        "overwrite": bool(body.get("overwrite")),
                        "render": body.get("render") if isinstance(body.get("render"), dict) else {},
                    }
                )
                self._json(200, {"ok": True, "jobId": job_id})
                return
            if path == "/api/open":
                session_id = str(body.get("sessionId", ""))
                kind = body.get("kind", "output")
                folder = session_store.session_dir(session_id) if kind == "session" else session_store.output_dir(session_id)
                if not folder.is_dir():
                    self._error(404, "Folder belum ada")
                    return
                if os.name == "nt":
                    subprocess.Popen(["explorer", str(folder)])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(folder)])
                else:
                    subprocess.Popen(["xdg-open", str(folder)])
                self._json(200, {"ok": True})
                return
            if path == "/api/delete":
                session_store.delete(str(body.get("sessionId", "")))
                self._json(200, {"ok": True})
                return
            self._error(404, "Not found")
        except (ValueError, FileNotFoundError) as exc:
            self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"Server error: {exc}")


def _serve(port: int) -> ThreadingHTTPServer:
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            server.daemon_threads = True
            return server
        except OSError:
            continue
    raise RuntimeError("No free port in range")


def main() -> None:
    parser = argparse.ArgumentParser(description="AIKLIPYT local server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    ensure_dirs()
    server = _serve(args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"AIKLIPYT {VERSION} running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
