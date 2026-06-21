# Analisis Keseluruhan Sistem: Beta Agentic SR API & RAG Pipeline (Updated)

Berdasarkan penelusuran terhadap direktori `c:\Personal\aitf\demooo\Agentic_RAG` serta pembaruan (*pull*) terbaru dari *branch main*, berikut adalah hasil analisis komprehensif mengenai arsitektur, fungsionalitas, komponen utama, dan perbaikan performa terbaru dari sistem.

## 1. Ringkasan Eksekutif
Sistem ini merupakan solusi **Unified Microservice** yang menggabungkan kemampuan **Agentic (LLM orchestration)** dan **RAG (Retrieval-Augmented Generation) Pipeline** yang difokuskan untuk sistem edukasi (EdTech). Sistem memproses dokumen materi pelajaran (seperti buku cetak/PDF), mengubahnya menjadi struktur *knowledge base* (teks dan multimodal), lalu menyediakan endpoint API pintar untuk:
- Membuat konten pembelajaran secara otomatis (kuis, materi bacaan, mindmap, flashcard).
- Melakukan evaluasi esai siswa.
- Memberikan rekomendasi pembelajaran dan motivasi berdasarkan riwayat performa siswa.

## 2. Arsitektur Sistem
Sistem ini dirancang dengan pendekatan mikroservis, memisahkan lapisan orkestrasi logika/AI dengan lapisan eksekusi model ML yang berat.

### A. Layanan Utama (`agentic_api`)
Layanan ini berjalan menggunakan **FastAPI** (`main.py`) dan bertindak sebagai otak utama.
- **Orkestrasi Agentic:** Menggunakan `LangGraph` (`graph.py`) untuk membangun *state machine* dalam meng-generate konten.
- **Pipeline RAG Asinkron:** Menyediakan endpoint untuk menerima file PDF dan memprosesnya secara *background job* menggunakan *pipeline* ekstraksi, *chunking*, dan *ingestion* ke Qdrant.
- **Tools RAG & Optimasi:** Menggunakan `tools.py` (dan skrip ekuivalen `tools_rag_team.py`) untuk memproses pencarian Qdrant yang sudah dioptimasi untuk *caching* dan pembatasan muatan data (payload).
- **Template Berbasis Jinja2:** Menggunakan `templates/` untuk memisahkan *prompt template* dari *source code*.

### B. Layanan Model (`model_api`)
Berjalan menggunakan **FastAPI** terpisah (`model_api.py`) khusus menangani model *Machine Learning* yang berat:
- **Embedding Dense:** BAAI/bge-m3.
- **Embedding Sparse:** naver/splade-cocondenser-ensembledistil.
- **Reranking:** Cross-encoder untuk mengurutkan hasil pencarian.
- **Ekstraksi PDF via Docling:** Mengonversi PDF kompleks menjadi teks, gambar, formula, dan tabel secara terstruktur.

### C. Folder Data & Hasil
- **`extraction/`**: Berisi folder *output multimodal* hasil ekstraksi dari beragam buku kurikulum sekolah. 
- **`pipeline_output/` & `chunks/`**: Tempat menyimpan file perantara (JSONL/Markdown) yang digunakan selama proses *ingestion* ke Qdrant.

## 3. Alur Kerja Utama (Workflows)

### Workflow 1: RAG Data Ingestion (Pipeline)
1. **Upload:** File PDF diunggah.
2. **Ekstraksi Docling:** Dokumen dipisahkan antara paragraf, gambar, dan tabel.
3. **Deskripsi VLM:** Gambar/grafik dianalisis menggunakan *Vision Language Model* lokal (Ollama - qwen2.5vl:7b) untuk dibuatkan *caption* konten.
4. **Chunking & Embedding:** Teks dipecah menjadi *chunk*, di-embed menggunakan *Dense* dan *Sparse model*.
5. **Ingestion:** Hasil disimpan ke **Qdrant Vector Database**.

### Workflow 2: Generate Konten Pembelajaran (Agentic)
1. Permintaan masuk via `/konten/generate`.
2. Memicu *state machine* LangGraph (`beta_graph`).
3. State machine melakukan: *Retrieve context* dari Qdrant → Menyusun prompt LLM → Mengenerate respons → *Evaluator LLM* memvalidasi kualitas JSON LLM (apakah format rusak) → Menyusun `final_payload` dengan aset visual.

## 4. Pembaruan dan Optimasi Terbaru
Berdasarkan *commit* terbaru, sistem ini telah mendapatkan beberapa pembaruan signifikan terkait performa:
1. **Optimasi RAG Query Caching:** Pada modul retrieval (`tools_rag_team.py`), ditambahkan variabel lokal `_query_embed_cache` dengan TTL (Time To Live) 5 menit. Hal ini berfungsi menghindari *encode* vektor berulang kali untuk pertanyaan/kueri yang sama.
2. **Pengurangan Payload Memori di Qdrant:** Secara eksplisit menambahkan pengecualian filter `{"exclude": ["has_visual_content"]}` pada operasi *scroll* atau pencarian biasa di Qdrant. Ini mencegah data base64 gambar yang besar termuat sia-sia ke dalam memori jika sistem hanya membutuhkan teks *chunk* untuk BM25 atau Dense search.
3. **Versi Cache BM25:** Adanya variabel `BM25_CACHE_VERSION` untuk memvalidasi *cache* index secara lebih rapi bila terdapat perubahan format *payload*.
4. **Penyajian Gambar Visual (Multimodal):** File `graph.py` diperbarui sehingga ketika LLM melakukan *Retrieve*, sistem akan ikut merakit data gambar Base64 dari metadata. Hasil akhirnya akan dimasukkan secara langsung ke kunci `"visuals"` di dalam *payload JSON*, memudahkan *frontend* menampilkan gambar referensi dari buku tanpa perlu *request* terpisah.
5. **Perbaikan *Hardcoded* Qdrant Config (Bug Fix):** Menemukan dan menambal celah pada `agentic_api/full_pipeline.py` di mana alamat IP Qdrant tertulis secara statis (*hardcoded*). Kini `PipelineConfig` memanggil *host*, *port*, dan *collection* menggunakan nilai dari variabel `environment` secara dinamis, sehingga sinkron dengan konfigurasi sistem secara menyeluruh.

## 5. Stack Teknologi
- **Backend:** FastAPI, Uvicorn.
- **LLM / Agentic:** LangChain, LangGraph.
- **Local Models Server:** Ollama (untuk VLM & evaluasi lokal), Llama-cpp (melalui *notebook sandbox* tambahan).
- **ML / NLP Libraries:** Sentence-Transformers (BGE-M3), SPLADE, Docling.
- **Vector Database:** Qdrant.
- **Templating:** Jinja2.

## 6. Kesimpulan
Sistem *Agentic RAG* yang dibangun memiliki stabilitas produksi yang sangat baik. Pemisahan antara `agentic_api` dan `model_api` mengurangi *bottleneck* komputasi. Penambahan optimasi tingkat lanjut (seperti *query embedding caching*, *payload memory limiting*, dan implementasi hybrid search mode tersimpan/cadangan) membuat sistem ini mampu berjalan jauh lebih efisien dibandingkan iterasi sebelumnya. Sistem ini juga sudah berstatus *multimodal-ready*, mengingat aset gambar dari buku pelajaran kini terintegrasi langsung dengan luaran (output) LLM ke sisi *frontend*.
