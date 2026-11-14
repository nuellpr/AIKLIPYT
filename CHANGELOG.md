# Changelog

Semua perubahan penting pada AIKLIPYT.

## [1.0.2] - 2026-11-14

### Added
- Pemilih file watermark PNG/JPG dengan upload ke `data/watermarks`, 9 posisi
  watermark, preview 9:16, dan 9 posisi teks kredit.
- Slider transparansi watermark dan teks kredit (0-100%) dengan preview langsung.
- AI diminta mengembalikan jumlah klip yang tepat; hingga 2 panggilan tambahan
  untuk melengkapi klip yang kurang, dengan peringatan jika tetap kurang.

### Fixed
- Preview watermark gagal dibaca karena CSP memblokir URL `blob:`; `img-src`
  sekarang mengizinkan `blob:`.
- Traceback WinError 10053/10054 saat browser menutup atau seek video tidak lagi
  ditampilkan.

### Changed
- Rilis Windows menyertakan ffmpeg 8.0.1 dan deno 2.8.1 beserta lisensi pihak
  ketiga.

## [1.0.1] - 2026-11-13

### Added
- Enam gaya caption ala Wayin: `smart-bg-focus`, `box-highlight`, `word-focus`, `underline-focus`, `outline-focus`, dan `temp-0` (total 9 gaya caption).
- Halaman **Tentang** dengan logo, deskripsi, metadata, dan tautan GitHub/rilis/Figma.
- Logo aplikasi di README, sidebar, dan favicon.

### Changed
- Paket rilis Windows menyertakan ffmpeg 8.0.1 dan deno 2.8.1, plus `THIRD_PARTY_NOTICES.md` dan lisensi.
- README kini portabel (tanpa path lokal) dan menjelaskan paket ZIP.

### Fixed
- Skor highlight memakai empat dimensi berbobot dan menampilkan alasan; tersedia `Pilih skor >= 7`.
- Pemilihan encoder hardware memakai probe encode nyata (NVENC/QSV/AMF) sebelum fallback libx264.

## [1.0.0] - 2026-11-13

Rilis pertama AIKLIPYT: studio klip YouTube lokal dengan AI highlight, caption
karaoke, dan render vertikal 9:16.

### Ditambahkan

- Pipeline dua fase: unduh subtitle, pilih highlight dengan AI, lalu unduh
  bagian video dan render klip.
- UI lokal dengan tab **Buat**, **Pustaka**, dan **Pengaturan**.
- Dukungan provider OpenAI-compatible: OpenAI, Groq, Gemini, OpenRouter, vLLM
  lokal, dan base URL custom.
- Pemilih model dari endpoint `/models` dengan opsi model custom.
- Tiga gaya caption karaoke: **Highlight kata**, **Kotak tebal**, dan
  **Pop membesar**, plus warna aksen caption yang bisa diatur.
- Skor kualitas highlight dari empat dimensi berbobot: hook 35%, emosi 25%,
  kejelasan 20%, dan potensi loop 20%. UI menampilkan alasan skor, urutan
  terbaik, dan tombol **Pilih skor ≥ 7**.
- Reframe vertikal 9:16 dengan latar hitam atau blur, opsi output 16:9.
- Hook di awal klip, teks kredit, dan watermark PNG/JPG.
- Deteksi encoder hardware dengan uji encode nyata: NVENC, QSV, AMF, lalu
  fallback libx264.
- Cookies YouTube opsional yang difilter hanya untuk domain YouTube.
- API key disimpan terenkripsi DPAPI Windows.
- Logo dan favicon AIKLIPYT (play mark + spark AI).

### Diperbaiki

- nvenc tidak lagi dicoba di mesin tanpa GPU NVIDIA; aplikasi memilih encoder
  yang benar-benar bisa dipakai.
- Request POST dari UI tidak lagi ditolak 403 karena validasi Origin.
- Tombol tidak lagi terkunci ketika job highlight/render gagal.
- Encoder hardware yang gagal tidak diulang untuk setiap klip.
- Pemilih model tidak lagi bergantung pada datalist yang sulit dibuka.

### Keamanan

- Tanpa akun, telemetri, atau panggilan ke server AIKLIPYT.
- Server hanya mendengarkan di `127.0.0.1`.
- Filter cookies membuang domain non-YouTube dan cookie Google non-autentikasi.
- Data lokal (`data/`) dan virtualenv tidak disertakan di repository.

### Batasan

- Video harus memiliki subtitle/caption; belum ada fallback Whisper.
- Belum ada face tracking; reframe memakai center crop.
- Belum ada upload Repliz, penjadwalan sosial media, atau billing.
- Skor highlight adalah estimasi AI, bukan prediksi performa nyata.
