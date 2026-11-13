# Changelog

Semua perubahan penting pada AIKLIPYT.

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
