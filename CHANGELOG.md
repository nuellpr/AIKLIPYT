# Changelog

Semua perubahan penting pada AIKLIPYT.

## [1.0.5] - 2026-11-21

### Added
- **10 gaya Judul pembuka (Hook)** yang langsung dirender oleh FFmpeg/ASS: `classic` (Klasik), `card` (Kartu), `quote` (Kutipan), `accent-bar` (Bar Aksen), `cinema` (Sinema), `neon` (Neon Glow), `breaking` (Breaking News), `impact` (Impact Slam), `tape` (Stiker Miring), dan `spotlight` (Sorot).
- **Carousel kartu preview beranimasi** di Pengaturan → Klip, Subtitle & Hook untuk memilih ke-14 gaya subtitle dan ke-10 gaya hook secara visual, lengkap dengan panel **Warna & font** serta **Durasi**.
- **Live preview thumbnail YouTube 9:16 / 16:9** saat menempel URL di tab Buat, mengikuti latar hitam/blur, gaya subtitle, gaya hook, warna aksen, font, dan opsi Bold secara real-time.
- Tombol **Muat highlight** di detail sesi Pustaka untuk memuat ulang daftar highlight sesi lama ke tab Buat tanpa memanggil AI ulang.
- Berkas [LICENSE](LICENSE) (MIT) dan kebijakan keamanan [SECURITY.md](SECURITY.md).

### Security
- Memblokir skema non-`http://`/`https://` pada `core/highlights.py` (`chat()`) dan validasi `baseUrl` di `_apply_settings`.
- Menambahkan header keamanan `X-Frame-Options: DENY`, `Cross-Origin-Resource-Policy: same-origin`, dan `Permissions-Policy`.
- Memisahkan argumen `--` sebelum URL pada pemanggilan `yt-dlp` dan menyimpan `cookies.txt` secara atomik (dengan izin `0600` di POSIX).
- Memperketat `_apply_settings`: whitelist kunci dari `DEFAULTS`, menolak nilai `NaN`/`Infinity`, membatasi `hookSeconds` (`0.5–10` dtk), dan memvalidasi `background`.
- Penjaga sesi aktif (`409 Conflict`) mencegah render ganda dan penghapusan sesi saat render masih berjalan.

### Fixed
- Memotong tumpang tindih waktu kata di `normalize_words` dan akhir grup di `build_ass` agar subtitle tidak lagi menumpuk dan melompat vertikal saat transisi grup.
- Klip yang dimulai di detik `0` (`start_time: 0`) tidak lagi dibuang diam-diam.
- Setelan **Bahasa output default** di Pengaturan kini otomatis tersinkronisasi ke tab Buat saat mencari highlight.
- Parser `.vtt` kini membaca kata pertama sebelum tag `<timestamp>`, memproses cue 1-tag, dan fallback ke `words_from_cues` untuk subtitle `.vtt` manual.
- Gaya `mrbeast` memakai outline hitam pada kata non-aktif (tidak lagi putih di atas outline putih).
- Path relatif untuk watermark/input/output di-resolve absolut sebelum dikirim ke `ffmpeg`, dan `ffmpeg` diberi watchdog timeout agar tidak macet permanen.
- Pemilih subtitle kini mengenali kode wilayah manual (`en-US`, `pt-BR`, `zh-Hans`) dan menormalisasi `"auto"`.
- Render ulang klip yang sudah ada kini mengirim `overwrite: true`, label progres memakai `{urutan}/{total}`, polling job memakai `setTimeout` berantai, dan batas body dinaikkan ke 9 MB sambil mempertahankan format JPEG saat resize watermark.
- Animasi kartu preview tetap berjalan meski Windows mengaktifkan `prefers-reduced-motion`.

## [1.0.4] - 2026-11-19

### Added
- Pilihan **Font subtitle** (13 font bawaan Windows: Arial Black, Arial, Impact, Segoe UI, Bahnschrift, Verdana, Tahoma, Trebuchet MS, Calibri, Georgia, Times New Roman, Comic Sans MS, Consolas) di **Pengaturan → Klip**.
- Toggle **Huruf subtitle tebal (Bold)** untuk mengatur subtitle tebal atau normal.

### Fixed
- Pencarian `ffmpeg.exe` di `core/assets.py` kini mengecek `assets/ffmpeg/` sesuai struktur paket ZIP rilis sebelum fallback ke `ffmpeg/` dan `PATH`.
- Gaya subtitle `hormozi` dan `mrbeast` kini menerapkan outline tebal sejak kata aktif pertama, dan warna merah pada palet `mrbeast` menggunakan kode BGR ASS yang benar.
- File subtitle ASS ditulis per klip (`clip_01.ass`, dst.) alih-alih menimpa `captions.ass` yang sama.
- Transparansi watermark `0%` kini benar-benar melewati overlay watermark alih-alih di-clamp ke 5%.
- Sisa folder sementara di `data/tmp/` dari render yang terhenti dibersihkan otomatis saat server dinyalakan.
- Mode Bilingual tidak lagi memanggil API terjemahan saat caption dimatikan, dan mencatat alasan error terjemahan di log job.
- Fallback thumbnail di Pustaka tidak lagi memakai inline `onerror` yang diblokir CSP, dan class tombol watermark diperbaiki ke `.btn.ghost`.

## [1.0.3] - 2026-11-17

### Added
- Lima gaya subtitle baru: Hormozi (huruf besar tebal), Karaoke (highlight per kata), Iman Gadzhi (minimalis), MrBeast (warna cerah dinamis), dan Bilingual (dua lapis dengan terjemahan AI).
- Terjemahan Bilingual memakai penyedia AI yang sudah terhubung; bahasa tujuannya diatur lewat Bahasa output di Pengaturan.

### Security
- API key tidak lagi ikut terkirim saat penyedia AI mengalihkan permintaan ke alamat lain.
- Respons AI dibatasi 4 MB dan koneksi yang gagal ditutup dengan benar.

### Fixed
- Video bisa di-seek sampai ke ujung: rentang byte negatif kini mengambil bagian akhir, bukan awal file.
- Memulai job baru saat render masih berjalan tidak lagi menggagalkan job pertama.
- Download yang menggantung kini benar-benar berhenti sesuai batas waktunya.
- Klip setengah jadi tidak lagi dipakai ulang pada render berikutnya.
- Penanda waktu 59,999 detik tidak lagi tampil sebagai detik ke-60.
- Tombol tanpa ikon spinner kini tetap menampilkan status "Memproses…"; pilihan klip kembali sinkron setelah render.
- Dua impor berjudul sama dalam satu detik tidak lagi saling menimpa, dan subtitle lama tidak terseret ke unduhan berikutnya.
- Render tidak lagi memakai flag khusus Windows saat dijalankan di sistem lain.

### Changed
- Daftar gaya caption disatukan antara server dan antarmuka; sembilan gaya lama tetap berfungsi apa adanya.

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
