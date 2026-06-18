[TUGAS]

Buat TEPAT 5 soal esai dalam format JSON array.

[SKEMA_KELUARAN]

[
  {
    "level": "LOTS/MOTS/HOTS",
    "stimulus": "",
    "question": "",
    "rubric_points": [],
    "explanation": ""
  }
]

[KONFIGURASI_LEVEL]

{LEVEL_CONFIGURATION}

[KONFIGURASI_STIMULUS]

{STIMULUS_CONFIGURATION}

[KONTEKS_PEMBELAJARAN]

{context}

[ATP]

{atp}

Prioritaskan ATP jika tersedia.

[ATURAN_SOAL]

* Soal harus sesuai level yang diberikan.
* Soal harus relevan dengan konteks pembelajaran dan ATP.
* Soal harus kontekstual, realistis, dan bergantung pada stimulus.
* Hindari pola soal yang berulang.

[ATURAN_STIMULUS]

* Setiap soal wajib memiliki stimulus.
* Variasikan bentuk stimulus dalam satu paket soal.
* Jika memuat data atau perbandingan, prioritaskan tabel atau data terstruktur.
* Hindari dominasi narasi murni.

[ATURAN_RUBRIK]

* Gunakan 3 indikator penilaian yang operasional, terukur, dan singkat.
* Sesuaikan indikator dengan level yang diberikan.

[ATURAN_PENJELASAN]

Penjelasan ditampilkan kepada siswa sebagai pembahasan soal.

Gunakan struktur:

### Pengerjaan
* Langkah atau analisis bertahap menuju jawaban.
* Untuk STEM gunakan LaTeX bila diperlukan.
* Untuk non-STEM jelaskan alasan atau hubungan konsep yang mendukung jawaban.

Hindari chain-of-thought yang panjang.

[PENYAJIAN_VISUAL_PENJELASAN]

Gunakan bila relevan:

* bullet list → poin jawaban
* tabel → perbandingan
* blockquote → kesimpulan
* bold → konsep penting

[PENGGUNAAN_EMOJI]

Gunakan emoji secara fungsional pada stimulus dan penjelasan untuk:

- informasi penting
- data penting
- langkah penyelesaian
- kesimpulan

Hindari emoji dekoratif.

[BATASAN]
Hindari instruksi atau struktur internal muncul pada konten.