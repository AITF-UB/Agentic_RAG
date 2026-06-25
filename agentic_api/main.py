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

  -- Chat Memory --
  POST /chat-memory/ingest       → Simpan pasangan Q&A ke Qdrant
  POST /chat-memory/retrieve     → Ambil histori chat relevan

  -- System --
  GET  /health                   → Health check

Cara menjalankan:
  pip install fastapi uvicorn python-multipart langchain jinja2 python-dotenv
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import uvicorn
import os
import sys
import traceback
import threading
import uuid
from typing import List, Any, Dict, Optional
from enum import Enum
from datetime import datetime, timedelta
from cachetools import LRUCache
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

# ── LangSmith — set sebelum import LangChain/LangGraph agar tracing aktif ────
import os as _os
_ls_project = _os.getenv("LANGSMITH_PROJECT", "agentic-workflow")
_os.environ["LANGSMITH_PROJECT"]  = _ls_project
_os.environ["LANGSMITH_ENDPOINT"] = _os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
del _os, _ls_project  # Hapus variabel sementara agar tidak polusi namespace

from chat_memory.schemas import (
    IngestChatRequest,
    RetrieveChatRequest,
)
from chat_memory.dependencies import (
    embedding_service,
    qdrant_service,
    chunking_service,
)

from graph import beta_graph
from llm import get_llm, get_eval_llm
from tools import clean_json_from_llm

# ── Pastikan agentic_api/ ada di sys.path (agar import berfungsi dari mana pun) ──
_THIS_DIR = Path(__file__).parent.resolve()
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# ── Import pipeline ──────────────────────────────────────────────────────────
try:
    from full_pipeline import (
        PipelineConfig, run_full_pipeline,
        DEFAULT_VLM_MODEL, DEFAULT_VLM_HOST, DEFAULT_DENSE_MODEL, DEFAULT_SPARSE_MODEL,
    )
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    DEFAULT_VLM_MODEL   = os.getenv("VLM_MODEL", "ub-sr-all")
    DEFAULT_VLM_HOST    = os.getenv("VLM_HOST", "https://providers-else-hear-wheel.trycloudflare.com")
    DEFAULT_DENSE_MODEL  = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
    DEFAULT_SPARSE_MODEL = os.getenv("SPARSE_MODEL", "naver/splade-cocondenser-ensembledistil")

# ── Import Celery task ────────────────────────────────────────────────────────
try:
    from celery_app import celery_app
    from tasks.pipeline_task import run_pipeline as celery_run_pipeline
    # Verifikasi Redis benar-benar bisa dikoneksi (bukan hanya import berhasil)
    celery_app.backend.client.ping()
    CELERY_AVAILABLE = True
    print("[Celery] Redis reachable — Celery mode aktif.")
except Exception:
    CELERY_AVAILABLE = False
    celery_app = None
    celery_run_pipeline = None
    print("[Celery] Redis tidak tersedia — fallback ke BackgroundTask.")


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & DIRECTORIES
# ══════════════════════════════════════════════════════════════════════════════

UPLOAD_DIR  = Path("uploads")          # PDF yang di-upload disimpan di sini
OUTPUT_DIR  = Path("pipeline_output")  # Output pipeline
CHUNKS_DIR  = Path("chunks")           # Output JSONL chunks

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
    buku_id:          Optional[str] = Field(None, description="ID unik buku (UUID, di-generate/diinput saat upload)")
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
    vlm_model:        str  = Field(DEFAULT_VLM_MODEL, description="Nama model VLM (OpenAI-compatible API)")
    ollama_host:      str  = Field(DEFAULT_VLM_HOST,  description="Base URL server VLM (OpenAI-compatible)")
    dense_model:      str  = Field(DEFAULT_DENSE_MODEL,  description="Model dense embedding")
    sparse_model:     str  = Field(DEFAULT_SPARSE_MODEL, description="Model sparse")


# ══════════════════════════════════════════════════════════════════════════════
# JOB STORE — Celery Result Backend (Redis) dengan fallback in-memory
# ══════════════════════════════════════════════════════════════════════════════

# Fallback in-memory store — digunakan jika Celery tidak tersedia.
# Menggunakan LRUCache (max 500 item) untuk mencegah memory leak saat server
# berjalan berhari-hari. Job lama yang paling jarang diakses akan otomatis
# terhapus ketika cache penuh. (Hanya berlaku saat Celery tidak aktif).
_jobs: LRUCache = LRUCache(maxsize=500)
_jobs_lock = threading.Lock()


def _celery_state_to_job_status(state: str) -> JobStatus:
    """Map Celery task state ke JobStatus enum."""
    mapping = {
        "PENDING":  JobStatus.PENDING,
        "RECEIVED": JobStatus.PENDING,
        "STARTED":  JobStatus.RUNNING,
        "PROGRESS": JobStatus.RUNNING,
        "SUCCESS":  JobStatus.SUCCESS,
        "FAILURE":  JobStatus.FAILED,
        "RETRY":    JobStatus.RUNNING,
        "REVOKED":  JobStatus.FAILED,
    }
    return mapping.get(state, JobStatus.PENDING)


def _celery_result_to_job_info(task_id: str, filename: Optional[str] = None, step: Optional[str] = None) -> Optional[JobInfo]:
    """Baca status task dari Celery result backend dan konversi ke JobInfo."""
    if not CELERY_AVAILABLE or celery_app is None:
        return None
    try:
        result = celery_app.AsyncResult(task_id)
        state  = result.state
        meta   = result.info or {}

        status    = _celery_state_to_job_status(state)
        error_msg = None
        job_result = None

        if state == "SUCCESS":
            job_result = meta if isinstance(meta, dict) else {}
        elif state == "FAILURE":
            error_msg = str(meta) if not isinstance(meta, dict) else meta.get("exc_message", str(meta))

        message = None
        if isinstance(meta, dict):
            message = meta.get("message")

        now = datetime.now().isoformat()
        return JobInfo(
            job_id     = task_id,
            status     = status,
            filename   = filename or (meta.get("filename") if isinstance(meta, dict) else None),
            step       = step or (meta.get("step") if isinstance(meta, dict) else None),
            created_at = (meta.get("started_at") if isinstance(meta, dict) else None) or now,
            updated_at = now,
            message    = message,
            error      = error_msg,
            result     = job_result,
        )
    except Exception:
        return None


def _create_job(filename: Optional[str] = None, step: Optional[str] = None) -> JobInfo:
    """Buat JobInfo baru (in-memory fallback saat Celery tidak tersedia)."""
    now = datetime.now().isoformat()
    job = JobInfo(
        job_id     = str(uuid.uuid4()),
        status     = JobStatus.PENDING,
        filename   = filename,
        step       = step,
        created_at = now,
        updated_at = now,
    )
    with _jobs_lock:
        _jobs[job.job_id] = job
    return job


def _update_job(job_id: str, **kwargs) -> None:
    """Update JobInfo di in-memory store (fallback)."""
    with _jobs_lock:
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
            buku_id           = params.buku_id,
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

        # Normalisasi source_file agar tetap informatif
        # Logika identik dengan _normalize_source_file_for_qdrant di full_pipeline.py
        source_file_raw = pdf_path.stem  # mis. "Biologi_Kelas_X"
        source_file_normalized = source_file_raw.lower()
        for _sfx in ("_chunks", "_final_paginated", "_structure"):
            if source_file_normalized.endswith(_sfx):
                source_file_normalized = source_file_normalized[: -len(_sfx)]

        _update_job(
            job_id,
            status  = JobStatus.SUCCESS,
            message = "Pipeline selesai.",
            result  = {
                "pdf_file":          pdf_path.name,
                "buku_id":           params.buku_id,
                "source_file":       source_file_normalized,
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

from fastapi.security import APIKeyHeader
from fastapi import Security, Depends

API_KEY = os.getenv("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if API_KEY and api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API Key"
        )
    return api_key

app = FastAPI(
    title       = "Beta Agentic SR API + RAG Pipeline",
    description = "Unified microservice: Konten/RAG endpoints + Pipeline PDF → Qdrant (Docling + VLM + BGE-M3 + SPLADE).",
    version     = "4.0",
    lifespan    = lifespan,
    dependencies=[Depends(verify_api_key)]
)

import traceback
from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print(tb)
    return PlainTextResponse(str(tb), status_code=500)

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

# ── Concurrency limiter untuk konten generation ───────────────────────────────
# Batasi max concurrent LLM generation agar LLM provider tidak overload.
# Jika ada request ke-11, client akan menunggu sampai ada slot kosong.
_MAX_CONCURRENT_GENERATION = int(os.getenv("MAX_CONCURRENT_GENERATION", "30"))
_generation_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_GENERATION)


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
        "status":                      "ok",
        "pipeline_available":          PIPELINE_AVAILABLE,
        "celery_available":            CELERY_AVAILABLE,
        "upload_dir":                  str(UPLOAD_DIR.resolve()),
        "output_dir":                  str(OUTPUT_DIR.resolve()),
        "chunks_dir":                  str(CHUNKS_DIR.resolve()),
        "active_jobs":                 sum(1 for j in _jobs.values() if j.status == JobStatus.RUNNING),
        "total_jobs":                  len(_jobs),
        "max_concurrent_generation":   _MAX_CONCURRENT_GENERATION,
        "current_concurrent_generation": _MAX_CONCURRENT_GENERATION - _generation_semaphore._value,
        "timestamp":                   datetime.now().isoformat(),
    }


# ================================================================
# KONTEN ENDPOINTS (Celery / Async)
# ================================================================

def _run_generate_task_fallback(job_id: str, initial_state: dict):
    """Fallback in-process untuk /konten/generate jika Celery tidak tersedia.
    
    Dijalankan di thread pool FastAPI BackgroundTasks. Menggunakan asyncio.run()
    yang lebih efisien daripada membuat event loop manual per-request.
    """
    async def _invoke():
        return await beta_graph.ainvoke(initial_state)

    try:
        final_state = asyncio.run(_invoke())
        final_payload = final_state.get("final_payload", {})
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].status = JobStatus.SUCCESS
                _jobs[job_id].result = final_payload
                _jobs[job_id].updated_at = datetime.now().isoformat()
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].status = JobStatus.FAILED
                _jobs[job_id].error = error_msg
                _jobs[job_id].updated_at = datetime.now().isoformat()

@app.post("/konten/generate", response_model=JobInfo, tags=["Konten"])
async def generate_konten(req: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Generate konten (Soal/Bacaan) secara asynchronous.
    Mengembalikan job_id untuk di-polling menggunakan `GET /job/{job_id}`.
    """
    try:
        initial_state = {
            "request_params": req.model_dump(),
            "tipe": req.tipe,
            "level": req.level,
            "revision_count": 0,
            "instruksi_revisi": req.instruksi_revisi
        }

        # Jika konten_id dikirimkan klien, kita simpan di state agar di-inject nanti di final payload (opsional)
        if req.konten_id and req.tipe not in ["quiz_pg", "quiz_essay", "pretest"]:
            initial_state["request_params"]["konten_id"] = req.konten_id

        if CELERY_AVAILABLE and celery_app is not None:
            from tasks.generate_task import run_generation
            # Dispatch ke Celery
            task = run_generation.delay(initial_state)
            now = datetime.now().isoformat()
            return JobInfo(
                job_id     = task.id,
                status     = JobStatus.PENDING,
                step       = req.tipe,
                created_at = now,
                updated_at = now,
                message    = "Generasi konten dikirim ke antrian Celery. Pantau via GET /job/{job_id}"
            )
        else:
            # Fallback ke in-process BackgroundTask
            job = _create_job(step=req.tipe)
            background_tasks.add_task(_run_generate_task_fallback, job.job_id, initial_state)
            job.message = "Generasi konten diproses di background. Pantau via GET /job/{job_id}"
            return job
            
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

import asyncio
import json

@app.post("/siswa/quiz/essay", tags=["Quiz"])
async def submit_essay(req: List[EssayEvalItem]):
    try:
        sys_prompt = load_prompt("essay_judge_system.j2")
        sys_msg = SystemMessage(content=sys_prompt)

        async def evaluate_single(item: EssayEvalItem):
            rubric_list = []
            try:
                # Mengubah string JSON dari frontend menjadi list jika ada
                rubric_list = json.loads(item.rubrik)
                if not isinstance(rubric_list, list):
                    rubric_list = [item.rubrik]
            except Exception:
                # Jika string biasa, jadikan item dalam list
                rubric_list = [item.rubrik]
                
            stimulus = item.stimulus or ""
            # Bersihkan dan gabung stimulus dengan soal sesuai template
            stimulus_dan_pertanyaan = f"{stimulus}\nPertanyaan: {item.soal}".strip()
            
            rp1 = rubric_list[0] if len(rubric_list) > 0 else ""
            rp2 = rubric_list[1] if len(rubric_list) > 1 else ""
            rp3 = rubric_list[2] if len(rubric_list) > 2 else ""
            
            usr_prompt = load_prompt(
                "essay_judge_user.j2",
                stimulus_dan_pertanyaan=stimulus_dan_pertanyaan,
                rubric_point_1=rp1,
                rubric_point_2=rp2,
                rubric_point_3=rp3,
                jawaban_siswa=item.jawaban_siswa
            )
            
            res = await eval_llm.ainvoke([sys_msg, HumanMessage(content=usr_prompt)])
            return clean_json_from_llm(res.content)

        # Lakukan pemanggilan LLM secara paralel untuk semua soal
        tasks = [evaluate_single(item) for item in req]
        evaluasi_hasil = await asyncio.gather(*tasks)
        
        response_data = {}
        for idx, hasil in enumerate(evaluasi_hasil):
            skor = hasil.get("final_score", 0)
            
            q_num = idx + 1
            response_data[f"q{q_num}_score"] = skor
            response_data[f"q{q_num}_eval"] = hasil.get("evaluation_reason", "")
            
        return response_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EVAL_ERR: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# RAG SERVICES ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/rag/rekomendasi", tags=["RAG"])
def rekomendasi(req: RekomendasiRequest):
    try:
        # Serialize Pydantic objects ke dict agar Jinja2 dapat mengakses field-nya via dot-notation
        available_dicts = [b.model_dump() for b in req.available]
        for b in available_dicts:
            if not b.get("materi") or str(b.get("materi")).strip().upper() in ("NONE", "NULL", "N/A", ""):
                b["materi"] = b.get("elemen_label") or "Tanpa Materi"

        in_progress_dicts = [b.model_dump() for b in req.in_progress_ids]
        for b in in_progress_dicts:
            if not b.get("materi") or str(b.get("materi")).strip().upper() in ("NONE", "NULL", "N/A", ""):
                b["materi"] = b.get("elemen_label") or "Tanpa Materi"

        complete_dicts = [b.model_dump() for b in req.complete_ids]

        prompt = load_prompt(
            "rekomendasi.j2",
            available=available_dicts,
            in_progress=in_progress_dicts,
            complete=complete_dicts,
        )
        sys_msg = SystemMessage(content=(
            "You are an AI Study Recommender for Indonesian students."
            "OUTPUT RULE: Return ONLY a raw JSON object. No markdown, no explanation, no code fences."
            "FIELD VALUES: Every bundle_id, mapel_label, elemen_label, and materi in your output MUST be copied character-for-character from the input data. Never invent or paraphrase these fields."
            "MATERI NULL RULE: If the source entry has materi = null, empty, 'None', or 'N/A', set the 'materi' field in your output to the value of elemen_label instead."
            "MANDATORY OUTPUT: You MUST always return at least 1 recommendation. An empty 'rekomendasi' array is NEVER acceptable when Available or In Progress materials exist."
        ))
        res = llm.invoke([sys_msg, HumanMessage(content=prompt)])
        content = clean_json_from_llm(res.content)

        # ── Post-processing: paksa nilai materi sesuai sumber di available/in_progress ──────
        # Jika materi sumber null/kosong → fallback ke elemen_label.
        combined_sources = available_dicts + in_progress_dicts
        available_map = {str(b["bundle_id"]): b for b in combined_sources}
        if isinstance(content, dict) and "rekomendasi" in content:
            for item in content["rekomendasi"]:
                bid = str(item.get("bundle_id", ""))
                if bid in available_map:
                    source = available_map[bid]
                    source_materi = source.get("materi")
                    # Jika sumber null/None/""/N/A → fallback ke elemen_label
                    if not source_materi or source_materi.strip().upper() in ("", "N/A", "NULL", "NONE"):
                        item["materi"] = source.get("elemen_label") or None
                    else:
                        item["materi"] = source_materi

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
    buku_id:          Optional[str] = Form(None, description="ID unik buku. Kosongkan untuk auto-generate UUID"),
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
    - `buku_id` adalah ID unik buku. Jika tidak dikirim, akan di-generate UUID otomatis.
    """
    # Validasi tipe file
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima.")

    # Auto-generate buku_id jika tidak dikirim
    if not buku_id:
        buku_id = str(uuid.uuid4())

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
        buku_id         = buku_id,
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

    # Validasi: step extract dan describe WAJIB punya file PDF
    if params.step in ("extract", "describe") and pdf_path is None:
        raise HTTPException(
            status_code=400,
            detail=f"Step '{params.step}' memerlukan file PDF. "
                   f"Sertakan parameter 'filename' atau upload via POST /pipeline/upload.",
        )

    if pdf_path is None:
        pdf_path = UPLOAD_DIR / "placeholder.pdf"

    if CELERY_AVAILABLE and celery_run_pipeline is not None:
        # ── Celery path: pipeline berjalan di worker terpisah (production) ────
        job_params = params.model_dump()
        job_params["pdf_path"] = str(pdf_path)
        task = celery_run_pipeline.delay(job_params)
        now = datetime.now().isoformat()
        return JobInfo(
            job_id     = task.id,
            status     = JobStatus.PENDING,
            filename   = filename,
            step       = params.step if params.step else "all",
            created_at = now,
            updated_at = now,
            message    = "Task dikirim ke Celery worker. Pantau via GET /pipeline/job/{job_id}",
        )
    else:
        # ── Fallback: in-process BackgroundTask (dev / tanpa Redis) ──────────
        job = _create_job(filename=filename, step=params.step if params.step else "all")
        background_tasks.add_task(_run_pipeline_task, job.job_id, pdf_path, params)
        return job


# ── Job Status ────────────────────────────────────────────────────────────────

@app.get("/job/{job_id}", response_model=JobInfo, tags=["Jobs"])
@app.get("/pipeline/job/{job_id}", response_model=JobInfo, tags=["Jobs"], include_in_schema=False)
def get_job(job_id: str):
    """Ambil status dan hasil dari sebuah job berdasarkan `job_id`."""
    # Coba baca dari Celery result backend (Redis) dulu
    job = _celery_result_to_job_info(job_id)
    if job:
        return job
    # Fallback: cari di in-memory store
    with _jobs_lock:
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
    with _jobs_lock:
        jobs = list(_jobs.values())
    if status:
        jobs = [j for j in jobs if j.status == status]
    # Urutkan terbaru dulu
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs


@app.delete("/job/{job_id}", tags=["Jobs"])
@app.delete("/pipeline/job/{job_id}", tags=["Jobs"], include_in_schema=False)
def delete_job(job_id: str):
    """Hapus job dari riwayat dan revoke task Celery jika masih berjalan."""
    # Coba revoke dari Celery
    if CELERY_AVAILABLE and celery_app is not None:
        try:
            # Menggunakan terminate=True untuk membunuh paksa task yang sedang berjalan
            celery_app.control.revoke(job_id, terminate=True)
        except Exception:
            pass  # Abaikan error revoke (task mungkin sudah selesai)
        return {"message": f"Job '{job_id}' dihapus dari antrian.", "job_id": job_id}
    # Fallback: hapus dari in-memory
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' tidak ditemukan.")
        job = _jobs.pop(job_id)
    return {"message": f"Job '{job_id}' dihapus.", "filename": job.filename}


# ══════════════════════════════════════════════════════════════════════════════
# CHAT MEMORY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

CHAT_CHUNK_SIZE = os.getenv("CHAT_CHUNK_SIZE")


@app.post("/chat-memory/ingest", tags=["Chat Memory"])
def ingest_chat_memory(request: IngestChatRequest):
    """Simpan satu pasangan Q&A (user + assistant) ke Qdrant chat memory."""
    page_content = f"""User:\n{request.user_message}\n\nAssistant:\n{request.assistant_message}""".strip()

    chunks = [page_content] if len(page_content) <= CHAT_CHUNK_SIZE else chunking_service.split_text(page_content)

    for idx, chunk in enumerate(chunks):
        embedding = embedding_service.embed(chunk)
        payload = {
            "user_id":      request.user_id,
            "sesi_id":      request.sesi_id,
            "chat_id":      request.chat_id,
            "chunk_index":  idx,
            "total_chunks": len(chunks),
            "page_content": chunk,
        }
        qdrant_service.insert(embedding=embedding, payload=payload)

    return {
        "status":       "success",
        "user_id":      request.user_id,
        "sesi_id":      request.sesi_id,
        "chat_id":      request.chat_id,
        "total_chunks": len(chunks),
    }


@app.post("/chat-memory/retrieve", tags=["Chat Memory"])
def retrieve_chat_memory(request: RetrieveChatRequest):
    """Ambil histori chat yang relevan berdasarkan query semantik."""
    query_embedding = embedding_service.embed(request.query)

    results = qdrant_service.search(
        query_vector=query_embedding,
        user_id=request.user_id,
        sesi_id=request.sesi_id,
        top_k=request.top_k,
    )

    formatted_results = [
        {
            "score":        r.score,
            "page_content": r.payload.get("page_content"),
            "metadata":     {k: v for k, v in r.payload.items() if k != "page_content"},
        }
        for r in results
    ]

    return {
        "query":         request.query,
        "user_id":       request.user_id,
        "sesi_id":       request.sesi_id,
        "top_k":         request.top_k,
        "total_results": len(formatted_results),
        "results":       formatted_results,
    }


# ══════════════════════════════════════════════════════════════════════════════
# STATIC FILES
# ══════════════════════════════════════════════════════════════════════════════

# Serve extraction folder for images
EXTRACTION_BASE_DIR = Path(__file__).resolve().parent / "extraction"
if EXTRACTION_BASE_DIR.exists():
    app.mount("/extraction", StaticFiles(directory=str(EXTRACTION_BASE_DIR)), name="extraction")


# LangSmith config dipindah ke atas (setelah load_dotenv) agar aktif
# sebelum LangChain/LangGraph diinisialisasi. Lihat bagian atas file ini.


# ══════════════════════════════════════════════════════════════════════════════
# MAIN (untuk development)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)