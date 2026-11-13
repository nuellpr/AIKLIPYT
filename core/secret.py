"""API key storage.

Windows: encrypted with DPAPI (per-user, per-machine) via ctypes.
Other platforms: reversible base64 is *not* security, so we store nothing and
ask for the key through an environment variable instead.
"""
from __future__ import annotations

import base64
import ctypes
import os
import sys
from ctypes import wintypes

_IS_WIN = sys.platform == "win32"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DataBlob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _dpapi(data: bytes, unprotect: bool) -> bytes:
    fn = ctypes.windll.crypt32.CryptUnprotectData if unprotect else ctypes.windll.crypt32.CryptProtectData
    blob_in = _blob(data)
    blob_out = _DataBlob()
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def protect(text: str) -> str:
    if not text:
        return ""
    if _IS_WIN:
        return "dpapi:" + base64.b64encode(_dpapi(text.encode("utf-8"), False)).decode("ascii")
    return "env"


def unprotect(value: str) -> str:
    if not value:
        return ""
    if value.startswith("dpapi:") and _IS_WIN:
        return _dpapi(base64.b64decode(value[6:]), True).decode("utf-8")
    if value == "env":
        return os.environ.get("AIKLIPYT_API_KEY", "")
    return ""


def api_key(config: dict) -> str:
    return unprotect(config.get("ai", {}).get("apiKeyEnc", ""))
