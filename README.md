# AIKLIPYT

<p align="center">
  <img src="web/assets/logo.png" alt="Logo AIKLIPYT" width="112">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/versi-v1.0.5-blue" alt="Versi v1.0.5">
  <img src="https://img.shields.io/badge/lisensi-MIT-green" alt="Lisensi MIT">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/tests-92%20passing-brightgreen" alt="92 test lulus">
</p>

**Studio klip YouTube yang berjalan di komputermu sendiri.** Tempel URL, biarkan AI
memilih momen terbaik, lalu ffmpeg merender klip vertikal 9:16 dengan caption per
kata, hook, dan watermark. Tanpa akun, tanpa telemetri, dan video tidak pernah
diunggah ke server mana pun.

Ditulis ulang dari nol berdasarkan perilaku yang diamati dari **YT Short Clipper v2**
(v2.0.7-beta) lewat analisis REA. Ini **bukan salinan** kode atau aset aplikasi asli —
yang sama hanya alur kerjanya; implementasinya bersih dan terbuka.

**Rilis terbaru:** [v1.0.5](https://github.com/nuellpr/AIKLIPYT/releases/tag/v1.0.5)
· [Riwayat perubahan](CHANGELOG.md) · [Lisensi MIT](LICENSE) · [Kebijakan Keamanan](SECURITY.md)

## Daftar isi

- [Kenapa Python, bukan Tauri?](#kenapa-python-bukan-tauri)
- [Fitur](#fitur)
- [Kebutuhan](#kebutuhan)
- [Mulai cepat](#mulai-cepat)
- [Gaya subtitle](#gaya-subtitle)
- [Skor highlight](#skor-highlight)
- [Struktur proyek](#struktur-proyek)
- [Pengujian](#pengujian)
- [Rilis](#rilis)
- [Troubleshooting](#troubleshooting)
- [Keamanan](#keamanan)
- [Perbedaan dengan aplikasi asli](#perbedaan-dengan-aplikasi-asli)
- [Batasan yang jujur](#batasan-yang-jujur)

## Kenapa Python, bukan Tauri?

Mesin ini tidak punya Rust/cargo, jadi build Tauri mustahil tanpa menambah toolchain
~1 GB. Versi ini memakai Python + Web UI lokal: fungsi inti sama, tanpa build step,
dan mudah diubah. UI berjalan di browser pada `http://127.0.0.1:8765`.

## Fitur

- Cari highlight dari transkrip YouTube (manual atau auto-generated).
- AI OpenAI-compatible: OpenAI, Groq, Gemini, OpenRouter, vLLM lokal, dan lain-lain.
  Tombol **Muat model** mengisi dropdown; pilih **Custom** untuk mengetik nama model.
- Klip 9:16 dengan latar hitam atau blur; opsi 16:9 dan durasi 5–600 detik.
- **14 gaya subtitle** dan **10 gaya Judul pembuka (Hook)** dengan kartu preview beranimasi di Pengaturan — lihat [Gaya subtitle](#gaya-subtitle).
- **Live preview 9:16 / 16:9** saat menempel link YouTube: langsung menampilkan thumbnail video, latar hitam/blur, hook, dan simulasi subtitle sesuai Pengaturan.
- Pilihan **13 font subtitle** dan opsi **Huruf subtitle tebal (Bold)** di Pengaturan.
- Warna aksen caption dan hook yang bisa diatur; teks kredit, dan watermark PNG/JPG dengan 9 posisi serta transparansi yang bisa di-preview.
- Encoder hardware (NVENC/QSV/AMF) dipilih lewat uji encode nyata, lalu fallback otomatis ke libx264. Encoder tanpa GPU/driver tidak akan dicoba.
- Pustaka sesi lokal: preview klip, muat ulang highlight ke tab Buat, buka folder, hapus.
- Cookies YouTube **opsional** dan difilter: domain lain dibuang; dari google.com
  hanya cookie login YouTube yang disimpan.
- API key dienkripsi DPAPI Windows (hanya bisa dibaca user yang sama).
- Tanpa akun, tanpa telemetri, tanpa panggilan ke server AIKLIPYT.

## Kebutuhan

- Windows 10/11, Python 3.11+ (dites di 3.14.6).
- **ffmpeg** — sudah disertakan di paket ZIP rilis pada `assets\ffmpeg\ffmpeg.exe`.
  Kalau memakai source dari Git, taruh `ffmpeg.exe` di folder itu atau pasang ffmpeg
  dan pastikan ada di `PATH`.
- **deno** (disertakan di ZIP, opsional tetapi disarankan) — membantu yt-dlp melewati
  tantangan JS YouTube. Letakkan di `bin\deno.exe` atau `PATH`.
- Koneksi internet saat pertama kali menjalankan `run.bat` untuk mengunduh yt-dlp
  ke `.venv`.

Ekstrak ZIP ke folder biasa (misalnya `Dokumen\AIKLIPYT`), **bukan** ke `Program
Files`, supaya `.venv` dan `data\` bisa ditulis. Semua path bersifat relatif terhadap
folder hasil ekstrak.

## Mulai cepat

1. Unduh ZIP Windows dari [halaman Releases](https://github.com/nuellpr/AIKLIPYT/releases),
   lalu ekstrak. ZIP sudah berisi `ffmpeg.exe` dan `deno.exe`.
2. Klik dua kali `run.bat`. Pertama kali akan membuat `.venv` dan meng-install yt-dlp.
3. Buka **Pengaturan** → pilih Provider (Gemini, OpenAI, Groq, OpenRouter, vLLM lokal,
   atau **Custom**), lalu isi API key dan model. Contoh: `https://api.openai.com/v1`
   + `gpt-4.1-mini`. Untuk Google, pilih preset Gemini (endpoint OpenAI-compatible AI
   Studio) dan pakai key dari AI Studio.
4. (Opsional) **Cookies**: ekspor cookies khusus `youtube.com` dengan ekstensi
   "Get cookies.txt LOCALLY", tempel, simpan. Tanpa cookies, video publik biasanya
   tetap jalan.
5. Tab **Buat** → tempel URL → **Cari highlight**.
6. Pilih klip → atur gaya subtitle → **Render klip** → lihat hasilnya di **Pustaka**.

Semua data ada di `data/`:

```
data/
  config.json          # setelan (API key terenkripsi)
  cookies.txt          # cookies YouTube terfilter
  sessions/<id>/       # session.json, words.json, transcript.txt
  outputs/<id>/        # clip_01.mp4, clip_01.ass, clips.json
  watermarks/          # gambar watermark hasil unggahan
  tmp/                 # file sementara, dibersihkan otomatis
```

## Gaya subtitle

Pilih gaya di **Pengaturan → Klip → Gaya caption**. Semua gaya memakai timing kata
asli dan warna aksen yang sama.

### Dasar dan Wayin

| Gaya | Tampilan |
|---|---|
| `highlight` | Kata aktif berwarna aksen, kata lain putih |
| `box` | Kata aktif hitam dengan garis tebal warna aksen |
| `pop` | Kata aktif berwarna aksen dan sedikit membesar |
| `smart-bg-focus` | Kotak gelap di belakang teks, kata aktif berwarna aksen |
| `box-highlight` | Hanya kata aktif, dalam kotak warna aksen |
| `word-focus` | Kata lain meredup, kata aktif berwarna aksen dan membesar |
| `underline-focus` | Teks kapital, kata aktif bergaris bawah warna aksen |
| `outline-focus` | Teks outline, kata aktif terisi warna aksen |
| `temp-0` | Huruf kapital, teks putih outline hitam, kata aktif terisi aksen |

Enam gaya terakhir diadaptasi dari referensi gaya subtitle
[Wayin](https://wayin.ai/id/api-docs/subtitles-style/). Karena dirender lewat
ASS/libass, hasilnya mendekati preview web, bukan identik.

### Gaya kreator

| Gaya | Tampilan |
|---|---|
| `hormozi` | Huruf kapital tebal, outline hitam tebal, kata aktif membesar dengan aksen |
| `karaoke` | Fill-sweep per kata ala karaoke klasik, satu baris per grup kata |
| `gadzhi` | Arial tipis putih, outline 1 px, tanpa animasi — minimalis |
| `mrbeast` | Palet warna cerah berputar, kata aktif membesar, outline putih tebal |
| `bilingual` | Dua lapis: teks asli + terjemahan AI di atasnya |

**Bilingual** memakai penyedia AI yang sudah terhubung di Pengaturan. Bahasa tujuan
diambil dari **Bahasa output** (default `auto` → Inggris); tanpa pengaturan ini,
terjemahan tidak akan benar. Jika panggilan AI gagal, AIKLIPYT tetap merender subtitle
satu lapis dan mencatatnya di log job — render tidak dibatalkan.

Warna aksen diatur di **Pengaturan → Klip → Warna caption** (default kuning `#FFD700`).
Hook memakai warna yang sama.

## Skor highlight

**Skor viralitas adalah perkiraan AI, bukan hasil pengukuran.** Model menilai empat
dimensi 1–10: **hook** (35%), **emosi** (25%), **kejelasan sebagai klip mandiri** (20%),
dan **potensi loop/replay** (20%). Skor akhir adalah rata-rata berbobot, lalu UI
memberi label **Sangat kuat** (8.5+), **Kuat** (7–8.4), **Cukup** (5.5–6.9), atau
**Lemah** (<5.5). `score_reason` menjelaskan dimensi terkuat dan terlemah.

Highlight diurutkan dari skor tertinggi, dan tombol **Pilih skor ≥ 7** memilih klip
yang layak dirender. Skor tinggi tetap belum tentu performanya tinggi di
YouTube/TikTok.

AI diminta mengembalikan **tepat** sejumlah klip yang diminta. Kalau hasilnya kurang,
AIKLIPYT meminta tambahan hingga dua kali dengan rentang klip yang sudah dipilih
dikecualikan. Kalau masih kurang, UI menampilkan peringatan "AI hanya menemukan X
dari Y momen".

## Struktur proyek

```
AIKLIPYT/
  run.bat              # launcher + bootstrap venv
  server.py            # HTTP server 127.0.0.1 + API
  core/
    config.py          # setelan & path portable
    secret.py          # DPAPI
    assets.py          # cari ffmpeg/deno
    cookies.py         # filter cookies YouTube
    models.py          # daftar model dari provider AI
    ytdlp.py           # info, subtitle, download section
    subtitles.py       # SRT/VTT/json3 → word timing
    highlights.py      # prompt, panggilan AI, terjemahan, validasi JSON
    render.py          # ASS caption (14 gaya), reframe, encode
    session.py         # penyimpanan sesi
    pipeline.py        # job background
  web/                 # UI (HTML/CSS/JS, tanpa build step)
    assets/logo.svg    # brand mark (favicon + sidebar)
    assets/logo.png    # fallback raster 640px
  tests/               # unittest
  docs/superpowers/    # spec & rencana fitur subtitle
```

## Pengujian

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Saat ini **92 test** lulus. Test render memakai ffmpeg untuk membuat video sintetis
dan memverifikasi output 1080x1920, termasuk 14 gaya subtitle, 10 gaya hook, pilihan font/bold,
dan validasi keamanan server. Test DPAPI hanya berjalan di Windows.

## Rilis

| Versi | Tanggal | Catatan |
|---|---|---|
| [v1.0.5](https://github.com/nuellpr/AIKLIPYT/releases/tag/v1.0.5) | 2026-11-21 | 10 gaya hook, carousel kartu beranimasi, live preview thumbnail YouTube, perbaikan tumpang tindih subtitle & pengerasan keamanan, LICENSE MIT & SECURITY.md |
| [v1.0.4](https://github.com/nuellpr/AIKLIPYT/releases/tag/v1.0.4) | 2026-11-19 | Pilihan font subtitle & toggle Bold, perbaikan lookup `assets/ffmpeg`, render ASS & UI |
| [v1.0.3](https://github.com/nuellpr/AIKLIPYT/releases/tag/v1.0.3) | 2026-11-17 | 5 gaya subtitle kreator, bilingual, pengerasan API & media |
| [v1.0.2](https://github.com/nuellpr/AIKLIPYT/releases/tag/v1.0.2) | 2026-11-14 | Watermark & kredit, jumlah klip tepat |
| [v1.0.1](https://github.com/nuellpr/AIKLIPYT/releases/tag/v1.0.1) | 2026-11-13 | 6 gaya Wayin, halaman Tentang, logo |
| [v1.0.0](https://github.com/nuellpr/AIKLIPYT/releases/tag/v1.0.0) | 2026-11-13 | Rilis pertama |

Detail lengkap ada di [CHANGELOG.md](CHANGELOG.md).

## Troubleshooting

- **"ffmpeg tidak ditemukan"** — taruh `ffmpeg.exe` di `assets\ffmpeg\` atau isi path
  absolut di Pengaturan.
- **HTTP 403 / "Sign in to confirm you're not a bot"** — cookies hilang atau
  kedaluwarsa. Ekspor ulang cookies YouTube, lalu simpan.
- **"Video ini tidak punya subtitle"** — pilih video dengan caption, atau aktifkan
  auto-caption di YouTube.
- **AI error 401/404** — cek base URL (harus berakhiran `/v1` untuk OpenAI), API key,
  dan nama model.
- **Terjemahan bilingual tidak muncul** — cek koneksi AI dan Bahasa output di
  Pengaturan; tanpa itu subtitle tetap tampil satu lapis.
- **Log menyebut `h264_nvenc failed` / `libx264`** — GPU NVIDIA tidak ada atau driver
  belum terpasang. AIKLIPYT menguji encoder sebelum memakainya; mesin Intel akan
  memakai QSV, mesin tanpa GPU memakai libx264. Tidak perlu mengubah pengaturan.
- **Port dipakai** — server otomatis mencoba port berikutnya; lihat URL di konsol.

## Keamanan & Lisensi

Detail kebijakan keamanan, pelaporan kerentanan, dan praktik aman ada di [SECURITY.md](SECURITY.md).

File `cookies.txt` adalah kredensial hidup. Jangan dibagikan. Kalau pernah mengekspor
seluruh cookie browser (bukan hanya YouTube), hapus file aslinya dan logout/rotasi
sesi Google. AIKLIPYT hanya menyimpan cookie YouTube setelah difilter, tapi tetap
perlakukan `data\cookies.txt` seperti password.

API key disimpan terenkripsi DPAPI, tetapi tetap bisa dibaca oleh proses yang berjalan
sebagai user Windows yang sama. Gunakan key khusus dengan limit. Kunci tidak ikut
terkirim jika penyedia AI mengalihkan permintaan ke alamat lain.

Kode sumber AIKLIPYT dirilis di bawah lisensi [MIT](LICENSE). Paket rilis Windows
menyertakan biner pihak ketiga (FFmpeg GPL-3.0 dan Deno MIT) — lihat [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Perbedaan dengan aplikasi asli

| Aspek | Asli | AIKLIPYT |
|---|---|---|
| Shell | Tauri + React | Web UI lokal (Python stdlib) |
| AI | Akun in-app + LiteLLM proxy + topup QRIS | API key sendiri, OpenAI-compatible |
| Telemetri | GA4 measurement protocol | Tidak ada |
| Cookies | Wajib, bisa seluruh browser | Opsional, difilter YouTube |
| API key | Windows Credential Manager | DPAPI (config terenkripsi) |
| Face tracking | MediaPipe face landmarker | Belum; center crop / blur |
| Upload Repliz | Ada | Tidak ada |
| Auto-update | Cek server + download | Tidak ada |
| Durasi klip | 58–120 detik | Bisa diatur 5–600 detik |
| Gaya subtitle | — | 14 gaya, termasuk bilingual |
| Tests | Tidak diketahui | 78 unit/integration test |

## Batasan yang jujur

- **Butuh subtitle.** Kalau video tidak punya caption sama sekali, app berhenti dengan
  pesan jelas. Tidak ada fallback Whisper.
- **Belum ada face tracking.** Reframe vertikal memakai center crop (hitam atau blur).
  Untuk konten yang wajahnya selalu di tengah, hasilnya sudah layak.
- **Tidak ada Repliz / penjadwalan sosmed / billing.** Fokus versi ini: menghasilkan
  file MP4.
- **Caption manual bersifat perkiraan.** Word timing asli hanya tersedia di track auto
  `*-orig`; SRT manual dibagi proporsional per karakter.
- **UI belum punya pemilih track subtitle manual per bahasa.** Otomatis: bahasa yang
  diminta → track original → en → track pertama.
- **Hasil gaya subtitle mendekati, bukan identik** dengan preview web referensi,
  karena dirender lewat ASS/libass.
- **Tidak ada code signing.** Windows SmartScreen bisa muncul; ini normal untuk
  aplikasi lokal yang belum ditandatangani.
- Semua proses berjalan lokal; kualitas highlight sangat tergantung model AI.

---

AIKLIPYT v1.0.5 · MIT · lokal, tanpa telemetri.
