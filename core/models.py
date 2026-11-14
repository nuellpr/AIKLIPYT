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


def list_models(base_url: str, key: str, timeout: float = 25.0) -> list[str]:
    base = (base_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ModelsError("Base URL harus diawali http:// atau https://")
    if not key:
        raise ModelsError("API key belum diisi")
    request = urllib.request.Request(
        base + "/models",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(4_000_000)
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode("utf-8", "replace").strip()
        message = f"Provider menolak permintaan (HTTP {exc.code})"
        raise ModelsError(f"{message}: {detail}" if detail else message) from exc
    except urllib.error.URLError as exc:
        raise ModelsError(f"Tidak bisa menghubungi provider: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ModelsError("Provider terlalu lama merespons") from exc

    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
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
