# Kebijakan Keamanan (Security Policy)

## Versi yang Didukung

Pembaruan keamanan hanya diberikan untuk rilis minor/patch terbaru.

| Versi | Didukung |
|---|---|
| `1.0.6` | Ya |
| `< 1.0.6` | Tidak — silakan perbarui ke versi terbaru |

## Model Keamanan AIKLIPYT

AIKLIPYT dirancang berjalan **100% lokal** di mesin pengguna:

- **Loopback-only server:** Server HTTP hanya mendengarkan pada `127.0.0.1` dan memvalidasi header `Host` serta `Origin` secara ketat (semua `POST` lintas-origin ditolak dengan `403`).
- **Header keamanan HTTP:** `Content-Security-Policy` ketat (`script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin`, dan `Permissions-Policy`.
- **Proteksi API key:** Di Windows, API key dienkripsi memakai Windows DPAPI (per-user, per-machine). Kunci tidak ikut terkirim saat provider melakukan redirect HTTP (`3xx`), tidak dikirim ke base URL baru tanpa input ulang, dan dihapus dari environment subprocess `yt-dlp`.
- **Filter cookies YouTube:** Impor cookies membuang semua domain selain `youtube.com`/`youtu.be` dan hanya mempertahankan nama cookie login YouTube tertentu dari `google.com`. File disimpan secara atomik di `data/cookies.txt` (diabaikan oleh `.gitignore`).
- **Validasi URL & path:** Hanya URL `http://`/`https://` untuk endpoint AI dan domain YouTube untuk unduhan video; argumen `--` dipisahkan sebelum URL pada `yt-dlp`; ID sesi, nama file media, dan path statis divalidasi terhadap *path traversal*.
- **Tanpa telemetri:** Tidak ada akun, analitik, pelacakan, atau panggilan ke server milik AIKLIPYT.

## Praktik Aman untuk Pengguna

- **Perlakukan `data/cookies.txt` seperti password.** Jangan bagikan folder `data/`. Jika telanjur mengekspor seluruh cookie browser, hapus file mentahnya dan rotasi sesi Google kamu.
- **Gunakan API key khusus dengan batas pemakaian (*spending limit*)** — DPAPI melindungi dari pengguna/mesin lain, namun proses lain yang berjalan sebagai user Windows yang sama tetap dapat mendekripsinya.
- **Periksa path biner di Pengaturan:** Kolom path `ffmpeg` dan `deno` mengeksekusi biner lokal yang kamu tentukan; gunakan hanya biner dari sumber tepercaya.

## Melaporkan Kerentanan

Jika kamu menemukan celah keamanan, **jangan buat public Issue**. Laporkan secara privat melalui:

- **GitHub Security Advisories:** https://github.com/nuellpr/AIKLIPYT/security/advisories/new

Sertakan langkah reproduksi, dampak yang terlihat, dan versi AIKLIPYT yang digunakan. Laporan akan ditinjau secepat mungkin dan perbaikan akan dirilis bersama catatan keamanan di `CHANGELOG.md`.
