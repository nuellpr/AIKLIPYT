"""Fetch the model catalog from an OpenAI-compatible provider."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class ModelsError(Exception):
    """A user-facing failure while listing models."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect could forward the Authorization header to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RequestFailure(Exception):
    def __init__(self, kind: str, detail: str = "", code: int = 0):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.code = code


def request_json(
    url: str,
    headers: dict[str, str],
    data: bytes | None = None,
    timeout: float = 25.0,
    detail_limit: int = 500,
):
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(4_000_000)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", "replace").strip()[:detail_limit]
        exc.close()
        raise RequestFailure("http", detail, exc.code) from exc
    except urllib.error.URLError as exc:
        raise RequestFailure("conn", str(exc.reason)) from exc
    except TimeoutError as exc:
        raise RequestFailure("timeout", "timeout") from exc
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise RequestFailure("json", "invalid json") from exc


def list_models(base_url: str, key: str, timeout: float = 25.0) -> list[str]:
    base = (base_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ModelsError("Base URL harus diawali http:// atau https://")
    if not key:
        raise ModelsError("API key belum diisi")
    try:
        payload = request_json(
            base + "/models",
            {"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=timeout,
            detail_limit=300,
        )
    except RequestFailure as exc:
        if exc.kind == "http":
            message = f"Provider menolak permintaan (HTTP {exc.code})"
            raise ModelsError(f"{message}: {exc.detail}" if exc.detail else message) from exc
        if exc.kind == "conn":
            raise ModelsError(f"Tidak bisa menghubungi provider: {exc.detail}") from exc
        if exc.kind == "timeout":
            raise ModelsError("Provider terlalu lama merespons") from exc
        raise ModelsError("Respons provider bukan JSON") from exc

    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        items = payload.get("models", []) if isinstance(payload, dict) else []
    found: set[str] = set()
    for item in items:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = str(item.get("id") or item.get("name") or "")
        else:
            continue
        name = name.strip()
        if name.startswith("models/"):
            name = name[7:]
        if name:
            found.add(name)
    if not found:
        raise ModelsError("Provider tidak mengembalikan model")
    return sorted(found)[:2000]
