# Design: Optimasi Kecepatan Render & Preview Pra-Render (Pendekatan B)

Tanggal: 2026-11-26

## Intent / why

Pengguna menjalankan AIKLIPYT pada mesin Intel Core i5-6300U (2 core / 4 thread) + Intel HD Graphics 520 (`h264_qsv`) dengan mode default aktif `fill` (Layar Penuh). Waktu tunggu render menjadi hambatan terbesar karena:
1. `download_section()` meminta sumber `2160p` (VP9/AV1) dan memakai `--force-keyframes-at-cuts`, yang memaksa `yt-dlp` melakukan *re-encode* CPU penuh (`libx264 medium`) sebelum `render_clip()` melakukan encode kedua.
2. `render_clip()` memproses seluruh 60fps tanpa batas `fps=30`, menggunakan `flags=lanczos` + `unsharp`, dan menjalankan `h264_qsv` tanpa `-preset veryfast` (terukur 2,1x lebih lambat pada benchmark lokal).
3. Unduhan klip berikutnya menunggu encode klip saat ini selesai (tidak ada *prefetch* 1 klip).
4. Pengguna belum bisa memutar pratinjau rentang detik `start`–`end` langsung dari YouTube sebelum menekan tombol **Render klip**.

## Goals

- Menghilangkan *double-encode* pada tahap unduh potongan (`-c copy` dengan dukungan *MP4 edit-list* FFmpeg + batas `-t duration` saat render) dan memakai sumber `1080p avc1` H.264 secara default agar ramah dekoder hardware.
- Mempercepat tahap encode ~2x lewat pembatasan `fps=30`, penskalaan `bicubic`, dan `-preset veryfast` pada `h264_qsv`.
- Melakukan *prefetch* unduhan klip `N+1` di latar belakang saat klip `N` sedang dianalisis/dirender (maksimal 1 unduhan paralel), tetap patuh pada pembatalan job (`cancel_event`).
- Menyediakan tombol **Putar sampel** di tiap kartu highlight untuk memutar rentang `Mulai`–`Selesai` lewat iframe `youtube-nocookie.com` sebelum render.

## Non-goals & Anti-goals

- Tidak menjalankan 2+ proses encode FFmpeg secara bersamaan (anti-goal: membuat CPU 2-core dan iGPU mengalami *throttling*).
- Tidak menambah dependensi Python baru.

## Constraints

- Seluruh 143 pengujian yang sudah ada tetap harus hijau (atau diperbarui sesuai kontrak baru seperti penghapusan `--force-keyframes-at-cuts` dan rantai filter `fill`).
- CSP di `server.py` hanya membuka `frame-src https://www.youtube-nocookie.com https://www.youtube.com` khusus untuk pratinjau embed, tanpa melonggarkan `script-src 'self'`.

## Approaches

- **A — Tuning Argumen FFmpeg Saja:** Menurunkan ke `1080p`, `fps=30`, dan `-preset veryfast`, namun tetap memakai `--force-keyframes-at-cuts` dan antrean sekuensial. Ditolak karena *double-encode* di `yt-dlp` masih memakan waktu paling lama.
- **B (Dipilih) — *Zero-Reencode Download* + *Fast QSV 30fps* + *1-Ahead Prefetch* + *Pre-Render Embed Preview*:** Menyelesaikan keempat titik lambat sekaligus tanpa membebani CPU 2-core.
- **C — Multi-FFmpeg Paralel:** Ditolak karena kontraproduktif pada prosesor dual-core + iGPU.

## Design (keputusan implementasi)

1. `core/ytdlp.py`:
   - Hapus `--force-keyframes-at-cuts` di `download_section()` sehingga `yt-dlp` memotong stream memakai `-c copy` (*MP4 edit-list* menjaga akurasi frame awal).
   - Default `max_height=1080` memilih `avc1` + `mp4a` lebih dulu; di `core/pipeline.py`, mode `fill` juga memakai `1080` secara default agar tidak menarik stream 4K VP9/AV1 di CPU ringan.
2. `core/render.py`:
   - Tambahkan `-preset veryfast` pada `_HW_ENCODERS` untuk `h264_qsv`.
   - Batasi frame rate output maksimal 30fps (`fps='min(30,source_fps)'` atau `-r 30` / filter `fps=fps='min(source_fps,30)'` — paling aman & kompatibel di semua versi FFmpeg: `-fps_mode cfr -r 30` pada argumen output atau filter `fps=30` di awal/akhir `[v]`) serta ganti `flags=lanczos` + `unsharp` menjadi `flags=bicubic` yang tajam namun 2x lebih cepat.
   - Tambahkan `-t {duration:.3f}` pada `base_cmd` agar durasi akhir selalu presisi walau kontainer sumber bukan MP4.
3. `core/pipeline.py`:
   - Di `_render_worker`, jalankan `ThreadPoolExecutor(max_workers=1)` untuk mengunduh klip berikutnya (`N+1`) sementara klip `N` sedang melalui `analyze_reframe()` + `render_clip()`, dengan pembatalan bersih melalui `cancel_event`.
4. `server.py` & `web/` (`index.html`, `app.js`, `styles.css`):
   - Perbarui `Content-Security-Policy` di `server.py` dari `frame-ancestors 'none'` tetap terjaga dan tambahkan `frame-src https://www.youtube-nocookie.com https://www.youtube.com;`.
   - Tambahkan tombol **Putar sampel** (`data-preview-clip`) pada kartu highlight yang memuat iframe embed `https://www.youtube-nocookie.com/embed/<videoId>?start=<int>&end=<int>&autoplay=1&rel=0` di panel preview ponsel (lengkap dengan tombol **Tutup sampel** untuk kembali ke simulasi subtitle/hook).
