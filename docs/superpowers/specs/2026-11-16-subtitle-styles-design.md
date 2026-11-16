# Design: 5 gaya subtitle baru

Tanggal: 2026-11-16

## Intent / why

User ingin 5 preset subtitle baru di dropdown "Gaya karaoke" yang sudah ada:
Hormozi, Karaoke word-by-word, Iman Gadzhi (minimalis), MrBeast (high-energy),
dan Bilingual / Dual-Layer. Semua harus jalan tanpa dependency baru dan tanpa
merusak 9 gaya yang sudah ada.

## Goals

- 4 preset ASS murni + 1 preset bilingual (dua lapis teks).
- Tanpa dependency baru; tanpa engine subtitle atau font baru.
- Session/config lama tetap jalan; default tetap `highlight`.

## Non-goals

- Tidak mengubah deteksi highlight / prompt AI.
- Tidak menambah field UI baru untuk bahasa terjemahan.
- Tidak mengubah pipeline download/render selain yang diperlukan bilingual.

## Constraints / fakta kode

- `core/render.py:build_ass()` sudah punya 9 gaya, semuanya override tag ASS.
- `web/index.html:347` `<select id="captionStyle">`; nilainya lolos validasi di
  `server.py:159-170` (duplikat daftar dengan `_CAPTION_STYLES` di render.py).
- `Word` punya `start`/`end` per kata; `_groups()` mengelompokkan kata.
- `config["outputLanguage"]` sudah ada (dipakai prompt highlight).

## Approaches

- **A (dipilih):** perluas resep ASS di `build_ass()` + satu helper terjemahan
  yang memakai `chat()` yang sudah ada. Cocok dengan arsitektur sekarang, nol
  dependency.
- B: caption sebagai overlay gambar/drawtext ffmpeg — presisi lebih tinggi tapi
  jalur render terpisah dan jauh lebih banyak kode.
- C: library subtitle baru — ditolak, ASS sudah cukup.

## Design (keputusan implementasi)

1. `core/render.py`
   - Ganti `_CAPTION_STYLES` menjadi `CAPTION_STYLES` (public), isi 14 nama.
   - Tambah recipe:
     - `hormozi`: Arial Black, uppercase, outline hitam tebal, kata aktif = accent
       + skala 118%.
     - `karaoke`: satu event per grup dengan tag `{\kf<centis>}` untuk sweep isian.
     - `gadzhi`: Arial tipis, putih, outline 1, tanpa animasi.
     - `mrbeast`: uppercase, palet warna bergilir per kata, skala 120%, outline putih tebal.
     - `bilingual`: dua event per grup (asli + terjemahan) dengan style `CaptionAlt`
       di atas caption utama.
   - `build_ass()` menerima `translations: list[str] | None` (sejajar dengan grup).
2. `core/highlights.py`: `translate_groups(texts, target, base, key, model, timeout)`
   — satu panggilan `chat()`, balasan JSON array, return `list[str]`; error → raise.
3. `core/pipeline.py`: jika `captionStyle == "bilingual"`, terjemahkan grup kata
   per klip sekali sebelum render; pada kegagalan AI, log + lanjut single-layer.
4. `server.py`: import `CAPTION_STYLES` untuk validasi (hapus duplikat tuple).
5. `web/index.html`: 5 `<option>` baru dalam optgroup; bahasa target bilingual =
   `outputLanguage` (fallback `en` bila `auto`).
6. Test: satu assertion `build_ass()` per gaya + test parse/error `translate_groups`.
