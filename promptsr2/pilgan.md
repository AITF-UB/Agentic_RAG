[TUGAS]

Buat TEPAT 10 soal pilihan ganda dalam format JSON array.

[SKEMA_KELUARAN]

[
    {
        "level": "LOTS/MOTS/HOTS",
        "stimulus": "",
        "question": "",
        "options": {
            "A": "",
            "B": "",
            "C": "",
            "D": "",
            "E": ""
        },
        "answer": "",
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

[ATURAN_SOAL]

* Seluruh soal harus sesuai dengan level yang diberikan.
* Seluruh soal harus mengukur kompetensi yang relevan dengan konteks pembelajaran dan ATP (jika tersedia).
* Soal harus kontekstual, realistis, dan bergantung pada stimulus.
* Pastikan hanya ada satu jawaban yang paling benar.
* Hindari pola soal yang berulang.

[ATURAN_STIMULUS]

- Setiap soal harus memiliki stimulus.
- Stimulus harus ringkas, relevan, dan memuat informasi yang cukup untuk dianalisis.
- Gunakan bentuk stimulus sesuai konfigurasi yang diberikan.
- Variasikan bentuk stimulus dalam satu paket soal.
- Jika stimulus memuat beberapa data, kategori, atau perbandingan, prioritaskan tabel atau data terstruktur dibanding paragraf.
- Hindari dominasi narasi murni dalam satu paket soal.
- Jika relevan, stimulus dapat menggabungkan beberapa bentuk yang saling melengkapi.

[ATURAN_OPSI]

* Semua opsi harus masuk akal dan relevan dengan stimulus.
* Panjang, tingkat detail, dan gaya bahasa opsi harus relatif seimbang.
* Jawaban benar tidak boleh tampak paling panjang, paling spesifik, atau paling berbeda.
* Distraktor harus mencerminkan miskonsepsi atau penalaran yang realistis.

[ATURAN_PENJELASAN]

Penjelasan berfungsi sebagai pembahasan soal.

Gunakan:

### Analisis 
- Dasar Teori
- Gunakan pembahasan bertahap terhadap masalah yang akan dipecahkan


[PENGGUNAAN_EMOJI]

Gunakan emoji secara fungsional pada stimulus dan penjelasan untuk:

- informasi penting
- data penting
- langkah penyelesaian
- kesimpulan

Hindari emoji dekoratif.

[BATASAN]
Hindari instruksi atau struktur internal muncul pada konten.