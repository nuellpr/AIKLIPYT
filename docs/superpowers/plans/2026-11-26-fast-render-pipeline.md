# Optimasi Kecepatan Render & Preview Pra-Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Memangkas waktu tunggu render klip secara drastis di perangkat dual-core + Intel QSV lewat pemotongan `-c copy` tanpa *double-encode*, batas `30fps` + `bicubic` + `h264_qsv -preset veryfast`, *prefetch* unduhan 1 klip ke depan, serta tombol **Putar sampel** pra-render.

**Architecture:** `download_section` di `core/ytdlp.py` mengunduh stream `1080p avc1` dengan `-c copy` (mengandalkan *MP4 edit-list* FFmpeg + penjaga `-t duration` di `core/render.py`). `_render_worker` di `core/pipeline.py` memakai `ThreadPoolExecutor(max_workers=1)` untuk mengunduh klip `N+1` selagi klip `N` dirender, sementara UI `web/` menyediakan pratinjau iframe `youtube-nocookie.com` untuk mengecek batas waktu sebelum render.

**Tech Stack:** Python 3.11+ stdlib (`concurrent.futures`, `subprocess`, `threading`), FFmpeg 8 (`h264_qsv`/`libx264`), `yt-dlp`, Vanilla HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-11-26-fast-render-pipeline-design.md`

## Global Constraints

- Nol dependensi Python baru.
- Maksimal 1 proses encode FFmpeg dan maksimal 1 unduhan *prefetch* di latar belakang pada satu waktu.
- CSP tetap menjaga `script-src 'self'` dan `frame-ancestors 'none'`, hanya membuka `frame-src https://www.youtube-nocookie.com https://www.youtube.com`.

## Review Focus

- Pembatalan job (`pipeline.cancel`) saat klip `N` sedang dirender FFmpeg dan klip `N+1` sedang di-*prefetch* `yt-dlp` harus menghentikan **kedua** proses anak sekaligus tanpa error penghapusan `workdir`.
- Kegagalan unduhan pada task *prefetch* klip `N+1` tidak boleh menggagalkan klip `N` yang sedang dirender dan harus tercatat rapi pada daftar `errors` klip `N+1`.
- Pemutaran iframe sampel YouTube harus berhenti (mengosongkan `src`) saat ditutup, saat berpindah tab, atau saat memulai job baru agar suara tidak bocor di latar belakang.
- Video sumber ber-framerate rendah (mis. 24fps) tidak boleh diduplikasi paksa menjadi 30fps (`fps='min(30,source_fps)'`), sementara 60fps diturunkan ke 30fps.

---

### Task 1: Zero-Reencode Download (`-c copy`) & Default 1080p H.264

**Files:**
- Modify: `core/ytdlp.py:196-235`
- Modify: `core/pipeline.py:375-395`
- Test: `tests/test_ytdlp.py`

- [ ] **Step 1: Tulis tes gagal** yang memastikan `--force-keyframes-at-cuts` tidak lagi dikirim oleh `download_section`.
- [ ] **Step 2: Jalankan tes (RED)** — gagal karena `--force-keyframes-at-cuts` masih ada.
- [ ] **Step 3: Implementasi** penghapusan `--force-keyframes-at-cuts` di `core/ytdlp.py` dan penggunaan `max_height=1080` default pada `core/pipeline.py`.
- [ ] **Step 4: Jalankan tes (GREEN)**.

### Task 2: Fast FFmpeg Render (`min(30,source_fps)`, `bicubic`, `h264_qsv -preset veryfast`, `-t duration`)

**Files:**
- Modify: `core/render.py:480-810`
- Test: `tests/test_render.py`, `tests/test_reframe.py`

- [ ] **Step 1: Tulis tes gagal** untuk `fps=fps='min(30,source_fps)'`, `flags=bicubic` (tanpa `unsharp`), `-preset veryfast` pada `h264_qsv`, dan batas `-t` durasi pada perintah FFmpeg, serta verifikasi render nyata 60fps menghasilkan <=30fps.
- [ ] **Step 2: Jalankan tes (RED)**.
- [ ] **Step 3: Implementasi** perubahan di `core/render.py`.
- [ ] **Step 4: Jalankan tes (GREEN)**.

### Task 3: Background Prefetch Klip `N+1` & Multi-Process Cancel

**Files:**
- Modify: `core/pipeline.py:100-165, 340-495`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Tulis tes gagal** yang membuktikan unduhan klip ke-2 berjalan tumpang tindih selama `render_clip` klip ke-1 berlangsung, dan pembatalan memanggil semua *killer* aktif.
- [ ] **Step 2: Jalankan tes (RED)**.
- [ ] **Step 3: Implementasi** himpunan *killer* per job dan `ThreadPoolExecutor(max_workers=1)` untuk *prefetch* di `_render_worker`.
- [ ] **Step 4: Jalankan tes (GREEN)**.

### Task 4: Tombol Putar Sampel YouTube Pra-Render

**Files:**
- Modify: `server.py:258-266`
- Modify: `web/index.html:160-185`
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Test: `tests/test_server.py`

- [ ] **Step 1: Tulis tes gagal** untuk header CSP `frame-src https://www.youtube-nocookie.com` dan elemen UI `#previewEmbed`, `#closeEmbedBtn`, serta `data-preview-clip`.
- [ ] **Step 2: Jalankan tes (RED)**.
- [ ] **Step 3: Implementasi** CSP dan fitur putar/tutup sampel YouTube di `web/`.
- [ ] **Step 4: Jalankan seluruh suite tes & verifikasi di Playwright (GREEN)**.
