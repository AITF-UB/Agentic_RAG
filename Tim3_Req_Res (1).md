# Request Response MVP buat RAG & AGENTIC
## Per Tanggal 21/06/2026
## NYESUAIN SR 2

### Format Request Konten Generate
- `bacaan`: 3x [`lots`, `mots`, `hots`]
- `quiz_pg`: 3x [`lots`, `mots`, `hots`]
- `quiz_essay`: 3x [`lots`, `mots`, `hots`]
- `flashcard`: 3x [`lots`, `mots`, `hots`]
- `mindmap`: 1x
- `pretest`: 1x
- `rekomendasi`: 1x
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
  "konten_markdown": "## Tujuan Pembelajaran\nPada bagian ini, kamu belajar menyatakan perkalian berulang dalam bentuk bilangan berpangkat.\n\n## Konsep Inti\nBilangan berpangkat digunakan untuk menuliskan perkalian berulang secara ringkas. Bentuk a^n berarti bilangan a dikalikan dengan dirinya sendiri sebanyak n kali. Bilangan a disebut basis, sedangkan n disebut pangkat atau eksponen.\n\nContoh: 2^4 = 2 x 2 x 2 x 2 = 16. Bentuk ini lebih ringkas daripada menulis perkalian berulang.\n\n## Contoh Kontekstual\nSebuah pola memiliki 3 cabang. Setiap cabang bercabang lagi menjadi 3 bagian. Jika proses ini terjadi 4 tingkat, banyak cabang dapat ditulis sebagai 3^4.\n\n## Rangkuman\nBilangan berpangkat membantu kita menulis perkalian berulang secara singkat dan menjadi dasar untuk memahami pertumbuhan, skala, dan notasi ilmiah.",
  "judul_utama": "Mengenal Bilangan Berpangkat",
  "source": "Matematika Fase E - Bilangan",
  "image_path": null
}
```

### `flashcard`
```json
{
  "cards": [
    {
      "front": "Model pertidaksamaan",
      "back": "Representasi batasan sumber daya dalam masalah nyata."
    },
    {
      "front": "Optimasi kuadrat",
      "back": "Mencari nilai maksimum/minimum melalui titik puncak."
    },
    {
      "front": "Fungsi pertumbuhan",
      "back": "Model eksponensial untuk pertumbuhan dengan faktor tetap."
    },
    {
      "front": "Feasible region",
      "back": "Daerah semua solusi yang memenuhi batasan."
    }
  ],
  "source": "Matematika Fase E - Aljabar dan Fungsi"
}
```


### `mindmap`
```json
{
  "root": {
      "name": "Unsur Kebahasaan Teks Negosiasi 🤝",
      "description": "Elemen bahasa untuk mencapai kesepakatan yang saling menguntungkan dalam negosiasi.",
      "children": [
        {
          "name": "Tuturan Berpasangan 🗣️",
          "description": "Pola percakapan timbal balik antara pihak yang terlibat dalam negosiasi.",
          "children": [
            {
              "name": "Salam",
              "description": "Mengucapkan dan membalas salam sebagai pembuka interaksi.",
              "children": []
            },
            {
              "name": "Tanya-Jawab",
              "description": "Proses pertukaran informasi melalui pertanyaan dan jawaban.",
              "children": []
            },
            {
              "name": "Permintaan",
              "description": "Meminta sesuatu dan memberikan respon memenuhi atau menolak.",
              "children": []
            },
            {
              "name": "Penawaran",
              "description": "Menawarkan sesuatu dan memberikan respon menerima atau menolak.",
              "children": []
            }
          ]
        },
        {
          "name": "Kalimat Persuasif 🎯",
          "description": "Bahasa yang digunakan untuk membujuk pihak lain mencapai kesepakatan.",
          "children": [
            {
              "name": "Tujuan",
              "description": "Mengarahkan pihak lain agar setuju dengan tawaran yang diajukan.",
              "children": []
            },
            {
              "name": "Fungsi",
              "description": "Mencapai jalan tengah atau keberhasilan transaksi.",
              "children": []
            }
          ]
        },
        {
          "name": "Pronomina 👤",
          "description": "Kata ganti persona untuk mewakili pihak yang berkepentingan.",
          "children": [
            {
              "name": "Contoh Kata",
              "description": "Penggunaan kata saya, kami, dan Anda dalam percakapan.",
              "children": []
            }
          ]
        },
        {
          "name": "Bahasa Santun ✨",
          "description": "Penggunaan tutur kata sopan sebagai cerminan sikap saling menghargai.",
          "children": [
            {
              "name": "Etika",
              "description": "Menjaga hubungan baik antar pihak selama proses negosiasi.",
              "children": []
            }
          ]
        }
      ]
    }
}
```


### `quiz_pg`
```json
{
  "soal": [
    {
      "id": "q1",
      "question": "Bentuk pangkat yang tepat adalah ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Perkalian 5 x 5 x 5 dapat ditulis dalam bentuk pangkat.",
      "image_path": null,
      "explanation": "Bilangan 5 dikalikan berulang sebanyak 3 kali, sehingga ditulis 5^3."
    },
    {
      "id": "q2",
      "question": "Angka 7 pada 7^4 disebut ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Pada bentuk 7^4, angka 7 dan 4 memiliki peran berbeda.",
      "image_path": null,
      "explanation": "Pada bentuk a^n, a disebut basis dan n disebut pangkat."
    },
    {
      "id": "q3",
      "question": "Nilai dari 2^5 adalah ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Rani menulis 2^5 di papan tulis.",
      "image_path": null,
      "explanation": "2^5 = 2 x 2 x 2 x 2 x 2 = 32."
    },
    {
      "id": "q4",
      "question": "Cara membaca 9^2 yang tepat adalah ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Bentuk 9^2 dibaca sebagai ...",
      "image_path": null,
      "explanation": "9^2 dibaca sembilan pangkat dua."
    },
    {
      "id": "q5",
      "question": "Bentuk pangkatnya adalah ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Perkalian 4 x 4 x 4 x 4 adalah perkalian berulang.",
      "image_path": null,
      "explanation": "Ada empat faktor bernilai 4, sehingga bentuknya 4^4."
    },
    {
      "id": "q6",
      "question": "Nilai dari 10^3 adalah ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Bilangan 10^3 sering muncul dalam satuan ribuan.",
      "image_path": null,
      "explanation": "10^3 = 10 x 10 x 10 = 1.000."
    },
    {
      "id": "q7",
      "question": "Pada 3^6, eksponennya adalah ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Bentuk a^n memiliki basis dan eksponen.",
      "image_path": null,
      "explanation": "Eksponen adalah angka kecil di atas, yaitu 6."
    },
    {
      "id": "q8",
      "question": "Bentuk pangkatnya adalah ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Perkalian 8 x 8 dapat ditulis secara ringkas.",
      "image_path": null,
      "explanation": "8 dikalikan dengan dirinya sendiri dua kali, sehingga 8^2."
    },
    {
      "id": "q9",
      "question": "Banyak kemungkinan dapat ditulis sebagai ...",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Sebuah pola memiliki 2 pilihan pada setiap tahap dan berlangsung 3 tahap.",
      "image_path": null,
      "explanation": "Dua pilihan berulang selama 3 tahap dapat dinyatakan sebagai 2^3."
    },
    {
      "id": "q10",
      "question": "Manakah yang sama dengan 6^3?",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Bilangan berpangkat digunakan untuk menulis perkalian berulang.",
      "image_path": null,
      "explanation": "6^3 berarti 6 x 6 x 6."
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
      "question": "Jelaskan arti bentuk 4^3 dan hitung nilainya.",
      "rubric_points": [
          "Mengidentifikasi pasangan tuturan (salam-salam, tanya-jawab, tawar-menawar).",
          "Menganalisis efektivitas respon penjual dalam menanggapi kendala pembeli.",
          "Menilai kesantunan bahasa sebagai pendukung keberhasilan negosiasi."
        ],
      "stimulus": "Bilangan berpangkat merupakan cara ringkas menulis perkalian berulang.",
      "image_path": null,
      "explanation": "4^3 berarti 4 x 4 x 4 = 64."
    },
    {
      "id": "e2",
      "question": "Jelaskan perbedaan basis dan pangkat pada bentuk 6^5.",
      "rubric_points": [
          "Mengidentifikasi pasangan tuturan (salam-salam, tanya-jawab, tawar-menawar).",
          "Menganalisis efektivitas respon penjual dalam menanggapi kendala pembeli.",
          "Menilai kesantunan bahasa sebagai pendukung keberhasilan negosiasi."
        ],
      "stimulus": "Dalam bentuk a^n, a dan n memiliki nama yang berbeda.",
      "image_path": null,
      "explanation": "Pada 6^5, 6 adalah bilangan yang dikalikan berulang, sedangkan 5 menunjukkan banyaknya pengulangan."
    },
    {
      "id": "e3",
      "question": "Ubah 3 x 3 x 3 x 3 menjadi bentuk pangkat dan jelaskan alasannya.",
      "rubric_points": [
          "Mengidentifikasi pasangan tuturan (salam-salam, tanya-jawab, tawar-menawar).",
          "Menganalisis efektivitas respon penjual dalam menanggapi kendala pembeli.",
          "Menilai kesantunan bahasa sebagai pendukung keberhasilan negosiasi."
        ],
      "stimulus": "Perkalian berulang dapat ditulis menjadi bentuk pangkat.",
      "image_path": null,
      "explanation": "Bentuknya 3^4 karena angka 3 muncul sebagai faktor sebanyak 4 kali."
    },
    {
      "id": "e4",
      "question": "Berikan satu contoh pola sederhana yang dapat ditulis dalam bentuk pangkat.",
      "rubric_points": [
          "Mengidentifikasi pasangan tuturan (salam-salam, tanya-jawab, tawar-menawar).",
          "Menganalisis efektivitas respon penjual dalam menanggapi kendala pembeli.",
          "Menilai kesantunan bahasa sebagai pendukung keberhasilan negosiasi."
        ],
      "stimulus": "Bilangan berpangkat sering dipakai dalam pola.",
      "image_path": null,
      "explanation": "Contoh: dua pilihan di setiap tahap selama 3 tahap dapat ditulis sebagai 2^3."
    },
    {
      "id": "e5",
      "question": "Mengapa 10^6 lebih praktis daripada menulis 1.000.000?",
      "rubric_points": [
          "Mengidentifikasi pasangan tuturan (salam-salam, tanya-jawab, tawar-menawar).",
          "Menganalisis efektivitas respon penjual dalam menanggapi kendala pembeli.",
          "Menilai kesantunan bahasa sebagai pendukung keberhasilan negosiasi."
        ],
      "stimulus": "Bilangan berpangkat membantu membuat penulisan lebih ringkas.",
      "image_path": null,
      "explanation": "10^6 menyatakan 10 dikalikan berulang 6 kali sehingga lebih ringkas untuk bilangan besar."
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
      "question": "Manakah yang merupakan pertidaksamaan linear dua variabel?",
      "level": "LOTS",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Persamaan linear dua variabel biasanya memuat tanda sama dengan, sedangkan pertidaksamaan memuat tanda <, >, <=, atau >=.",
      "image_path": null,
      "explanation": "Bentuk 2x - y > 4 adalah pertidaksamaan linear dua variabel karena memuat x, y, dan tanda lebih dari."
    },
    {
      "id": "p2",
      "question": "Manakah yang merupakan persamaan kuadrat?",
      "level": "LOTS",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Persamaan kuadrat memiliki bentuk umum ax^2 + bx + c = 0 dengan a tidak sama dengan 0.",
      "image_path": null,
      "explanation": "x^2 - 5x + 6 = 0 merupakan persamaan kuadrat karena pangkat tertinggi variabelnya adalah 2."
    },
    {
      "id": "p3",
      "question": "Manakah contoh fungsi kuadrat?",
      "level": "LOTS",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Fungsi kuadrat memiliki grafik berbentuk parabola.",
      "image_path": null,
      "explanation": "Fungsi kuadrat memiliki suku x^2 dengan koefisien tidak nol."
    },
    {
      "id": "p4",
      "question": "Manakah contoh persamaan eksponensial?",
      "level": "LOTS",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Persamaan eksponensial memuat variabel pada pangkat.",
      "image_path": null,
      "explanation": "Pada 2^x = 32, variabel x berada pada pangkat."
    },
    {
      "id": "p5",
      "question": "Akar-akar dari x^2 - 5x + 6 = 0 adalah ...",
      "level": "mots",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Akar-akar persamaan kuadrat dapat diperoleh dengan faktorisasi jika bentuknya mudah difaktorkan.",
      "image_path": null,
      "explanation": "x^2 - 5x + 6 = (x - 2)(x - 3), sehingga akarnya x = 2 dan x = 3."
    },
    {
      "id": "p6",
      "question": "Jika 3^(x+1) = 3^5, maka nilai x adalah ...",
      "level": "mots",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Persamaan eksponensial dengan basis sama dapat diselesaikan dengan menyamakan pangkatnya.",
      "image_path": null,
      "explanation": "Karena basis sama, x + 1 = 5 sehingga x = 4."
    },
    {
      "id": "p7",
      "question": "Untuk x^2 - 4x + 4 = 0, nilai diskriminannya adalah ...",
      "level": "mots",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Diskriminan persamaan kuadrat ax^2 + bx + c = 0 adalah D = b^2 - 4ac.",
      "image_path": null,
      "explanation": "D = (-4)^2 - 4(1)(4) = 16 - 16 = 0."
    },
    {
      "id": "p8",
      "question": "Titik (0,0) memenuhi pertidaksamaan x + y <= 5 karena ...",
      "level": "mots",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Daerah penyelesaian pertidaksamaan linear dapat diuji menggunakan titik tertentu.",
      "image_path": null,
      "explanation": "Substitusi (0,0) menghasilkan 0 <= 5, sehingga titik tersebut memenuhi pertidaksamaan."
    },
    {
      "id": "p9",
      "question": "Apa makna utama daerah penyelesaian dari sistem pertidaksamaan tersebut?",
      "level": "hots",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Sebuah daerah parkir memiliki batas x + y <= 20 dan 2x + y <= 30, dengan x dan y menyatakan banyak kendaraan dua jenis berbeda.",
      "image_path": null,
      "explanation": "Daerah penyelesaian sistem pertidaksamaan berisi semua pasangan nilai x dan y yang memenuhi seluruh batasan."
    },
    {
      "id": "p10",
      "question": "Makna titik puncak grafik fungsi tersebut adalah ...",
      "level": "hots",
      "answer": "B",
      "options": {
        "A": "Penjual menggunakan kalimat persuasif untuk menekan pembeli agar segera melakukan pembayaran.",
        "B": "Penjual menggunakan kalimat persuasif dengan menonjolkan keunggulan produk sebagai solusi atas kebutuhan pembeli.",
        "C": "Penjual menggunakan kalimat persuasif untuk menyembunyikan kekurangan harga produk yang mahal.",
        "D": "Penjual menggunakan kalimat persuasif untuk membatasi pilihan pembeli agar hanya fokus pada satu produk.",
        "E": "Penjual menggunakan kalimat persuasif untuk menunjukkan dominasi posisi penjual terhadap pembeli."
      },
      "stimulus": "Sebuah bola dilempar sehingga tinggi h terhadap waktu t dimodelkan dengan h(t) = -t^2 + 6t + 1.",
      "image_path": null,
      "explanation": "Pada fungsi kuadrat yang membuka ke bawah, titik puncak menyatakan nilai maksimum, yaitu tinggi maksimum bola."
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
