# -*- coding: utf-8 -*-
"""
Unified Microservice: Beta Agentic SR API + RAG Pipeline

Endpoints:
  -- Konten & RAG --
  POST /konten/generate          → Generate konten via state machine
  POST /sesi/summary             → Summary sesi belajar
  POST /siswa/quiz/essay         → Evaluasi jawaban essay
  POST /rag/rekomendasi          → Rekomendasi konten
  POST /rag/insight              → Insight motivasi siswa

  -- Pipeline --
  POST /pipeline/upload          → Upload satu PDF, jalankan full pipeline
  POST /pipeline/step            → Jalankan step tertentu (extract/describe/chunk/ingest)
  GET  /pipeline/job/{id}        → Cek status / hasil job
  GET  /pipeline/jobs            → Daftar semua job
  DELETE /pipeline/job/{id}      → Hapus job dari riwayat

  -- System --
  GET  /health                   → Health check

Cara menjalankan:
  pip install fastapi uvicorn python-multipart langchain jinja2 python-dotenv
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import uvicorn
import os
import traceback
import uuid
from typing import List, Any, Dict, Optional
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path

# Mematikan handler Ctrl+C bawaan Fortran (MKL/Sentence-Transformer)
# agar Uvicorn --reload tidak crash saat file berubah.
os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"

from fastapi import (
    BackgroundTasks, FastAPI, File, Form,
    HTTPException, UploadFile,
)
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from jinja2 import Environment, FileSystemLoader

from api_models import (
    GenerateRequest,
    SesiSummaryRequest, EssayEvalItem, RekomendasiRequest, InsightRequest,
)

from dotenv import load_dotenv
load_dotenv()

from graph import beta_graph
from llm import get_llm, get_eval_llm
from tools import clean_json_from_llm

# ── Import pipeline ──────────────────────────────────────────────────────────
try:
    from full_pipeline import PipelineConfig, run_full_pipeline
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & DIRECTORIES
# ══════════════════════════════════════════════════════════════════════════════

UPLOAD_DIR  = Path("uploads")          # PDF yang di-upload disimpan di sini
OUTPUT_DIR  = Path("pipeline_output")  # Output pipeline
CHUNKS_DIR  = Path("chunks")           # Output JSONL chunks

DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")
DEFAULT_OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "https://tipoff-errant-chatroom.ngrok-free.dev")
DEFAULT_DENSE_MODEL  = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
DEFAULT_SPARSE_MODEL = os.getenv("SPARSE_MODEL", "naver/splade-cocondenser-ensembledistil")

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CHUNKS_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE MODELS
# ══════════════════════════════════════════════════════════════════════════════

class JobStatus(str, Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    SUCCESS    = "success"
    FAILED     = "failed"


class StepName(str, Enum):
    EXTRACT  = "extract"
    DESCRIBE = "describe"
    CHUNK    = "chunk"
    INGEST   = "ingest"


class JobInfo(BaseModel):
    job_id:      str
    status:      JobStatus
    filename:    Optional[str]    = None
    step:        Optional[str]    = None
    created_at:  str
    updated_at:  str
    message:     Optional[str]    = None
    error:       Optional[str]    = None
    result:      Optional[Dict[str, Any]] = None


class PipelineParams(BaseModel):
    """Parameter opsional untuk pipeline."""
    step:             Optional[str] = Field(None, description="Step tertentu, kosong = semua step")
    qdrant_host:      str  = Field(os.getenv("QDRANT_HOST", "76.13.195.1"),           description="Host Qdrant")
    qdrant_port:      int  = Field(int(os.getenv("QDRANT_PORT", "6333")),             description="Port Qdrant")
    collection_name:  str  = Field(os.getenv("QDRANT_TEXT_COLLECTION", "Test_pipeline"), description="Nama collection Qdrant")
    collection_for_ekstraction: str= Field(os.getenv("QDRANT_PIPELINE_EKSTRACTION", "test_pipeline"), description="Nama collection Qdrant")
    chunk_size:       int  = Field(1000,                                              description="Ukuran chunk teks")
    force_reindex:    bool = Field(False,                                             description="Hapus & buat ulang collection")
    # Batasan halaman — 0 berarti tidak dibatasi (proses semua)
    start_page:       int  = Field(0, description="Halaman awal (1-based). 0 = dari halaman pertama")
    end_page:         int  = Field(0, description="Halaman akhir (inklusif). 0 = sampai halaman terakhir")
    # Metadata buku — masuk ke setiap chunk di Qdrant
    mata_pelajaran:   Optional[str] = Field(None, description="Mata pelajaran (mis. Biologi, Matematika)")
    id_kelas:         Optional[str] = Field(None, description="ID Kelas")
    jenjang:          Optional[str] = Field(None, description="Jenjang Kelas")
    id_guru:          Optional[str] = Field(None, description="ID Guru")
    vlm_model:        str  = Field(DEFAULT_OLLAMA_MODEL, description="Nama model Ollama untuk VLM")
    ollama_host:      str  = Field(DEFAULT_OLLAMA_HOST,  description="URL server Ollama")
    dense_model:      str  = Field(DEFAULT_DENSE_MODEL,  description="Model dense embedding")
    sparse_model:     str  = Field(DEFAULT_SPARSE_MODEL, description="Model sparse")


# ══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY JOB STORE
# ══════════════════════════════════════════════════════════════════════════════

_jobs: Dict[str, JobInfo] = {}


def _create_job(filename: Optional[str] = None, step: Optional[str] = None) -> JobInfo:
    now = datetime.now().isoformat()
    job = JobInfo(
        job_id     = str(uuid.uuid4()),
        status     = JobStatus.PENDING,
        filename   = filename,
        step       = step,
        created_at = now,
        updated_at = now,
    )
    _jobs[job.job_id] = job
    return job


def _update_job(job_id: str, **kwargs) -> None:
    if job_id in _jobs:
        job = _jobs[job_id]
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = datetime.now().isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNER (background task)
# ══════════════════════════════════════════════════════════════════════════════

def _run_pipeline_task(job_id: str, pdf_path: Path, params: PipelineParams) -> None:
    """Dijalankan sebagai background task."""
    if not PIPELINE_AVAILABLE:
        _update_job(job_id, status=JobStatus.FAILED,
                    error="full_pipeline.py tidak ditemukan. Pastikan file ada di direktori yang sama.")
        return

    _update_job(job_id, status=JobStatus.RUNNING, message="Pipeline dimulai...")

    try:
        cfg = PipelineConfig(
            input_pdf         = pdf_path,
            output_base       = OUTPUT_DIR,
            outputs_root      = OUTPUT_DIR / "outputs",
            qdrant_host       = params.qdrant_host,
            qdrant_port       = params.qdrant_port,
            collection_name   = params.collection_for_ekstraction,
            chunk_size        = params.chunk_size,
            force_reindex     = params.force_reindex,
            start_page        = params.start_page,
            end_page          = params.end_page,
            mata_pelajaran    = params.mata_pelajaran,
            id_kelas          = params.id_kelas,
            jenjang           = params.jenjang,
            id_guru           = params.id_guru,
            vlm_model_id      = params.vlm_model,
            ollama_host       = params.ollama_host,
            dense_model_name  = params.dense_model,
            sparse_model_name = params.sparse_model,
            skip_existing     = False,
        )

        run_full_pipeline(cfg, step=params.step if params.step else None)

        # Hitung artefak yang dihasilkan
        json_files  = list(OUTPUT_DIR.rglob("*_structure.json"))
        md_files    = list(OUTPUT_DIR.rglob("*_FINAL_PAGINATED.md"))
        jsonl_files = list(cfg.chunks_dir.glob("*.jsonl"))
        total_chunks = sum(
            sum(1 for line in open(f, encoding="utf-8") if line.strip())
            for f in jsonl_files
        )

        _update_job(
            job_id,
            status  = JobStatus.SUCCESS,
            message = "Pipeline selesai.",
            result  = {
                "pdf_file":          pdf_path.name,
                "step_run":          params.step if params.step else "all",
                "json_files":        [str(p) for p in json_files],
                "markdown_files":    [str(p) for p in md_files],
                "jsonl_files":       [str(p) for p in jsonl_files],
                "total_chunks":      total_chunks,
                "qdrant_collection": params.collection_for_ekstraction,
            },
        )

    except Exception as exc:
        _update_job(
            job_id,
            status  = JobStatus.FAILED,
            message = "Pipeline gagal.",
            error   = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# APP SETUP
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tidak perlu preload model lokal karena berjalan dalam proxy mode
    yield
    print("Shutting down...")

app = FastAPI(
    title       = "Beta Agentic SR API + RAG Pipeline",
    description = "Unified microservice: Konten/RAG endpoints + Pipeline PDF → Qdrant (Docling + VLM + BGE-M3 + SPLADE).",
    version     = "4.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")))
llm = get_llm()
eval_llm = get_eval_llm()


def load_prompt(template_name: str, **kwargs) -> str:
    template = env.get_template(template_name)
    return template.render(**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["System"])
def health_check():
    """Cek apakah service berjalan normal."""
    return {
        "status":             "ok",
        "pipeline_available": PIPELINE_AVAILABLE,
        "upload_dir":         str(UPLOAD_DIR.resolve()),
        "output_dir":         str(OUTPUT_DIR.resolve()),
        "chunks_dir":         str(CHUNKS_DIR.resolve()),
        "active_jobs":        sum(1 for j in _jobs.values() if j.status == JobStatus.RUNNING),
        "total_jobs":         len(_jobs),
        "timestamp":          datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# KONTEN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/konten/generate", tags=["Konten"])
async def generate_konten(req: GenerateRequest):
    try:
        # Menyiapkan State Awal untuk Graf
        initial_state = {
            "request_params": req.model_dump(),
            "tipe": req.tipe,
            "level": req.level,
            "revision_count": 0,
            "instruksi_revisi": req.instruksi_revisi
        }
        
        # Mengeksekusi State Machine
        final_state = await beta_graph.ainvoke(initial_state)
        final_payload = final_state["final_payload"]
        
        # Pertahankan konten_id jika diberikan dari klien (kecuali untuk quiz dan essay)
        if req.konten_id and req.tipe not in ["quiz_pg", "quiz_essay", "pretest"]:
            final_payload["konten_id"] = req.konten_id
            
        return final_payload
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GEN_ERROR: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY SESI (Tim 3 RAG)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/sesi/summary", tags=["Sesi"])
def generate_summary(req: SesiSummaryRequest):
    try:
        prompt = load_prompt(
            "summary.j2",
            req=req.model_dump()
        )
        sys_msg = SystemMessage(content="Kamu adalah AI yang merangkum hasil belajar siswa selama satu sesi menjadi JSON.")
        res = llm.invoke([sys_msg, HumanMessage(content=prompt)])
        content = clean_json_from_llm(res.content)
        
        return {
            "summary_text": content.get("summary_text", "Gagal menghasilkan summary.")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SUMMARY_ERR: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# QUIZ EVALUATION ENDPOINTS (Dipanggil BE)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/siswa/quiz/essay", tags=["Quiz"])
def submit_essay(req: List[EssayEvalItem]):
    try:
        evaluasi_hasil = []
        total_skor = 0
        sys_msg = SystemMessage(content="Kamu adalah Guru Penilai Esai JSON.")
        
        for item in req:
            usr_prompt = load_prompt(
                "essay_evaluation.j2",
                soal=item.soal,
                rubrik=item.rubrik,
                jawaban_siswa=item.jawaban_siswa,
                stimulus=item.stimulus,
                penjelasan=item.penjelasan
            )
            res = eval_llm.invoke([sys_msg, HumanMessage(content=usr_prompt)])
            hasil = clean_json_from_llm(res.content)
            
            skor = hasil.get("skor", 0)
            total_skor += skor
            evaluasi_hasil.append(hasil)
            
        return {"total_skor": total_skor}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EVAL_ERR: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# RAG SERVICES ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/rag/rekomendasi", tags=["RAG"])
def rekomendasi(req: RekomendasiRequest):
    try:
        prompt = load_prompt(
            "rekomendasi.j2",
            available=req.available,
            in_progress=req.in_progress_ids,
            complete=req.complete_ids
        )
        sys_msg = SystemMessage(content="Kamu adalah AI Recommender JSON.")
        res = llm.invoke([sys_msg, HumanMessage(content=prompt)])
        content = clean_json_from_llm(res.content)
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"REKOM_ERR: {str(e)}")

@app.post("/rag/insight", tags=["RAG"])
def insight(req: InsightRequest):
    try:
        prompt = load_prompt(
            "insight.j2",
            nama=req.nama,
            streak=req.streak,
            total_topik=req.total_topik,
            poin=req.total_poin_kuiz,
            durasi=req.total_durasi_menit
        )
        sys_msg = SystemMessage(content="Kamu adalah Penyedia Motivasi Pendek JSON.")
        usr_msg = HumanMessage(content=prompt)
        res = llm.invoke([sys_msg, usr_msg])
        content = clean_json_from_llm(res.content)
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"INSIGHT_ERR: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/pipeline/upload", response_model=JobInfo, status_code=202, tags=["Pipeline"])
async def upload_and_run(
    background_tasks: BackgroundTasks,
    file:             UploadFile = File(..., description="File PDF yang akan diproses"),
    # Parameter opsional
    step:             Optional[str] = Form(None),
    start_page:       int  = Form(0, description="Halaman awal (1-based). 0 = dari awal"),
    end_page:         int  = Form(0, description="Halaman akhir (inklusif). 0 = sampai akhir"),
    mata_pelajaran:   Optional[str] = Form(None, description="Mata pelajaran (mis. Biologi)"),
    id_kelas:         Optional[str] = Form(None, description="Tingkat kelas"),
    jenjang:          Optional[str] = Form(None, description="Jenjang Kelas (mis. X, XI, XII)"),
    id_guru:          Optional[str] = Form(None, description="ID Guru"),
):
    """
    Upload satu file PDF dan jalankan pipeline RAG secara asinkron.

    - Pipeline berjalan di background; response langsung dikembalikan beserta `job_id`.
    - Pantau status via `GET /pipeline/job/{job_id}`.
    - `step` bisa diisi `extract`, `describe`, `chunk`, atau `ingest` untuk menjalankan
      satu step saja. Kosongkan untuk menjalankan semua step.
    """
    # Validasi tipe file
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima.")

    # Simpan file yang di-upload
    safe_name = Path(file.filename).name  # Hindari path traversal
    dest_path = UPLOAD_DIR / safe_name
    try:
        with open(dest_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan file: {exc}")

    params = PipelineParams(
        step            = step,
        start_page      = start_page,
        end_page        = end_page,
        mata_pelajaran  = mata_pelajaran,
        id_kelas        = id_kelas,
        jenjang         = jenjang,
        id_guru         = id_guru,
    )

    job = _create_job(filename=safe_name, step=step if step else "all")

    # Jalankan pipeline di background (non-blocking)
    background_tasks.add_task(_run_pipeline_task, job.job_id, dest_path, params)

    return job


# ── Run Specific Step (tanpa upload ulang) ─────────────────────────────────

@app.post("/pipeline/step", response_model=JobInfo, status_code=202, tags=["Pipeline"])
async def run_step(
    background_tasks: BackgroundTasks,
    params: PipelineParams,
    filename: Optional[str] = None,
):
    """
    Jalankan step tertentu dari pipeline tanpa upload PDF baru.

    - Berguna untuk re-run step yang gagal, atau melanjutkan dari tengah pipeline.
    - `filename`: nama file PDF yang sudah ada di folder `uploads/`.
      Kosongkan jika hanya menjalankan `chunk` atau `ingest` (tidak butuh PDF baru).
    """
    pdf_path = None
    if filename:
        pdf_path = UPLOAD_DIR / filename
        if not pdf_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File '{filename}' tidak ditemukan di folder uploads. "
                       f"Upload dulu via POST /pipeline/upload.",
            )

    job = _create_job(filename=filename, step=params.step.value if params.step else "all")

    if pdf_path is None:
        # Buat dummy path supaya runner tidak crash; runner akan skip jika tidak ada PDF
        pdf_path = UPLOAD_DIR / "placeholder.pdf"

    background_tasks.add_task(_run_pipeline_task, job.job_id, pdf_path, params)
    return job


# ── Job Status ────────────────────────────────────────────────────────────────

@app.get("/pipeline/job/{job_id}", response_model=JobInfo, tags=["Jobs"])
def get_job(job_id: str):
    """Ambil status dan hasil dari sebuah job berdasarkan `job_id`."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' tidak ditemukan.")
    return job


@app.get("/pipeline/jobs", response_model=List[JobInfo], tags=["Jobs"])
def list_jobs(status: Optional[JobStatus] = None):
    """
    Daftar semua job.

    - Filter opsional dengan query param `?status=running`, `?status=success`, dll.
    """
    jobs = list(_jobs.values())
    if status:
        jobs = [j for j in jobs if j.status == status]
    # Urutkan terbaru dulu
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs


@app.delete("/pipeline/job/{job_id}", tags=["Jobs"])
def delete_job(job_id: str):
    """Hapus job dari riwayat (hanya riwayat; file output tidak dihapus)."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' tidak ditemukan.")
    job = _jobs.pop(job_id)
    return {"message": f"Job '{job_id}' dihapus.", "filename": job.filename}


# ══════════════════════════════════════════════════════════════════════════════
# STATIC FILES
# ══════════════════════════════════════════════════════════════════════════════

# Serve extraction folder for images
EXTRACTION_BASE_DIR = Path(__file__).resolve().parent / "extraction"
if EXTRACTION_BASE_DIR.exists():
    app.mount("/extraction", StaticFiles(directory=str(EXTRACTION_BASE_DIR)), name="extraction")


# ══════════════════════════════════════════════════════════════════════════════
# LANGSMITH CONFIG
# ══════════════════════════════════════════════════════════════════════════════

os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_PROJECT"] = "beta-agentic"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN (untuk development)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)