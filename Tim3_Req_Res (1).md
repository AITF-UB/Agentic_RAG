# Request Response MVP buat RAG & AGENTIC
## Per Tanggal 05/06/2025

### Format Request Konten Generate
- `bacaan`: 3x [`lots`, `mots`, `hots`]
- `quiz_pg`: 3x [`lots`, `mots`, `hots`]
- `quiz_essay`: 3x [`lots`, `mots`, `hots`]
- `flashcard`: 3x [`lots`, `mots`, `hots`]
- `mindmap`: 1x
- `pretest`: 1x
- `rekomendasi`: tbd
```json
{
  "mapel_id": "string",
  "elemen_id": "string",
  "elemen_label": "string",
  "materi": "string | null",
  "materi_id": "string | null",
  "kelas_id": "string",
  "jenjang": "string",
  "atp": ["string"] ,
  "tipe": "game | quiz | video | null",
  "level": "easy | medium | hard | null",
  "konten_id": "string | null",
  "instruksi_revisi": "string | null"
}
```

### Format Response Konten Generate (contoh mock di DB MVP)
### `bacaan`
```json
{
  "text": "## Tujuan Pembelajaran\nPada bagian ini, kamu belajar menyatakan perkalian berulang dalam bentuk bilangan berpangkat.\n\n## Konsep Inti\nBilangan berpangkat digunakan untuk menuliskan perkalian berulang secara ringkas. Bentuk a^n berarti bilangan a dikalikan dengan dirinya sendiri sebanyak n kali. Bilangan a disebut basis, sedangkan n disebut pangkat atau eksponen.\n\nContoh: 2^4 = 2 x 2 x 2 x 2 = 16. Bentuk ini lebih ringkas daripada menulis perkalian berulang.\n\n## Contoh Kontekstual\nSebuah pola memiliki 3 cabang. Setiap cabang bercabang lagi menjadi 3 bagian. Jika proses ini terjadi 4 tingkat, banyak cabang dapat ditulis sebagai 3^4.\n\n## Rangkuman\nBilangan berpangkat membantu kita menulis perkalian berulang secara singkat dan menjadi dasar untuk memahami pertumbuhan, skala, dan notasi ilmiah.",
  "judul": "Mengenal Bilangan Berpangkat",
  "source": "Matematika Fase E - Bilangan",
  "image_path": null
}
```

### `flashcard`
```json
{
  "cards": [
    {
      "depan": "Model pertidaksamaan",
      "belakang": "Representasi batasan sumber daya dalam masalah nyata."
    },
    {
      "depan": "Optimasi kuadrat",
      "belakang": "Mencari nilai maksimum/minimum melalui titik puncak."
    },
    {
      "depan": "Fungsi pertumbuhan",
      "belakang": "Model eksponensial untuk pertumbuhan dengan faktor tetap."
    },
    {
      "depan": "Feasible region",
      "belakang": "Daerah semua solusi yang memenuhi batasan."
    }
  ],
  "source": "Matematika Fase E - Aljabar dan Fungsi"
}
```


### `mindmap`
```json
{
  "nodes": [
    {
      "id": "n1",
      "label": "Bilangan Berpangkat",
      "parent_id": null,
      "penjelasan": "Topik utama tentang eksponen dan penggunaannya."
    },
    {
      "id": "n2",
      "label": "Konsep Dasar",
      "parent_id": "n1",
      "penjelasan": "Mengenal basis, pangkat, dan perkalian berulang."
    },
    {
      "id": "n3",
      "label": "Sifat Eksponen",
      "parent_id": "n1",
      "penjelasan": "Perkalian, pembagian, pangkat dari pangkat, pangkat nol, dan pangkat pecahan."
    },
    {
      "id": "n4",
      "label": "Penyederhanaan",
      "parent_id": "n1",
      "penjelasan": "Menggunakan aturan eksponen untuk menyederhanakan operasi."
    },
    {
      "id": "n5",
      "label": "Pemodelan",
      "parent_id": "n1",
      "penjelasan": "Menggunakan eksponen untuk pertumbuhan, penyusutan, dan notasi ilmiah."
    },
    {
      "id": "n6",
      "label": "Masalah Kontekstual",
      "parent_id": "n5",
      "penjelasan": "Menyelesaikan kasus populasi, tabungan, skala, dan data besar."
    }
  ]
}
```


### `quiz_pg`
```json
{
  "soal": [
    {
      "id": "q1",
      "soal": "Bentuk pangkat yang tepat adalah ...",
      "jawaban": 1,
      "pilihan": [
        "5^2",
        "5^3",
        "3^5",
        "15^1"
      ],
      "stimulus": "Perkalian 5 x 5 x 5 dapat ditulis dalam bentuk pangkat.",
      "image_path": null,
      "penjelasan": "Bilangan 5 dikalikan berulang sebanyak 3 kali, sehingga ditulis 5^3."
    },
    {
      "id": "q2",
      "soal": "Angka 7 pada 7^4 disebut ...",
      "jawaban": 1,
      "pilihan": [
        "pangkat",
        "basis",
        "hasil",
        "koefisien"
      ],
      "stimulus": "Pada bentuk 7^4, angka 7 dan 4 memiliki peran berbeda.",
      "image_path": null,
      "penjelasan": "Pada bentuk a^n, a disebut basis dan n disebut pangkat."
    },
    {
      "id": "q3",
      "soal": "Nilai dari 2^5 adalah ...",
      "jawaban": 3,
      "pilihan": [
        "10",
        "16",
        "25",
        "32"
      ],
      "stimulus": "Rani menulis 2^5 di papan tulis.",
      "image_path": null,
      "penjelasan": "2^5 = 2 x 2 x 2 x 2 x 2 = 32."
    },
    {
      "id": "q4",
      "soal": "Cara membaca 9^2 yang tepat adalah ...",
      "jawaban": 1,
      "pilihan": [
        "sembilan kali dua",
        "sembilan pangkat dua",
        "dua pangkat sembilan",
        "sembilan dibagi dua"
      ],
      "stimulus": "Bentuk 9^2 dibaca sebagai ...",
      "image_path": null,
      "penjelasan": "9^2 dibaca sembilan pangkat dua."
    },
    {
      "id": "q5",
      "soal": "Bentuk pangkatnya adalah ...",
      "jawaban": 2,
      "pilihan": [
        "4^2",
        "4^3",
        "4^4",
        "16^2"
      ],
      "stimulus": "Perkalian 4 x 4 x 4 x 4 adalah perkalian berulang.",
      "image_path": null,
      "penjelasan": "Ada empat faktor bernilai 4, sehingga bentuknya 4^4."
    },
    {
      "id": "q6",
      "soal": "Nilai dari 10^3 adalah ...",
      "jawaban": 2,
      "pilihan": [
        "30",
        "100",
        "1.000",
        "10.000"
      ],
      "stimulus": "Bilangan 10^3 sering muncul dalam satuan ribuan.",
      "image_path": null,
      "penjelasan": "10^3 = 10 x 10 x 10 = 1.000."
    },
    {
      "id": "q7",
      "soal": "Pada 3^6, eksponennya adalah ...",
      "jawaban": 1,
      "pilihan": [
        "3",
        "6",
        "9",
        "18"
      ],
      "stimulus": "Bentuk a^n memiliki basis dan eksponen.",
      "image_path": null,
      "penjelasan": "Eksponen adalah angka kecil di atas, yaitu 6."
    },
    {
      "id": "q8",
      "soal": "Bentuk pangkatnya adalah ...",
      "jawaban": 1,
      "pilihan": [
        "8^1",
        "8^2",
        "2^8",
        "16^1"
      ],
      "stimulus": "Perkalian 8 x 8 dapat ditulis secara ringkas.",
      "image_path": null,
      "penjelasan": "8 dikalikan dengan dirinya sendiri dua kali, sehingga 8^2."
    },
    {
      "id": "q9",
      "soal": "Banyak kemungkinan dapat ditulis sebagai ...",
      "jawaban": 1,
      "pilihan": [
        "2+3",
        "2^3",
        "3^2",
        "2x3x3"
      ],
      "stimulus": "Sebuah pola memiliki 2 pilihan pada setiap tahap dan berlangsung 3 tahap.",
      "image_path": null,
      "penjelasan": "Dua pilihan berulang selama 3 tahap dapat dinyatakan sebagai 2^3."
    },
    {
      "id": "q10",
      "soal": "Manakah yang sama dengan 6^3?",
      "jawaban": 2,
      "pilihan": [
        "6+6+6",
        "6x3",
        "6x6x6",
        "3x3x3x3x3x3"
      ],
      "stimulus": "Bilangan berpangkat digunakan untuk menulis perkalian berulang.",
      "image_path": null,
      "penjelasan": "6^3 berarti 6 x 6 x 6."
    }
  ]
}
```


### `quiz_essay`
```json
{
  "pertanyaan": [
    {
      "id": "e1",
      "soal": "Jelaskan arti bentuk 4^3 dan hitung nilainya.",
      "rubrik": "Skor tinggi jika siswa menjelaskan basis, pangkat, perkalian berulang, dan hasil 64.",
      "stimulus": "Bilangan berpangkat merupakan cara ringkas menulis perkalian berulang.",
      "image_path": null,
      "penjelasan": "4^3 berarti 4 x 4 x 4 = 64."
    },
    {
      "id": "e2",
      "soal": "Jelaskan perbedaan basis dan pangkat pada bentuk 6^5.",
      "rubrik": "Skor tinggi jika siswa menyebutkan 6 sebagai basis dan 5 sebagai pangkat serta menjelaskan maknanya.",
      "stimulus": "Dalam bentuk a^n, a dan n memiliki nama yang berbeda.",
      "image_path": null,
      "penjelasan": "Pada 6^5, 6 adalah bilangan yang dikalikan berulang, sedangkan 5 menunjukkan banyaknya pengulangan."
    },
    {
      "id": "e3",
      "soal": "Ubah 3 x 3 x 3 x 3 menjadi bentuk pangkat dan jelaskan alasannya.",
      "rubrik": "Skor tinggi jika siswa menulis 3^4 dan menjelaskan ada empat faktor 3.",
      "stimulus": "Perkalian berulang dapat ditulis menjadi bentuk pangkat.",
      "image_path": null,
      "penjelasan": "Bentuknya 3^4 karena angka 3 muncul sebagai faktor sebanyak 4 kali."
    },
    {
      "id": "e4",
      "soal": "Berikan satu contoh pola sederhana yang dapat ditulis dalam bentuk pangkat.",
      "rubrik": "Skor tinggi jika contoh relevan dan menunjukkan perkalian berulang.",
      "stimulus": "Bilangan berpangkat sering dipakai dalam pola.",
      "image_path": null,
      "penjelasan": "Contoh: dua pilihan di setiap tahap selama 3 tahap dapat ditulis sebagai 2^3."
    },
    {
      "id": "e5",
      "soal": "Mengapa 10^6 lebih praktis daripada menulis 1.000.000?",
      "rubrik": "Skor tinggi jika siswa menjelaskan efisiensi penulisan dan makna pangkat.",
      "stimulus": "Bilangan berpangkat membantu membuat penulisan lebih ringkas.",
      "image_path": null,
      "penjelasan": "10^6 menyatakan 10 dikalikan berulang 6 kali sehingga lebih ringkas untuk bilangan besar."
    }
  ]
}
```


### Format Request Game Generate (Beda endpoint)
- `game`: 3x [`lots`, `mots`, `hots`]
```json
{
  "mapel_id": "string",
  "elemen_id": "string",
  "elemen_label": "string",
  "materi": "string | null",
  "materi_id": "string | null",
  "kelas_id": "string",
  "jenjang": "string",
  "atp": ["string"] | null,
  "level": "Low | Mid | High | null",
  "bacaan": {
    "judul": "string",
    "text": "string (markdown)",
    "source": "string",
    "image_path": "string | null"
  } | null
}
```

### `pretest`
```json
{
  "soal": [
    {
      "id": "p1",
      "soal": "Manakah yang merupakan pertidaksamaan linear dua variabel?",
      "level": "lots",
      "jawaban": 1,
      "pilihan": [
        "x + y = 10",
        "2x - y > 4",
        "x^2 + y = 9",
        "y = 3x + 2"
      ],
      "stimulus": "Persamaan linear dua variabel biasanya memuat tanda sama dengan, sedangkan pertidaksamaan memuat tanda <, >, <=, atau >=.",
      "image_path": null,
      "penjelasan": "Bentuk 2x - y > 4 adalah pertidaksamaan linear dua variabel karena memuat x, y, dan tanda lebih dari."
    },
    {
      "id": "p2",
      "soal": "Manakah yang merupakan persamaan kuadrat?",
      "level": "lots",
      "jawaban": 1,
      "pilihan": [
        "2x + 3 = 7",
        "x^2 - 5x + 6 = 0",
        "3x + 2y = 8",
        "2^x = 16"
      ],
      "stimulus": "Persamaan kuadrat memiliki bentuk umum ax^2 + bx + c = 0 dengan a tidak sama dengan 0.",
      "image_path": null,
      "penjelasan": "x^2 - 5x + 6 = 0 merupakan persamaan kuadrat karena pangkat tertinggi variabelnya adalah 2."
    },
    {
      "id": "p3",
      "soal": "Manakah contoh fungsi kuadrat?",
      "level": "lots",
      "jawaban": 1,
      "pilihan": [
        "f(x)=2x+1",
        "f(x)=x^2-4x+3",
        "f(x)=3^x",
        "f(x)=5"
      ],
      "stimulus": "Fungsi kuadrat memiliki grafik berbentuk parabola.",
      "image_path": null,
      "penjelasan": "Fungsi kuadrat memiliki suku x^2 dengan koefisien tidak nol."
    },
    {
      "id": "p4",
      "soal": "Manakah contoh persamaan eksponensial?",
      "level": "lots",
      "jawaban": 2,
      "pilihan": [
        "x + 2 = 7",
        "x^2 = 9",
        "2^x = 32",
        "2x + y = 5"
      ],
      "stimulus": "Persamaan eksponensial memuat variabel pada pangkat.",
      "image_path": null,
      "penjelasan": "Pada 2^x = 32, variabel x berada pada pangkat."
    },
    {
      "id": "p5",
      "soal": "Akar-akar dari x^2 - 5x + 6 = 0 adalah ...",
      "level": "mots",
      "jawaban": 1,
      "pilihan": [
        "1 dan 6",
        "2 dan 3",
        "-2 dan -3",
        "-1 dan -6"
      ],
      "stimulus": "Akar-akar persamaan kuadrat dapat diperoleh dengan faktorisasi jika bentuknya mudah difaktorkan.",
      "image_path": null,
      "penjelasan": "x^2 - 5x + 6 = (x - 2)(x - 3), sehingga akarnya x = 2 dan x = 3."
    },
    {
      "id": "p6",
      "soal": "Jika 3^(x+1) = 3^5, maka nilai x adalah ...",
      "level": "mots",
      "jawaban": 1,
      "pilihan": [
        "3",
        "4",
        "5",
        "6"
      ],
      "stimulus": "Persamaan eksponensial dengan basis sama dapat diselesaikan dengan menyamakan pangkatnya.",
      "image_path": null,
      "penjelasan": "Karena basis sama, x + 1 = 5 sehingga x = 4."
    },
    {
      "id": "p7",
      "soal": "Untuk x^2 - 4x + 4 = 0, nilai diskriminannya adalah ...",
      "level": "mots",
      "jawaban": 0,
      "pilihan": [
        "0",
        "4",
        "8",
        "16"
      ],
      "stimulus": "Diskriminan persamaan kuadrat ax^2 + bx + c = 0 adalah D = b^2 - 4ac.",
      "image_path": null,
      "penjelasan": "D = (-4)^2 - 4(1)(4) = 16 - 16 = 0."
    },
    {
      "id": "p8",
      "soal": "Titik (0,0) memenuhi pertidaksamaan x + y <= 5 karena ...",
      "level": "mots",
      "jawaban": 0,
      "pilihan": [
        "0 + 0 <= 5",
        "0 + 0 > 5",
        "0 + 5 = 5",
        "x dan y harus positif"
      ],
      "stimulus": "Daerah penyelesaian pertidaksamaan linear dapat diuji menggunakan titik tertentu.",
      "image_path": null,
      "penjelasan": "Substitusi (0,0) menghasilkan 0 <= 5, sehingga titik tersebut memenuhi pertidaksamaan."
    },
    {
      "id": "p9",
      "soal": "Apa makna utama daerah penyelesaian dari sistem pertidaksamaan tersebut?",
      "level": "hots",
      "jawaban": 0,
      "pilihan": [
        "Semua kemungkinan jumlah kendaraan yang memenuhi kedua batasan",
        "Hanya satu titik yang menjadi jawaban",
        "Jumlah kendaraan yang tidak mungkin terjadi",
        "Grafik fungsi kuadrat dari kendaraan"
      ],
      "stimulus": "Sebuah daerah parkir memiliki batas x + y <= 20 dan 2x + y <= 30, dengan x dan y menyatakan banyak kendaraan dua jenis berbeda.",
      "image_path": null,
      "penjelasan": "Daerah penyelesaian sistem pertidaksamaan berisi semua pasangan nilai x dan y yang memenuhi seluruh batasan."
    },
    {
      "id": "p10",
      "soal": "Makna titik puncak grafik fungsi tersebut adalah ...",
      "level": "hots",
      "jawaban": 1,
      "pilihan": [
        "waktu saat bola mulai dilempar",
        "tinggi maksimum bola",
        "jarak horizontal bola",
        "waktu saat bola menyentuh tanah saja"
      ],
      "stimulus": "Sebuah bola dilempar sehingga tinggi h terhadap waktu t dimodelkan dengan h(t) = -t^2 + 6t + 1.",
      "image_path": null,
      "penjelasan": "Pada fungsi kuadrat yang membuka ke bawah, titik puncak menyatakan nilai maksimum, yaitu tinggi maksimum bola."
    }
  ]
}
```

### Format Request Evaluasi Essay
```json
{
  {
    "jawaban_siswa": "string",
    "soal": "Berikan satu contoh pola sederhana yang dapat ditulis dalam bentuk pangkat.",
    "rubrik": "Skor tinggi jika contoh relevan dan menunjukkan perkalian berulang.",
    "stimulus": "Bilangan berpangkat sering dipakai dalam pola.",
    "image_path": null, // perlu gak?
    "penjelasan": "Contoh: dua pilihan di setiap tahap selama 3 tahap dapat ditulis sebagai 2^3."
  },
  {
    "jawaban_siswa": "string",
    "soal": "Jelaskan arti bentuk 4^3 dan hitung nilainya.",
    "rubrik": "Skor tinggi jika siswa menjelaskan basis, pangkat, perkalian berulang, dan hasil 64.",
    "stimulus": "Bilangan berpangkat merupakan cara ringkas menulis perkalian berulang.",
    "image_path": null,
    "penjelasan": "4^3 berarti 4 x 4 x 4 = 64."
  },
  {
    "jawaban_siswa": "string",
    "soal": "Jelaskan arti bentuk 4^3 dan hitung nilainya.",
    "rubrik": "Skor tinggi jika siswa menjelaskan basis, pangkat, perkalian berulang, dan hasil 64.",
    "stimulus": "Bilangan berpangkat merupakan cara ringkas menulis perkalian berulang.",
    "image_path": null,
    "penjelasan": "4^3 berarti 4 x 4 x 4 = 64."
  },
  {
    "jawaban_siswa": "string",
    "soal": "Jelaskan arti bentuk 4^3 dan hitung nilainya.",
    "rubrik": "Skor tinggi jika siswa menjelaskan basis, pangkat, perkalian berulang, dan hasil 64.",
    "stimulus": "Bilangan berpangkat merupakan cara ringkas menulis perkalian berulang.",
    "image_path": null,
    "penjelasan": "4^3 berarti 4 x 4 x 4 = 64."
  },
  {
    "jawaban_siswa": "string",
    "soal": "Jelaskan arti bentuk 4^3 dan hitung nilainya.",
    "rubrik": "Skor tinggi jika siswa menjelaskan basis, pangkat, perkalian berulang, dan hasil 64.",
    "stimulus": "Bilangan berpangkat merupakan cara ringkas menulis perkalian berulang.",
    "image_path": null,
    "penjelasan": "4^3 berarti 4 x 4 x 4 = 64."
  },
}
```
### Format Request Insight RAG (katanya token dibatas 256)
```json
{
  "nama": "Nama Siswa",
  "streak": 3,
  "total_topik": 2,
  "total_poin_kuiz": 85,
  "total_durasi_menit": 45,
}
```

### Format Response Insight RAG
```json
{
  "insight_text": "string"
}
```

### Format Request RAG Summary
```json
{
  "siswa": "nama",
  "mapel_label": "string",
  "elemen_label": "string",
  "materi_id": "string",
  "durasi_menit": 15,
  "hasil_quiz": [
    {
      "level": "high",
      "tipe": "mc",
      "nilai": 30
    }
  ],
  "last_quiz": {
    "nilai_mc": 30,
    "nilai_essay": null,
    "agregasi": null
  },
  "emosi_sesi": [
    "bosan"
  ],
  "violations": [
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-03T09:46:55.352000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-03T10:06:08.782000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-04T05:52:53.624000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-04T10:26:27.626000+07:00"
    },
    {
      "detail": "Berpindah Tab / Menyembunyikan Halaman",
      "terjadi_at": "2026-06-04T10:26:42.819000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-04T17:49:24.653000+07:00"
    },
    {
      "detail": "Berpindah Tab / Menyembunyikan Halaman",
      "terjadi_at": "2026-06-04T17:49:57.652000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-04T17:53:56.102000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-04T18:01:16.500000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-05T19:17:20.048000+07:00"
    },
    {
      "detail": "Membuka Aplikasi / Window Lain",
      "terjadi_at": "2026-06-05T19:17:41.787000+07:00"
    }
  ]
}
```

### Format Response Summary RAG
```json
{
  "summary_text": "string"
}
```

### Format Request Rekomendasi RAG
```json
{
    "available": [
        {
            "bundle_id": "1",
            "mapel_label": "Matematika Wajib",
            "elemen_label": "Bilangan dan Aljabar",
            "materi": "Persamaan Linear",
            "atp": [
                "deskripsi atp 1",
                "deskripsi atp 2"
            ]
        },
        {
            "bundle_id": "2",
            "mapel_label": "Biologi",
            "elemen_label": "Anatomi Tubuh",
            "materi": "Sistem Pernapasan",
            "atp": [
                "deskripsi atp 1"
            ]
        },
        {
            "bundle_id": "4",
            "mapel_label": "Kimia",
            "elemen_label": "Struktur Atom",
            "materi": "Nomor massa dan jumlah elektron",
            "atp": []
        }
    ],
    "in_progress_ids": [
        {
            "bundle_id": "2",
            "mapel_label": "Biologi",
            "elemen_label": "Anatomi Tubuh",
            "materi": "Sistem Pernapasan",
            "atp": [
                "deskripsi atp 1"
            ]
        }
    ],
    "complete_ids": [
        {
            "bundle_id": "1",
            "mapel_label": "Matematika Wajib",
            "elemen_label": "Bilangan dan Aljabar",
            "materi": "Persamaan Linear",
            "atp": [
                "deskripsi atp 1",
                "deskripsi atp 2"
            ]
        }
    ]
}
```

### Format Response Rekomendasi RAG
```json
{
  "rekomendasi": [
    {
      "bundle_id": "2",
      "mapel_label": "Biologi",
      "elemen_label": "Anatomi Tubuh",
      "materi": "Sistem Pernapasan",
      "alasan": "string"
    },
    {
      "bundle_id": "4",
      "mapel_label": "Kimia",
      "elemen_label": "Struktur Atom",
      "materi": "Nomor massa dan jumlah elektron",
      "alasan": "string"
    }
  ]
}
```
