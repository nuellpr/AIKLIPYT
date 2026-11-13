"""Cookie import that refuses to keep the whole browser's cookie jar.

Only youtube.com/youtu.be cookies are kept. From google.com only the cookie
names YouTube actually needs are kept, so exporting "youtube.com" in a cookie
extension cannot leak Gmail/Drive sessions into the app.
"""
from __future__ import annotations

import time
from pathlib import Path

YOUTUBE_DOMAINS = ("youtube.com", "youtu.be")
GOOGLE_AUTH_COOKIES = {
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "LOGIN_INFO",
    "PREF",
    "YSC",
    "VISITOR_INFO1_LIVE",
    "VISITOR_PRIVACY_METADATA",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
}
HEADER = "# Netscape HTTP Cookie File"


def filter_cookies(text: str) -> tuple[str, dict]:
    kept: list[str] = []
    skipped = 0
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            skipped += 1
            continue
        domain = parts[0].lstrip(".").lower()
        name = parts[5]
        if any(domain == suffix or domain.endswith("." + suffix) for suffix in YOUTUBE_DOMAINS):
            kept.append("\t".join(parts))
        elif domain == "google.com" or domain.endswith(".google.com"):
            if name in GOOGLE_AUTH_COOKIES:
                kept.append("\t".join(parts))
            else:
                skipped += 1
        else:
            skipped += 1
    header = HEADER + "\n"
    body = "\n".join(kept)
    has_auth = False
    for line in kept:
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] in {"SID", "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"}:
            has_auth = True
            break
    return header + (body + "\n" if body else ""), {
        "kept": len(kept),
        "skipped": skipped,
        "hasAuth": has_auth,
    }


def save(path: Path, text: str) -> dict:
    filtered, stats = filter_cookies(text)
    if stats["kept"] == 0:
        raise ValueError("No YouTube cookies found. Export cookies for youtube.com, not the whole browser.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(filtered, encoding="utf-8")
    return stats


def status(path: Path) -> dict:
    if not path.is_file():
        return {"saved": False, "count": 0, "hasAuth": False, "updatedAt": 0}
    try:
        lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line and not line.startswith("#")]
    except OSError:
        lines = []
    has_auth = any(
        len(line.split("\t")) >= 7
        and line.split("\t")[5] in {"SID", "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"}
        for line in lines
    )
    return {
        "saved": True,
        "count": len(lines),
        "hasAuth": has_auth,
        "updatedAt": int(path.stat().st_mtime),
        "ageHours": round((time.time() - path.stat().st_mtime) / 3600, 1),
    }


def remove(path: Path) -> None:
    if path.is_file():
        path.unlink()
