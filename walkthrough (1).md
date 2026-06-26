# Walkthrough: Deployment Sistem Agentic RAG

Setelah menganalisis repositori ini, sistem ini memiliki arsitektur **microservices** yang terbagi menjadi dua bagian utama:
1. **Agentic API** (`agentic_api/`): Merupakan aplikasi utama (FastAPI di port 8002) yang mengekspos endpoint seperti pembuatan soal, evaluasi essay, dan pipeline proses RAG dokumen. Bagian ini juga mengorkestrasi *background tasks* menggunakan **Celery** dan **Redis**.
2. **Model API** (`model_api/`): Microservice terpisah (FastAPI di port 8003) yang bertanggung jawab untuk tugas komputasi berat (ML), seperti *Dense/Sparse Embeddings*, *Reranking*, dan ekstraksi dokumen PDF menggunakan *Docling*. Layanan ini sangat disarankan untuk berjalan di sistem yang memiliki GPU.

Selain itu, sistem membutuhkan layanan eksternal tambahan:
- **Redis**: Sebagai message broker dan result backend untuk Celery.
- **Qdrant**: Sebagai Vector Database tempat knowledge-base tersimpan.

Berikut adalah langkah-langkah detail untuk proses deployment lokal dan production.

---

## 1. Deployment Lokal (Development)

Deployment lokal cocok untuk pengembangan atau testing fitur tanpa perlu menggunakan Docker untuk seluruh layanan. 

### Persiapan
- Python 3.10+
- Docker (Untuk menjalankan Redis)
- Akses Qdrant (bisa Qdrant Cloud atau via local docker)

### Langkah-langkah

**A. Jalankan Redis Lokal**
Gunakan Docker untuk memutar container Redis yang dibutuhkan oleh Celery.
```bash
docker run -d --name redis_local -p 6379:6379 redis:7-alpine
```

**B. Siapkan Environment**
Duplikat file konfigurasi dan sesuaikan isinya:
```bash
cp .env.example .env
```
Pada `.env`, ubah *values* berikut:
- `REDIS_URL=redis://localhost:6379/0`
- `QDRANT_HOST` dan konfigurasi API keys untuk LLM Provider.
- `MODEL_API_URL=http://localhost:8003` (jika Model API juga Anda jalankan secara lokal).

**C. Jalankan Model API (Port 8003)**
Sebaiknya gunakan environment Python yang berbeda jika versi package rawan bentrok.
```bash
cd model_api
pip install -r requirements.txt
uvicorn model_api:app --host 0.0.0.0 --port 8003 --reload
```

**D. Jalankan Agentic API (Port 8002)**
Buka tab terminal baru di root folder:
```bash
cd agentic_api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

**E. Jalankan Worker Celery**
Worker bertugas untuk memproses background task (seperti generasi konten dan pipeline PDF). Parameter *pool* dan *concurrency* Celery **sangat bergantung pada OS yang digunakan**:

- **Untuk Windows (Local Dev):**  
  Sistem operasi Windows memiliki limitasi kompatibilitas dengan *prefork multiprocessing* bawaan Celery. Anda wajib menggunakan `--pool=solo` agar stabil (dieksekusi satu persatu secara sinkronus).
  ```bash
  cd agentic_api
  celery -A celery_app worker --loglevel=info --pool=solo -Q celery,pipeline
  ```

- **Untuk Linux / macOS (Local Dev):**  
  Mendukung penuh *multiprocessing*. Gunakan `--concurrency` (misal 2 atau 4) agar beberapa *task* berjalan paralel.
  ```bash
  cd agentic_api
  celery -A celery_app worker --loglevel=info --concurrency=2 -Q celery,pipeline
  ```

**F. Jalankan Flower (Dashboard Celery) - Opsional**
Untuk memantau antrean task secara visual secara real-time, buka terminal baru:
```bash
cd agentic_api
celery -A celery_app flower --port=5555
```

> [!NOTE]  
> Anda kini dapat mengakses dokumentasi API utama secara lokal di http://localhost:8002/docs dan dashboard monitoring Celery di http://localhost:5555.

---

## 2. Deployment Production (Server / VM)

Untuk production, *Agentic API* sudah dilengkapi file `docker-compose.yml` yang mengatur semuanya dengan standar *production-ready* menggunakan gunicorn worker, resource limits, dan fitur monitoring.

> [!WARNING]  
> **Pisahkan Model API di Server GPU!**
> Karena fungsi ekstraksi (Docling) dan Embeddings sangat memakan *resources*, disarankan mendeploy `model_api` di instance terpisah yang mendukung GPU (contoh: RunPod, VM Cloud dengan GPU). Pastikan URL dari GPU server ini di-inject ke dalam file `.env` di main server lewat variabel `MODEL_API_URL`.

### Langkah-langkah

**A. Konfigurasi Environment Server**
Clone repository di server utama Anda. Konfigurasikan `.env` yang berada di *root direktori*:
```bash
cp .env.example .env
nano .env
```
Pastikan pengaturan berikut disesuaikan:
- `MODEL_API_URL=http://<IP_GPU_SERVER>:8003`
- Konfigurasi Qdrant, dan LLM Providers.
- `REDIS_URL` tidak perlu diubah secara manual jika menggunakan compose (sudah merujuk ke namespace `redis:6379`).

**B. Build dan Jalankan Docker Compose**
Masuk ke direktori `agentic_api` karena file konfigurasi docker berada di sana. Container API akan mem-mount `.env` dari direktori parent-nya.
```bash
cd agentic_api
docker-compose up -d --build
```

**C. Memantau Status Layanan**
Layanan Docker Compose ini akan secara otomatis mengangkat 4 services:
- `redis`: Server redis
- `agentic_api`: Core sistem pada port `8002`
- `celery_worker`: Pekerja *background task*. Karena *container* berjalan dengan base image Linux, worker ini sepenuhnya menggunakan *prefork multiprocessing* dengan `--concurrency=2`. Dikarenakan tugas RAG (seperti memuat model Docling dan *embedding*) memakan *footprint* memori besar, limitasi resource secara spesifik di-set ke **12GB RAM** pada *docker-compose.yml* untuk mencegah *Out-of-Memory* (OOM) crash.
- `flower`: Dashboard monitoring Celery

Untuk melihat log apakah layanan sukses berjalan:
```bash
docker-compose logs -f agentic_api
docker-compose logs -f celery_worker
```

> [!TIP]  
> Untuk memantau visualisasi queue (antrean) dan keberhasilan task PDF Pipeline dari Celery, Anda bisa membuka Dashboard Flower yang ter-expose pada http://<IP_SERVER_ANDA>:5555
