# AIKLIPYT

<p align="center">
  <img src="web/assets/logo.png" alt="Logo AIKLIPYT" width="112">
</p>

Reimplementasi fungsional dari **YT Short Clipper v2** (v2.0.7-beta): tempel URL
YouTube, AI memilih momen terbaik, lalu ffmpeg merender klip vertikal 9:16
dengan caption per kata, hook, dan watermark.

Aplikasi ini ditulis ulang dari nol berdasarkan perilaku yang diamati lewat
analisis REA. Ini **bukan salinan** kode/aset aplikasi asli: source asli tidak
tersedia, dan menyalin aset komersial bukan hal yang tepat. Yang sama adalah
alur kerjanya; implementasinya bersih dan terbuka.

Riwayat rilis ada di [CHANGELOG.md](CHANGELOG.md).

## Kenapa Python, bukan Tauri?

Mesin ini tidak punya Rust/cargo, jadi build Tauri tidak mungkin tanpa
menambah ~1 GB toolchain. Versi ini memakai Python + Web UI lokal: fungsi inti
sama, tanpa build, dan mudah diubah. UI berjalan di browser pada
`http://127.0.0.1:8765`.

## Fitur

- Cari highlight dari transkrip YouTube (manual atau auto-generated).
- AI OpenAI-compatible: OpenAI, Groq, Gemini, OpenRouter, vLLM lokal, dsb.
  Tombol **Muat model** mengisi dropdown model; pilih **Custom** untuk mengetik
  nama model manual.
- Klip 9:16 dengan latar hitam atau blur; opsi 16:9.
- Caption per kata dengan **warna aksen custom** dan 3 gaya karaoke:
  `Highlight kata`, `Kotak tebal`, `Pop membesar`. Hook memakai warna yang sama.
- Hook di awal klip, teks kredit, dan watermark PNG/JPG.
- Encoder hardware (NVENC/QSV/AMF) dipilih lewat uji encode nyata, lalu fallback
  otomatis ke libx264. Encoder yang tidak punya GPU/driver tidak akan dicoba.
- Pustaka sesi lokal: preview klip, buka folder, hapus.
- Cookies YouTube **opsional**, dan difilter: domain lain dibuang; dari
  google.com hanya cookie login YouTube yang disimpan.
- API key dienkripsi DPAPI Windows (hanya user yang sama).
- Tanpa akun, tanpa telemetri, tanpa panggilan ke server AIKLIPYT.

## Kebutuhan

- Windows 10/11, Python 3.11+ (dites di 3.14.6).
- **ffmpeg** — sudah disertakan di paket ZIP rilis pada `assets\ffmpeg\ffmpeg.exe`.
  Kalau memakai source dari Git, taruh `ffmpeg.exe` di folder itu atau install
  ffmpeg dan pastikan ada di `PATH`.
- **deno** (disertakan di ZIP, opsional tetapi disarankan) — membantu yt-dlp
  melewati tantangan JS YouTube. Letakkan di `bin\deno.exe` atau `PATH`.
- Koneksi internet saat pertama kali menjalankan `run.bat` untuk mengunduh
  yt-dlp ke `.venv`.

Ekstrak ZIP ke folder biasa (misalnya `Dokumen\AIKLIPYT`), bukan ke
`Program Files`, supaya `.venv` dan `data\` bisa ditulis. Semua path di app
bersifat relatif terhadap folder hasil ekstrak.

## Mulai

1. Unduh ZIP Windows dari halaman **Releases**
   ([github.com/nuellpr/AIKLIPYT/releases](https://github.com/nuellpr/AIKLIPYT/releases)),
   lalu ekstrak. ZIP sudah berisi `ffmpeg.exe` dan `deno.exe`.
2. Klik dua kali `run.bat`. Pertama kali akan membuat `.venv` dan meng-install
   yt-dlp.
3. Buka **Pengaturan** → pilih Provider (Google Gemini, OpenAI, Groq,
   OpenRouter, vLLM lokal, atau **Custom**), lalu isi API key dan model.
   Contoh: `https://api.openai.com/v1` + `gpt-4.1-mini`. Untuk Google, pilih
   preset Gemini (endpoint OpenAI-compatible AI Studio) dan pakai API key dari
   AI Studio.
4. (Opsional) **Cookies**: ekspor cookies khusus `youtube.com` dengan ekstensi
   "Get cookies.txt LOCALLY", tempel, simpan. Tanpa cookies, video publik
   biasanya tetap jalan.
5. Tab **Buat** → tempel URL → **Cari highlight**.
6. Pilih klip → **Render klip** → lihat di **Pustaka**.

Semua data ada di `data/`:

```
data/
  config.json          # setelan (API key terenkripsi)
  cookies.txt          # cookies YouTube terfilter
  sessions/<id>/       # session.json, words.json, transcript.txt
  outputs/<id>/        # clip_01.mp4, clips.json, captions.ass
  tmp/                 # file sementara, dibersihkan otomatis
```

## Skor dan caption

**Skor viralitas adalah perkiraan AI, bukan hasil pengukuran.** Model menilai
empat dimensi 1-10: **hook** (35%), **emosi** (25%), **kejelasan sebagai klip
mandiri** (20%), dan **potensi loop/replay** (20%). Skor akhir dihitung dari
rata-rata berbobot itu, lalu UI memberi label **Sangat kuat** (8.5+), **Kuat**
(7-8.4), **Cukup** (5.5-6.9), atau **Lemah** (<5.5). `score_reason` menjelaskan
dimensi terkuat dan terlemah. Highlight diurutkan dari skor tertinggi, dan tombol
**Pilih skor ≥ 7** memilih klip yang layak dirender. Skor tinggi tetap belum
tentu performanya tinggi di YouTube/TikTok.

AI diminta mengembalikan **tepat** sejumlah klip yang diminta. Kalau hasilnya
kurang, AIKLIPYT meminta tambahan hingga dua kali dengan rentang klip yang sudah
dipilih dikecualikan. Kalau masih kurang, UI menampilkan peringatan
"AI hanya menemukan X dari Y momen".

Caption memakai timing kata asli dari track auto `*-orig`. Tiga gaya karaoke:

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

Warna aksen diatur di **Pengaturan → Klip → Warna caption** (default kuning
`#FFD700`). Hook memakai warna yang sama.

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
| Tests | Tidak diketahui | 28 unit/integration test |

## Batasan yang jujur

- **Butuh subtitle.** Kalau video tidak punya caption sama sekali, app berhenti
  dengan pesan jelas. Tidak ada fallback Whisper.
- **Belum ada face tracking.** Reframe vertikal memakai center crop (hitam atau
  blur). Untuk konten yang wajahnya selalu di tengah, hasilnya sudah layak.
- **Tidak ada Repliz / penjadwalan sosmed / billing.** Fokus versi ini:
  menghasilkan file MP4.
- **Caption manual bersifat perkiraan.** Word timing asli hanya tersedia di
  track auto-caption `*-orig`; SRT manual dibagi proporsional per karakter.
- **UI belum punya pemilih track subtitle manual per bahasa.** Otomatis:
  bahasa yang diminta → track original → en → track pertama.
- **Tidak ada code signing.** Windows SmartScreen bisa muncul; ini normal untuk
  aplikasi lokal yang belum ditandatangani.
- Semua proses berjalan lokal; kualitas highlight sangat tergantung model AI.

## Struktur

```
AIKLIPYT/
  run.bat              # launcher + bootstrap venv
  server.py            # HTTP server 127.0.0.1 + API
  core/
    config.py          # setelan & path portable
    secret.py          # DPAPI
    assets.py          # cari ffmpeg/deno
    ytdlp.py           # info, subtitle, download section
    subtitles.py       # SRT/VTT/json3 → word timing
    highlights.py      # prompt + panggilan AI + validasi JSON
    render.py          # ASS caption, reframe, encode
    session.py         # penyimpanan sesi
    cookies.py         # filter cookies YouTube
    pipeline.py        # job background
  web/                 # UI (HTML/CSS/JS, tanpa build step)
    assets/logo.svg    # brand mark (favicon + sidebar)
    assets/logo.png    # fallback raster 640px
  tests/               # unittest
```

## Test

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test render memakai ffmpeg untuk membuat video sintetis dan memverifikasi
output 1080x1920. Test DPAPI hanya berjalan di Windows.

## Troubleshooting

- **"ffmpeg tidak ditemukan"** — taruh `ffmpeg.exe` di `assets\ffmpeg\` atau
  isi path absolut di Pengaturan.
- **HTTP 403 / "Sign in to confirm you're not a bot"** — cookies hilang atau
  kedaluwarsa. Ekspor ulang cookies YouTube, lalu simpan.
- **"Video ini tidak punya subtitle"** — pilih video dengan caption, atau
  aktifkan auto-caption di YouTube.
- **AI error 401/404** — cek base URL (harus berakhiran `/v1` untuk OpenAI),
  API key, dan nama model.
- **Log menyebut `h264_nvenc failed` / `libx264`** — GPU NVIDIA tidak ada atau
  driver belum terpasang. AIKLIPYT sekarang menguji encoder sebelum dipakai;
  mesin Intel akan memakai QSV, mesin tanpa GPU memakai libx264. Tidak perlu
  mengubah pengaturan.
- **Port dipakai** — server otomatis mencoba port berikutnya; lihat URL di
  konsol.

## Keamanan

File `cookies.txt` adalah kredensial hidup. Jangan dibagikan. Kalau pernah
mengekspor seluruh cookie browser (bukan hanya YouTube), hapus file aslinya dan
logout/rotasi sesi Google. AIKLIPYT hanya menyimpan cookie YouTube setelah
difilter, tapi tetap perlakukan `data\cookies.txt` seperti password.

API key disimpan terenkripsi DPAPI, tetapi tetap bisa dibaca oleh proses yang
berjalan sebagai user Windows yang sama. Gunakan key khusus dengan limit.
